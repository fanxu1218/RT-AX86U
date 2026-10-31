#!/usr/bin/env python3
"""Audit retained UU code/resources and the scoped local adapter models.

No downloaded monitor, UU account, game console or acceleration is exercised.
"""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
official = root / 'build/casefs/official_rootfs'
stage = root / 'build/casefs/rootfs'
files = {
    'vendor_rc': ('sbin/rc', 'usr/libexec/localmod/rc.vendor'),
    'uu_page': ('www/UUAccelerator.asp', 'www/UUAccelerator.asp'),
    'uu_icon': ('www/images/uu_accelerator.png', 'www/images/uu_accelerator.png'),
}
checks = {}
hashes = {}
for label, (original, retained) in files.items():
    source = (official / original).read_bytes()
    target = (stage / retained).read_bytes()
    checks[label + '_identical'] = source == target
    hashes[label] = hashlib.sha256(target).hexdigest()
checks['official_monitor_endpoint_retained'] = (
    b'https://router.uu.163.com/api/script/monitor?type=asuswrt'
    in (stage / 'usr/libexec/localmod/rc.vendor').read_bytes()
)
page = (stage / 'www/UUAccelerator.asp').read_text(encoding='utf-8-sig')
checks['official_navigation_and_label_mac_retained'] = (
    "https://router.uu.163.com/asus/pc.html#/acce?gwSn=" in page
    and 'get_label_mac();' in page and 'mac.toLowerCase()' in page
)
trace = (root / 'build/hooks_trace.log').read_text()
checks['uu_style_eval_contract_preserved_in_model'] = all(
    trace.count(marker) == 1 for marker in [
        'VENDOR uu-download-contract preserved',
        'VENDOR uu-monitor-contract preserved',
        'WORK uu-vendor-commands-preserved',
    ]
)
runtime = (root / 'build/runtime_tests.log').read_text()
checks['uu_page_and_query_bypass_private_api_in_model'] = all(
    marker in runtime for marker in ['PASS uu-vendor-page', 'PASS uu-vendor-query']
)
report = {
    'status': 'STATIC_AND_MODEL_PASS' if all(checks.values()) else 'FAIL',
    'checks': checks,
    'sha256': hashes,
    'boundary': 'Exact retained ASUS 24437 binaries/resources plus ARM32 adapter fixtures; the UU-style commands are observed by a mock vendor _eval, never executed.',
    'actual_downloaded_uu_component_executed': False,
    'not_tested': [
        'native exec_uu/NTP lifecycle on a router',
        'UU account, region eligibility, entitlement and console discovery',
        'monitor download/execution, packet routing and actual acceleration',
        'third-party plugin and UU coexistence on target hardware',
    ],
}
(root / 'output/uu_compatibility_tests.json').write_text(json.dumps(report, indent=2) + '\n')
for name, passed in checks.items():
    print('PASS' if passed else 'FAIL', name)
assert all(checks.values())
