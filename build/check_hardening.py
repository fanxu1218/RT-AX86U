#!/usr/bin/env python3
"""Exact readback bytes in sealed, bounded parallel VM jobs (no overlay)."""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from hardening_inputs import prepare
from check_memory import candidate, sha
from run_readonly_linux import run
from sealed_vm import SealedWorkspace
from release_config import CONFIG, ROOT

os.chdir(ROOT)
v, production = candidate()
assert v['image'] == CONFIG['image']
stage, back = ROOT / 'build/casefs/rootfs', ROOT / 'build/casefs/roundtrip'
paths = ['usr/libexec/localmod/' + x for x in ['archive-guard', 'plugin-run', 'log-limit',
         'localmod-status', 'localmod-event', 'bootstrap.sh', 'installer-guard.sh']]
paths += ['www/Module_Localmod.asp', 'usr/lib/localmod/httpd_bridge.so']
for p in paths:
    assert (stage / p).read_bytes() == (back / p).read_bytes()
artifacts = {p: sha(stage / p) for p in paths}
inputs = prepare()


def phase_job(item):
    phase, marker = item
    print('Sealed candidate VM:', phase, flush=True)
    job = SealedWorkspace(phase)
    receipt = {}
    log = ROOT / ('output/candidate_' + phase + '.log')
    text = run(log, timeout=660 if phase.endswith('memory') else 360,
               sealed=job, cpus=1, receipt=receipt)
    rows = [json.loads(l.removeprefix(marker + ' ')) for l in text.splitlines() if l.startswith(marker + ' ')]
    assert len(rows) == 1
    r = rows[0]
    if 'checks' in r:
        assert r['checks'] and all(r['checks'].values())
    if phase == 'candidate-installer':
        assert len(r['archive_cases']) == 28
    if phase == 'soak-httpd-cache':
        stats = [dict(re.findall(r'(\w+)=([\w]+)', l)) for l in text.splitlines() if l.startswith('TLS_CACHE ')]
        assert len(stats) >= 300 and all(int(s['capacity']) <= 256 and int(s['sessions']) <= 256 and int(s['timeout_seconds']) <= 300 for s in stats)
    if phase == 'soak-httpd-memory':
        assert r['healthy_queries'] == 243 and r['slow_disconnects'] == 6 and r['data_preserved'] and r['logout_and_relogin_verified']
    assert receipt['sealed_inputs_verified_before_and_after']
    return phase, dict(result=r, log_sha256=sha(log), vm=receipt)


plan = [('candidate-installer', 'INSTALLER_BOUNDARY_RESULT'), ('candidate-resources', 'RESOURCE_BOUNDS_RESULT'),
        ('candidate-uu', 'UU_RECOVERY_RESULT'), ('candidate-health', 'HEALTH_RESULT'),
        ('soak-httpd-cache', 'HTTPD_CACHE_RESULT'), ('soak-httpd-memory', 'HTTPD_MEMORY_RESULT')]
with ThreadPoolExecutor(max_workers=2) as pool:
    details = dict(pool.map(phase_job, plan))
assert candidate() == (v, production)
assert all(sha(stage / p) == sha(back / p) == digest for p, digest in artifacts.items())
assert all(sha(ROOT / p) == digest for p, digest in inputs.items())
(ROOT / 'output/hardening_tests.json').write_text(json.dumps(dict(
    status='FINAL_CANDIDATE_HARDENING_PASS', candidate_image=v['image'], candidate_sha256=v['sha256'],
    production_files=artifacts, source_sha256=inputs, phases=details, max_parallel_vms=2,
    vcpus_per_vm=1, memory_mib_per_vm=1024, source_overlay_used=False, physical_router_accessed=False), indent=2) + '\n')
print('PASS sealed candidate hardening, TLS cache and six-round coexistence', flush=True)
