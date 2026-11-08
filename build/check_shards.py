#!/usr/bin/env python3
"""Actual parallel native queries, owned cancellation and seal tamper checks."""
from device_config import render_source, compiler_flags
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import secrets
import threading
import time
from hardening_inputs import prepare
from run_readonly_linux import run
from sealed_vm import ROOT, SealedWorkspace, sha, acquire_slot


def wait_for(path, needle, future=None):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if path.exists() and needle in path.read_text(errors='replace'):
            return
        if future is not None and future.done():
            future.result()
            raise AssertionError('VM ended before readiness marker: ' + str(path))
        time.sleep(.1)
    raise TimeoutError('Owned shard readiness timeout: ' + str(path))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--candidate', action='store_true')
    args = ap.parse_args()
    os.chdir(ROOT)
    v = json.loads((ROOT / 'output/verification.json').read_text())
    assert sha(ROOT / v['image']) == v['sha256'] and all(v['checks'].values()) and not v['errors']
    prepare()
    if args.candidate:
        from check_memory import candidate
        from release_config import CONFIG
        assert candidate()[0] == v and v['image'] == CONFIG['image']
    else:
        from prepare_hardening_overlay import prepare_resources
        prepare_resources()
        arm = ['sources/zig-aarch64-macos-0.15.2/zig', 'cc', *compiler_flags(), '-O2', '-s']
        p = ROOT / 'build/hardening-overlay/usr/libexec/localmod/localmod-status'
        subprocess.run(arm + ['-o', str(p), 'sources/localmod/status.c'], check=True)
        p.chmod(0o755)
        subprocess.run(arm + ['-shared', '-fPIC', '-o', 'build/httpd_bridge_next.so', 'sources/localmod/httpd_bridge.c', '-ldl'], check=True)
        p = ROOT / 'build/hardening-overlay/www/Module_Localmod.asp'
        p.parent.mkdir(parents=True, exist_ok=True)
        from release_config import CONFIG
        p.write_text(render_source('sources/localmod/Module_Localmod.asp',CONFIG))
    paths = ['build/check_shards.py', 'build/sealed_vm.py', 'build/run_readonly_linux.py',
             'build/hardening_inputs.py', 'build/linux_real_plugins_job.sh', 'build/real_plugins_setup.sh']
    inputs = {p: sha(ROOT / p) for p in paths}
    checks, receipts, logs, timeline = {}, {}, {}, {}
    run_id = secrets.token_hex(6)
    def log_path(name):
        return ROOT / ('output/shard_' + run_id + '_' + name + '.log')
    first, second = acquire_slot(timeout=1), None
    try:
        second = acquire_slot(timeout=1)
        try:
            extra = acquire_slot(timeout=.3)
            os.close(extra)
            raise AssertionError('A third VM slot was granted')
        except TimeoutError:
            checks['third_vm_slot_is_refused_with_bounded_wait'] = True
        queued_cancel = threading.Event()
        queued_cancel.set()
        try:
            extra = acquire_slot(cancel=queued_cancel, timeout=1)
            os.close(extra)
            raise AssertionError('A cancelled queued VM obtained a slot')
        except InterruptedError:
            checks['queued_cancellation_does_not_start_vm'] = True
    finally:
        if second is not None:
            os.close(second)
        os.close(first)
    lock = threading.Lock()
    def execute(name, job, cancel=None):
        log = log_path(name)
        def started(pid):
            with lock:
                timeline[name] = dict(pid=pid, started=time.monotonic())
        receipt = {}
        try:
            return run(log, timeout=240, sealed=job, cpus=1, cancel=cancel,
                       on_started=started, receipt=receipt)
        finally:
            with lock:
                timeline.setdefault(name, {})['ended'] = time.monotonic()
                receipts[name] = receipt
                if log.exists():
                    logs[log.relative_to(ROOT).as_posix()] = sha(log)
    # All preparation is complete before any VM starts. No global phase file
    # is changed: each sealed export has its own explicitly selected phase.
    prefix = 'candidate-' if args.candidate else 'hardening-'
    native = [(name, SealedWorkspace(prefix + name)) for name in ['health', 'uu']]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {name: pool.submit(execute, 'native-' + name, job) for name, job in native}
        for name, future in futures.items():
            text = future.result()
            marker = 'HEALTH_RESULT ' if name == 'health' else 'UU_RECOVERY_RESULT '
            rows = [json.loads(line[len(marker):]) for line in text.splitlines() if line.startswith(marker)]
            assert len(rows) == 1 and rows[0]['checks'] and all(rows[0]['checks'].values()), name
            checks['parallel_native_' + name] = True
    a, b = timeline['native-health'], timeline['native-uu']
    checks['native_vm_execution_overlapped'] = max(a['started'], b['started']) < min(a['ended'], b['ended'])
    assert checks['native_vm_execution_overlapped']

    def smoke_script(name, seconds):
        return ('''#!/bin/sh
set -eu
[ "$(ls /sys/class/net)" = lo ]
[ ! -e /work/.git ] && [ ! -e /work/upstream ]
[ ! -e /work/build/native-lifecycle-private ]
[ "$(cat /work/build/real-plugin-phase)" = candidate-shard-''' + name + ''' ]
if (echo forbidden > /work/build/readonly-probe) 2>/dev/null;then exit 97;fi
printf '%s\\n' 'SHARD_READY ''' + name + ''''
sleep ''' + str(seconds) + '''
printf '%s\\n' 'SHARD_DONE ''' + name + ''''
''').encode()
    cancel = threading.Event()
    cancelled = SealedWorkspace('candidate-shard-cancel', guest_job=smoke_script('cancel', 30))
    survivor = SealedWorkspace('candidate-shard-survivor', guest_job=smoke_script('survivor', 5))
    with ThreadPoolExecutor(max_workers=2) as pool:
        left = pool.submit(execute, 'cancel', cancelled, cancel)
        right = pool.submit(execute, 'survivor', survivor)
        wait_for(log_path('cancel'), 'SHARD_READY cancel', left)
        wait_for(log_path('survivor'), 'SHARD_READY survivor', right)
        cancel.set()
        try:
            left.result()
            raise AssertionError('Cancellation did not stop its owned VM')
        except InterruptedError:
            checks['cancel_stops_only_owned_vm'] = True
        text = right.result()
        assert 'SHARD_DONE survivor' in text and 'SHARD_READY cancel' not in text
        checks['survivor_completes_after_other_vm_cancelled'] = True
    assert cancelled.job.exists() and not survivor.job.exists()
    checks['failed_workspace_retained_success_workspace_removed'] = True
    cancelled.verify()
    target = cancelled.workspace / 'build/real_plugins_setup.sh'
    target.write_bytes(target.read_bytes() + b'\n# owned prelaunch tamper probe\n')
    try:
        cancelled.verify()
        raise RuntimeError('Prelaunch tampering was accepted')
    except AssertionError:
        checks['prelaunch_seal_tamper_rejected'] = True
    assert sha(ROOT / 'build/real_plugins_setup.sh') == inputs['build/real_plugins_setup.sh']
    checks['snapshot_writes_do_not_modify_original_inputs'] = True
    # Change an unused file after the guest is ready; the guest itself exits
    # successfully, but the host must refuse a PASS after its manifest changes.
    tampered = SealedWorkspace('candidate-shard-tamper', guest_job=smoke_script('tamper', 5))
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(execute, 'tamper', tampered)
        wait_for(log_path('tamper'), 'SHARD_READY tamper', future)
        target = tampered.workspace / 'build/real_plugins_setup.sh'
        target.write_bytes(target.read_bytes() + b'\n# owned postlaunch tamper probe\n')
        try:
            future.result()
            raise RuntimeError('Postlaunch tampering was accepted')
        except AssertionError:
            checks['postlaunch_seal_tamper_rejected_despite_guest_success'] = True
    assert tampered.job.exists()
    checks['tampered_workspace_retained_for_diagnosis'] = True
    assert inputs == {p: sha(ROOT / p) for p in inputs}
    assert sha(ROOT / v['image']) == v['sha256']
    assert all(checks.values())
    report = dict(status='LOCAL_SEALED_SHARDS_PASS', base_candidate_image=v['image'],
                  base_candidate_sha256=v['sha256'], source_overlay_used=not args.candidate,
                  checks=checks, source_sha256=inputs, receipts=receipts, logs=logs,
                  timeline=timeline, max_parallel_vms=2, vcpus_per_vm=1, memory_mib_per_vm=1024,
                  failure_workspaces_retained=[str(j.job.relative_to(ROOT)) for j in [cancelled, tampered]],
                  limits=['Only the sealed executor supports parallel VM execution; legacy checker preparation remains serial',
                          'No guest NIC or physical router; root-owned test accounts only',
                          'Host manifest checks detect accidental input mutation; they do not defend against malicious host root'])
    if args.candidate:
        report.update(candidate_image=v['image'], candidate_sha256=v['sha256'])
    (ROOT / 'output/shard_tests.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS', len(checks), 'sealed/parallel checks; expected failure fixtures retained', flush=True)


if __name__ == '__main__':
    main()
