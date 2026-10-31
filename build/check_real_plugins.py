#!/usr/bin/env python3
"""Validate authentic HND plugin lifecycles against the read-back candidate."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

from prepare_real_plugins import prepare
from run_readonly_linux import run

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
stage = ROOT / 'build/casefs/rootfs'
readback = ROOT / 'build/casefs/roundtrip'
verification = json.loads((ROOT / 'output/verification.json').read_text())
assert all(verification['checks'].values()) and not verification['errors']
image = ROOT / verification['image']
sha256 = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert sha256(image) == verification['sha256']
for name in ['bootstrap.sh', 'dispatch.sh', 'installer-guard.sh']:
    assert (ROOT / 'sources/localmod' / name).read_bytes() == (stage / 'usr/libexec/localmod' / name).read_bytes()
for name, path in [('httpd_bridge.so', 'usr/lib/localmod/httpd_bridge.so'),
                   ('rc_bridge.so', 'usr/lib/localmod/rc_bridge.so')]:
    assert (ROOT / 'build' / name).read_bytes() == (stage / path).read_bytes()
for path in ['usr/libexec/localmod/bootstrap.sh', 'usr/libexec/localmod/dispatch.sh',
             'rom/etc/koolshare/scripts/base.sh', 'rom/etc/koolshare/scripts/ks_app_install.sh',
             'usr/libexec/localmod/busybox', 'usr/bin/skipd', 'usr/bin/dbus',
             'usr/sbin/curl', 'usr/sbin/wget', 'usr/libexec/localmod/httpd',
             'usr/libexec/localmod/rc.vendor', 'rom/etc/koolshare/bin/start-stop-daemon']:
    assert (stage / path).read_bytes() == (readback / path).read_bytes(), path
for applet in ['tee', 'xargs']:
    assert os.readlink(stage / 'usr/bin' / applet) == os.readlink(readback / 'usr/bin' / applet) == '/usr/libexec/localmod/busybox'
assert (stage / 'usr/libexec/localmod/busybox').read_bytes() == (ROOT / 'build/casefs/koolcenter_rootfs/bin/busybox').read_bytes()
manifest = prepare()
subprocess.run(['go', 'build', '-trimpath', '-o', 'build/test-real-plugins',
                'build/test_real_plugins.go', 'build/test_online.go',
                'build/native_runtime_client.go', 'build/coexist_helpers.go'], check=True,
               env=dict(os.environ, GOOS='linux', GOARCH='arm64', CGO_ENABLED='0'))
checks, details = {}, {}
for phase, expected in [('upgrade', 22), ('fresh', 10)]:
    (ROOT / 'build/real-plugin-phase').write_text(phase + '\n')
    print('Running real plugin VM:', phase, '(read-only export, no NIC, RAM-only chroot)', flush=True)
    text = run(ROOT / f'output/real_plugins_{phase}_tests_run.log')
    results = [line.removeprefix('REAL_PLUGIN_RESULT ') for line in text.splitlines() if line.startswith('REAL_PLUGIN_RESULT ')]
    assert len(results) == 1
    data = json.loads(results[0])
    names = data['checks']
    assert len(names) == len(set(names)) == expected, names
    assert all('PASS ' + name + '\n' in text for name in names)
    assert data['details']['uu_api_requests'] == data['details']['uu_monitor_downloads'] == data['details']['uu_launches'] == 1
    assert data['details']['actual_process_helper_sha256'] == sha256(stage / 'rom/etc/koolshare/bin/start-stop-daemon')
    assert data['details']['native_wget_sha256'] == sha256(stage / 'usr/sbin/wget')
    checks.update({phase + '_' + name: True for name in names})
    details[phase] = data['details']
assert not (ROOT / 'build/readonly-guest-write-probe').exists()
assert sha256(image) == verification['sha256']
assert all(sha256(ROOT / p['path']) == p['sha256'] for p in manifest['packages'])
report = {
    'status': 'LOCAL_ISOLATION_PASS', 'candidate_image': verification['image'],
    'candidate_sha256': verification['sha256'], 'checks': checks,
    'details': details, 'sources': manifest,
    'run_observations': ['One initial DDNS-Go read-only status request returned an unexpected EOF after HTTP 200 headers. A fresh full upgrade/fresh VM run, including four distinct status requests, passed without retrying an RPC. Cause remains unconfirmed; server-log diagnostics were added. This is not claimed as a firmware fix.'],
    'production_files': {path: sha256(stage / path) for path in [
        'usr/libexec/localmod/bootstrap.sh', 'usr/libexec/localmod/dispatch.sh',
        'rom/etc/koolshare/scripts/base.sh', 'usr/libexec/localmod/busybox', 'bin/busybox', 'usr/sbin/curl']},
    'isolation': [
        'Apple Virtualization ARM64 guest: no network devices, no physical disk/device passthrough',
        'Host workspace exported read-only; guest write probe rejected; only loopback interface before synthetic LAN setup',
        'Candidate root copied to guest RAM; 64 MiB JFFS tmpfs; disposable chroot with real proc and ARM binfmt_misc F',
        'No host extraction/execution of plugin scripts; package digests and archive member types checked before guest execution',
        'Test results returned through bounded serial output; guest has no host-writable results directory',
    ],
    'environment': [
        'Original ASUS ARM32 HTTPd/login/TLS, rc NTP/UU, curl, wget, BusyBox and native libraries',
        'Actual core httpdb/perp/skipd/dbus/versioncmp/start-stop-daemon, production bootstrap/installer/callback',
        'Six pinned real package versions, unmodified installers/config scripts/uninstallers/binaries',
        'DDNS-Go 1.28.0 packaged from unchanged pinned upstream git files; other five archives used byte-for-byte',
        'Synthetic NVRAM/account/shadow and guest-local verified HTTPS repository; no real account credentials',
        'Alpine 6.12 guest kernel and legacy xtables boundary; original 4.1 kernel/iptables still require hardware',
        'UU original NTP/download/checksum control flow with guest-local API and owned monitor/heartbeat worker',
    ],
    'not_tested': [
        'Physical router boot, flash, stock kernel/iptables, real NVRAM/JFFS and Wi-Fi/NAT performance',
        'Router public repository DNS/WAN/default CA trust and browser rendering',
        'Alibaba DNS API changes, DDNSTO authenticated cloud tunnel, DDNS-Go provider authentication',
        'Real UU monitor/account/discovery/entitlement/game traffic acceleration',
        'Arbitrary plugin ecosystem; separate interruption_tests.json covers defined recovery cases, not physical power loss',
    ],
}
(ROOT / 'output/real_plugin_tests.json').write_text(json.dumps(report, indent=2) + '\n')
print('PASS', len(checks), 'real plugin checks; image SHA256', verification['sha256'])
