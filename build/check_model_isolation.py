#!/usr/bin/env python3
"""Exercise actual private model jobs, UBIFS readback and owned failure controls."""
from device_config import leb_size
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import tarfile
import threading
import time
from model_private import ROOT, copy_tree, run_model, tree_inventory
from sealed_vm import encoded, inventory, sha


def archive_failure(job):
    # Only a completed, marked failure created by this test may be archived.
    assert job.parent == ROOT / 'build/casefs/model-private' and not job.is_symlink()
    assert json.loads((job / 'owner.json').read_text())['job'] == job.name
    before = inventory(job)
    folder = ROOT / 'build/vm-failures'
    assert not folder.is_symlink()
    folder.mkdir(mode=0o700, exist_ok=True)
    archive = folder / (job.name + '.tar.gz')
    assert not archive.exists()
    with tarfile.open(archive, 'w:gz', dereference=False) as out:
        out.add(job, arcname=job.name)
    with tarfile.open(archive, 'r:gz') as source:
        entries = source.getmembers()
        assert entries[0].name == job.name and entries[0].isdir()
        members = {p.name[len(job.name) + 1:]: p for p in entries[1:]}
        assert set(members) == set(before) and len(members) == len(entries) - 1
        for name, expected in before.items():
            item = members[name]
            assert stat.S_IMODE(item.mode) == expected['mode']
            if expected['type'] == 'file':
                assert item.isfile() or item.islnk()
                with source.extractfile(item) as data:
                    assert hashlib.file_digest(data, 'sha256').hexdigest() == expected['sha256']
                assert item.size == expected['bytes'] if item.isfile() else True
            elif expected['type'] == 'link':
                assert item.issym() and item.linkname == expected['target']
            else:
                assert item.isdir()
    assert inventory(job) == before
    receipt = dict(archive=archive.relative_to(ROOT).as_posix(), sha256=sha(archive), entries_verified=len(before))
    (folder / (job.name + '.archive.json')).write_bytes(encoded(receipt) + b'\n')
    shutil.rmtree(job)
    return receipt


