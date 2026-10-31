#!/usr/bin/env python3
"""Check online plugin operations against an owned HTTPS repository and UU worker."""
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent.parent
os.chdir(root)
stage = root / 'build/casefs/rootfs'
verification = json.loads((root / 'output/verification.json').read_text())
assert hashlib.sha256((root / verification['image']).read_bytes()).hexdigest() == verification['sha256']
assert all(verification['checks'].values()) and not verification['errors']
for script in ['bootstrap.sh', 'dispatch.sh']:
    assert (root / 'sources/localmod' / script).read_bytes() == (stage / 'usr/libexec/localmod' / script).read_bytes()
assert (stage / 'usr/libexec/localmod/installer-guard.sh').read_bytes() == (root / 'sources/localmod/installer-guard.sh').read_bytes()
for artifact, path in [('httpd_bridge.so', 'usr/lib/localmod/httpd_bridge.so'),
                       ('rc_bridge.so', 'usr/lib/localmod/rc_bridge.so')]:
    assert (root / 'build' / artifact).read_bytes() == (stage / path).read_bytes()
subprocess.run(['go', 'build', '-o', 'build/test-online', 'build/test_online_main.go', 'build/test_online.go',
                'build/native_runtime_client.go', 'build/coexist_helpers.go'], check=True,
               env=dict(os.environ, GOOS='linux', GOARCH='arm64', CGO_ENABLED='0'))
checks, details = {}, {}
for phase, expected in [('success', 7), ('errors', 13), ('concurrent', 8)]:
    result = root / f'build/online_{phase}_result.json'
    result.unlink(missing_ok=True)
    (root / 'build/online-phase').write_text(phase + '\n')
    shutil.copyfile(root / 'build/linux_online_job.sh', root / 'build/linux_job.sh')
    print('Running online workflow VM:', phase, flush=True)
    destination = root / f'build/online_{phase}_tests_run.log'
    with destination.open('w') as log:
        subprocess.run(['python3', 'build/run_linux.py', '--timeout', '180'], check=True, stdout=log, stderr=subprocess.STDOUT)
    data = json.loads(result.read_text())
    assert len(data['checks']) == expected and len(set(data['checks'])) == expected
    for name in data['checks']:
        key = phase + '_' + name
        assert key not in checks and 'PASS ' + name + '\n' in destination.read_text()
        checks[key] = True
    assert data['details']['uu_api_requests'] == data['details']['uu_monitor_downloads'] == data['details']['uu_launches'] == 1
    details[phase] = data['details']
    shutil.copyfile(destination, root / f'output/online_{phase}_tests_run.log')
official = root / 'build/casefs/official_rootfs'
wget = stage / 'usr/sbin/wget'
assert wget.read_bytes() == (official / 'usr/sbin/wget').read_bytes()
assert all(d['native_wget_sha256'] == hashlib.sha256(wget.read_bytes()).hexdigest() for d in details.values())
assert hashlib.sha256((root / verification['image']).read_bytes()).hexdigest() == verification['sha256']
fixture_names = {'test-online', 'onlineprobe.sh', 'onlineprobe_worker.sh',
                 'online-repo-ca.pem', 'online-phase', 'owned-uu-worker.sh'}
assert not [str(p) for p in stage.rglob('*') if p.name in fixture_names]
report = {
    'status': 'PASS', 'candidate_image': verification['image'], 'candidate_sha256': verification['sha256'],
    'checks': checks, 'details': details,
    'online_installer_sha256': hashlib.sha256((stage / 'rom/etc/koolshare/scripts/ks_app_install.sh').read_bytes()).hexdigest(),
    'guard_sha256': hashlib.sha256((stage / 'usr/libexec/localmod/installer-guard.sh').read_bytes()).hexdigest(),
    'retained_native_wget_sha256': hashlib.sha256(wget.read_bytes()).hexdigest(),
    'real_uu_monitor_or_third_party_plugin_executed': False,
    'plugin_download_tls_verification_disabled': False,
    'environment': [
        'Networkless ARM64 Linux VM, original ARM32 HTTPd/login/TLS and rc NTP/UU control flow',
        'Actual packaged perpboot/perpd/httpdb/skipd/dbus/versioncmp and production online installer',
        'Retained ASUS wget 1.20.1 with owned repository CA; hostname and untrusted CA rejection exercised',
        'Owned catalog follows pinned frontend RPC fields; owned plugin installs, updates and runs callbacks/worker',
        'UU API/monitor mapped to guest loopback hostnames and an owned worker; no real UU component/account',
        'Alpine start-stop-daemon/curl/legacy xtables and QEMU CPU/proc wrappers',
        'Numeric-IP download protection stays enabled; test hostnames resolve only inside the guest',
    ],
    'not_tested': [
        'Physical router boot, target kernel 4.1, real flash and NVRAM',
        'Public repository download with router DNS/WAN/default CA bundle and browser rendering',
        'Real third-party plugins, UU account/entitlement/discovery and actual traffic acceleration',
        'Rollback outside the center/skipd checkpoint scope or arbitrary privileged installer behavior',
        'These RAM-only cases do not test interruption; see interruption_tests.json for isolated restart coverage',
    ],
}
catalog = root / 'build/online_catalog_contract.json'
if catalog.exists():
    report['public_catalog_read_only_contract_snapshot'] = json.loads(catalog.read_text())
(root / 'output/online_plugin_tests.json').write_text(json.dumps(report, indent=2) + '\n')
print('PASS all 28 online plugin checks; candidate SHA256', verification['sha256'])
