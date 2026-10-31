#!/usr/bin/env python3
"""Summarize native vendor execution without treating synthetic inputs as hardware."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
httpd = (root / 'build/native_httpd_tests_run.log').read_text()
uu = (root / 'build/native_uu_tests_run.log').read_text()
checks = {}
for protocol in ['http', 'https']:
    for suffix in ['native_login_page_and_transport', 'wrong_password_rejected',
                   'native_password_check_and_session_issuance',
                   'native_protected_page_with_issued_token',
                   'issued_token_reaches_real_software_center',
                   'native_post_body_and_real_callback',
                   'missing_and_invalid_sessions_blocked', 'logout_revokes_session']:
        name = protocol + '_' + suffix
        checks[name] = 'PASS ' + name in httpd
for name in ['native_ntp_uu_start_once', 'native_uu_bad_checksum_blocks_execution',
             'native_uu_api_failure_blocks_execution', 'native_uu_malformed_response_blocks_execution',
             'native_uu_non_china_sku_skipped', 'native_uu_ap_mode_skipped']:
    checks[name] = 'PASS ' + name in uu
checks['early_stdio_before_adapter_constructor'] = all(
    'PASS early stdio before adapter constructor' in
    (root / ('build/native_' + mode + '_server.log')).read_text()
    for mode in ['http', 'https']
)
official = root / 'build/casefs/official_rootfs'
stage = root / 'build/casefs/rootfs'
checks['native_httpd_readonly_usr_path_and_bytes'] = (
    (stage / 'usr/libexec/localmod/httpd').read_bytes() == (official / 'usr/sbin/httpd').read_bytes()
    and '"/usr/libexec/localmod/httpd"' in (root / 'sources/localmod/launcher.c').read_text()
)
paths = ['usr/sbin/httpd', 'sbin/rc', 'usr/lib/libshared.so', 'usr/lib/libpasswd.so', 'usr/lib/libmssl.so',
         'usr/lib/libssl.so.1.1', 'usr/lib/libcrypto.so.1.1']
retained = {'usr/sbin/httpd': 'usr/libexec/localmod/httpd', 'sbin/rc': 'usr/libexec/localmod/rc.vendor'}
for name in paths:
    assert (stage / retained.get(name, name)).read_bytes() == (official / name).read_bytes(), name
hashes = {name: hashlib.sha256((official / name).read_bytes()).hexdigest() for name in paths}
test_names = {'native_hw_fixture.so', 'native_uu_transport.so', 'native_shadow_hash.txt',
              'native_defaults.bin', 'Module_NativeProbe.asp', 'native_probe.sh'}
fixture_leaks = [str(p.relative_to(stage)) for p in stage.rglob('*') if p.name in test_names]
assert not fixture_leaks, fixture_leaks
for path in (stage / 'usr/lib/localmod').glob('*.so'):
    assert b'local-test-password' not in path.read_bytes(), path
report = {
    'status': 'PASS' if all(checks.values()) else 'FAIL',
    'checks': checks,
    'executed_vendor_binary_sha256': hashes,
    'native_login_session_password_and_tls_functions_interposed': False,
    'tls_client_certificate_verification': 'Ephemeral fixture CA trusted explicitly; hostname/chain verified, no insecure bypass',
    'http_session_cookie': 'asus_token',
    'https_session_cookie': 'asus_s_token',
    'uu_native_ntp_signal_and_exec_uu_executed': True,
    'controlled_monitor_executed': True,
    'real_uu_monitor_executed': False,
    'test_fixture_files_in_firmware': fixture_leaks,
    'fixtures': ['pinned factory defaults with synthetic NVRAM/board inputs',
                 'synthetic local shadow account and ephemeral certificate',
                 'private address on VM loopback; VM has no external NIC',
                 'UU DNS/service notification boundary and observed native pause',
                 'wget test transport maps only approved URLs to local HTTP/curl; all other destinations rejected',
                 'owned monitor script verifies absence of inherited LD_PRELOAD before recording execution'],
    'not_tested': ['target kernel 4.1, real NVRAM/board hardware and physical boot',
                   'production certificate creation/persistence and browser UI',
                   'real NTP time synchronization and external UU download/TLS',
                   'UU accounts, entitlement, console discovery, traffic acceleration and device plugin coexistence'],
}
(root / 'output/native_runtime_tests.json').write_text(json.dumps(report, indent=2) + '\n')
for name, passed in checks.items():
    print('PASS' if passed else 'FAIL', name)
assert all(checks.values())