def readback(volume, out):
    from base_migration import metadata, tree
    from ubireader.ubi_io import ubi_file
    from ubireader.ubifs import ubifs, walk
    from ubireader.ubifs.output import extract_files
    assert volume.parent.parent == ROOT / 'build/model-results' and volume.name == 'localmod-rootfs.ubifs'
    parent = ROOT / 'build/casefs/model-readback'
    parent.mkdir(mode=0o700, exist_ok=True)
    job = parent / ('audit-' + secrets.token_hex(12))
    job.mkdir(mode=0o700)
    parsed = ubifs(ubi_file(str(volume), leb_size()))
    actual_meta = metadata(parsed)
    assert len(actual_meta) <= 20000
    stage = ROOT / 'build/casefs/rootfs'
    expected_paths = {'/'} | {'/' + p for p in inventory(stage)}
    source_meta = json.loads((ROOT / 'build/staged_metadata.json').read_text())
    assert set(actual_meta) == expected_paths
    for name in actual_meta:
        for key in ['mode', 'uid', 'gid']:
            assert actual_meta[name][key] == source_meta[name][key], (name, key)
        for parent_name in Path(name).parents:
            assert actual_meta[str(parent_name)]['mode'] & 0o170000 == 0o040000
    expected_meta = {name: source_meta[name] for name in expected_paths}
    target = job / 'rootfs'
    target.mkdir()
    extract_files(parsed, str(target))
    expected = tree(stage, expected_meta)
    assert tree(target, actual_meta) == expected
    inodes, bad = {}, []
    walk.index(parsed, parsed.master_node.root_lnum, parsed.master_node.root_offs, inodes, bad)
    assert not bad and all(getattr(n['ino'], 'xattr_cnt', 0) == 0 for n in inodes.values())
    # Compare regular-file alias groups using inode numbers from the archive.
    actual_groups = {}
    def visit(number, name):
        node = inodes[number]
        if node['ino'].mode & 0o170000 == 0o100000:
            actual_groups.setdefault(number, []).append(name)
        for dent in node.get('dent', []):
            visit(dent.inum, name.rstrip('/') + '/' + dent.name)
    visit(1, '/')
    groups = sorted(sorted(paths) for paths in actual_groups.values() if len(paths) > 1)
    original_groups = {}
    for name in expected_paths - {'/'}:
        path = stage / name.lstrip('/')
        if not path.is_symlink() and path.is_file():
            s = path.stat()
            original_groups.setdefault((s.st_dev, s.st_ino), []).append(name)
    assert groups == sorted(sorted(p) for p in original_groups.values() if len(p) > 1)
    result = dict(status='PRIVATE_MODEL_BUILD_READBACK_PASS', paths=len(expected_paths),
                  ubifs_sha256=sha(volume), tree_sha256=hashlib.sha256(encoded(expected)).hexdigest(),
                  contents_types_links_modes_owners_match=True, no_xattrs=True,
                  hardlink_groups_preserved=len(groups), excluded_removed_source_metadata=sorted(set(source_meta) - expected_paths))
    out.write_text(json.dumps(result, indent=2) + '\n')
    shutil.rmtree(job)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--readback', type=Path)
    ap.add_argument('--readback-out', type=Path)
    args = ap.parse_args()
    if args.readback is not None:
        readback(args.readback, args.readback_out)
        return
    os.chdir(ROOT)
    v = json.loads((ROOT / 'output/verification.json').read_text())
    assert all(v['checks'].values()) and not v['errors'] and sha(ROOT / v['image']) == v['sha256']
    source_names = ['build/model_private.py', 'build/run_linux.py', 'build/check_model_isolation.py',
                    'build/check_lifecycle.py', 'build/check_online.py', 'build/build_candidate.py', 'build/sealed_vm.py']
    inputs = {p: sha(ROOT / p) for p in source_names}
    protected_names = [v['image'], 'build/localmod-rootfs.ubifs', 'sources/localmod/bootstrap.sh',
                       'build/linux_job.sh', 'build/online-phase']
    protected = {p: sha(ROOT / p) if (ROOT / p).exists() else None for p in protected_names}
    checks, receipts, logs, failures = {}, {}, {}, []
    result_root = ROOT / 'build/model-results'
    assert not result_root.is_symlink()
    result_root.mkdir(mode=0o700, exist_ok=True)
    build_outputs = result_root / ('run-' + secrets.token_hex(12))
    for name, destination in [('build', 'build/runtime_tests.log'), ('filemap', 'output/filemap_tests.log'),
                              ('hooks', 'build/hooks_test_run.log'), ('restore', 'build/restore_tests_run.log'),
                              ('center', 'build/center_tests_run.log'), ('native_httpd', 'build/native_httpd_tests_run.log'),
                              ('native_uu', 'build/native_uu_tests_run.log')]:
        print('Private actual model job:', name, flush=True)
        command = ['python3', 'build/run_linux.py', '--job', name, '--timeout', '180']
        if name == 'build':
            command += ['--output-root', str(build_outputs)]
        with (ROOT / destination).open('w') as output:
            subprocess.run(command, check=True, stdout=output, stderr=subprocess.STDOUT)
        text = (ROOT / destination).read_text()
        rows = [json.loads(s[len('MODEL_RECEIPT '):]) for s in text.splitlines() if s.startswith('MODEL_RECEIPT ')]
        assert len(rows) == 1 and rows[0]['outcome'] == 'PASS' and rows[0]['runner_sha256'] == inputs['build/model_private.py']
        assert rows[0]['immutable_inputs_verified'] and not rows[0]['checkout_exported']
        assert not (ROOT / rows[0]['job']).exists()
        receipts[name] = rows[0]
        checks['actual_' + name + '_in_private_workspace'] = True
        log = ROOT / ('output/model_' + name + '_tests_run.log')
        log.write_text(text)
        logs[log.relative_to(ROOT).as_posix()] = sha(log)
    for script in ['verify_hooks.py', 'verify_compatibility.py', 'verify_native_runtime.py', 'verify_uu_compatibility.py']:
        subprocess.run(['python3', 'build/' + script], check=True)
    for name in ['runtime_tests.log', 'hooks_trace.log', 'hooks_test_run.log', 'restore_tests_run.log',
                 'restore_hook_trace.log', 'center_tests_run.log', 'native_httpd_tests_run.log', 'native_uu_tests_run.log']:
        shutil.copyfile(ROOT / 'build' / name, ROOT / 'output' / name)
    audit = build_outputs / 'readback.json'
    subprocess.run([str(ROOT / 'analysis/.venv/bin/python'), 'build/check_model_isolation.py',
                    '--readback', str(build_outputs / 'localmod-rootfs.ubifs'), '--readback-out', str(audit)], check=True)
    readback_result = json.loads(audit.read_text())
    checks['private_model_ubifs_independently_read_back'] = readback_result['contents_types_links_modes_owners_match']
    # A synthetic alias proves cloning never links mutable fixtures to inputs.
    alias = result_root / ('alias-' + secrets.token_hex(12))
    alias.mkdir()
    (alias / 'source').mkdir()
    (alias / 'source/a').write_bytes(b'owned alias probe')
    os.link(alias / 'source/a', alias / 'source/b')
    copy_tree(alias / 'source', alias / 'copy')
    assert (alias / 'copy/a').stat().st_ino == (alias / 'copy/b').stat().st_ino != (alias / 'source/a').stat().st_ino
    assert tree_inventory(alias / 'source') == tree_inventory(alias / 'copy')
    (alias / 'copy/a').write_bytes(b'private mutation')
    assert (alias / 'source/a').read_bytes() == b'owned alias probe'
    shutil.rmtree(alias)
    checks['internal_hardlinks_preserved_without_linking_originals'] = True
    prior = sha(ROOT / 'build/hooks_trace.log')
    controls = {
        'input-tamper': b'echo probe >> /work/sources/localmod/bootstrap.sh\necho forbidden > /work/build/hooks_trace.log\n',
        'output-link': b'echo forbidden > /work/build/hooks_trace.log\nln -s /work/sources/localmod/bootstrap.sh /work/build/center_install_trace.log\n',
        'unlisted-output': b'echo forbidden > /work/build/unlisted-model-output\n',
    }
    for name, script in controls.items():
        print('Private model negative control:', name, flush=True)
        receipt = {}
        try:
            run_model('hooks', guest_script=script, receipt=receipt)
        except AssertionError as error:
            assert receipt.get('outcome') == 'FAIL', (name, receipt)
            job = ROOT / receipt['job']
            assert (job / 'workspace/build/linux-job.status').read_text().strip() == '0'
            if name in ['input-tamper', 'unlisted-output']:
                assert 'Model input manifest changed' in str(error), str(error)
            else:
                assert (job / 'workspace/build/center_install_trace.log').is_symlink()
            assert sha(ROOT / 'build/hooks_trace.log') == prior
            failures.append(dict(case=name, receipt=receipt, archive=archive_failure(job), guest_completed_before_rejection=True))
            checks[name.replace('-', '_') + '_rejected_without_collecting_results'] = True
        else:
            raise AssertionError('Negative control accepted: ' + name)
    # Both controlled VMs must actually be ready before cancellation. A sibling
    # completes with its own result; no global process-name kill is used.
    cancel, ready = threading.Event(), {}
    mutex = threading.Lock()
    def execute(name):
        receipt = {}
        def started(pid, job):
            with mutex:
                ready[name] = (pid, job)
        script = ('echo MODEL_READY > /work/build/hooks_trace.log\nsleep ' + ('40' if name == 'cancel' else '20') + '\necho MODEL_DONE >> /work/build/hooks_trace.log\n').encode()
        try:
            return run_model('hooks', timeout=90, guest_script=script, receipt=receipt,
                             output_root=result_root / ('run-' + secrets.token_hex(12)),
                             cancel=cancel if name == 'cancel' else None, on_started=started), receipt
        finally:
            receipts[name] = receipt
    with ThreadPoolExecutor(max_workers=2) as pool:
        left, right = pool.submit(execute, 'cancel'), pool.submit(execute, 'survivor')
        deadline = time.monotonic() + 70
        while time.monotonic() < deadline:
            with mutex:
                snapshot = dict(ready)
            if len(snapshot) == 2 and all((j.workspace / 'build/hooks_trace.log').exists() for _, j in snapshot.values()):
                break
            for future in [left, right]:
                if future.done():
                    future.result()
                    raise AssertionError('VM ended before paired readiness')
            time.sleep(.1)
        else:
            cancel.set()
            raise TimeoutError('Paired private model readiness')
        cancel.set()
        try:
            left.result()
        except InterruptedError:
            assert receipts['cancel']['error_type'] == 'InterruptedError'
        else:
            raise AssertionError('Owned model cancellation ignored')
        _, survivor_receipt = right.result()
        assert survivor_receipt['outcome'] == 'PASS'
        assert (ROOT / survivor_receipt['output_root'] / 'hooks_trace.log').read_text().splitlines() == ['MODEL_READY', 'MODEL_DONE']
    assert sha(ROOT / 'build/hooks_trace.log') == prior
    assert ready['cancel'][0] != ready['survivor'][0]
    assert ready['cancel'][1].job.exists() and not ready['survivor'][1].job.exists()
    failures.append(dict(case='cancel', receipt=receipts['cancel'], archive=archive_failure(ready['cancel'][1].job)))
    checks['cancel_stops_only_owned_vm_and_sibling_completes'] = True
    checks['expected_failures_fully_verified_before_private_archival'] = True
    assert protected == {p: sha(ROOT / p) if (ROOT / p).exists() else None for p in protected}
    assert inputs == {p: sha(ROOT / p) for p in inputs}
    checks['original_image_ubifs_source_and_global_selectors_unchanged'] = True
    checks['final_runner_and_controller_sources_unchanged'] = True
    assert all(checks.values())
    report = dict(status='LOCAL_PRIVATE_MODEL_PASS', candidate_image=v['image'], candidate_sha256=v['sha256'],
                  checks=checks, source_sha256=inputs, receipts=receipts, logs=logs,
                  private_build_readback=readback_result, expected_failure_evidence=failures,
                  protected_sha256=protected, max_parallel_vms=2, guest_network_devices=0,
                  limits=['Only controlled model jobs use private writable exports; actual third-party scripts retain read-only exports',
                          'Checker input preparation and named result collection remain serial',
                          'Only synthetic certificate state is copied between model VMs; no physical router or user configuration is accessed',
                          'A manifest detects accidental guest input changes and does not defend against malicious host root'])
    (ROOT / 'output/model_isolation_tests.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS', len(checks), 'private model checks; candidate', v['sha256'], flush=True)


if __name__ == '__main__':
    main()
