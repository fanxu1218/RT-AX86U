#!/usr/bin/env python3
"""Bind fresh P7 executions to 388.13; this never approves physical flashing."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'build'))
from sealed_vm import encoded, inventory, sha
from gui24447 import payload


def read(name):
    return json.loads((ROOT / name).read_text())


def binding(report):
    return (report.get('stage', {}).get('image', {}).get('sha256')
        or report.get('candidate', {}).get('sha256')
        or report.get('image', {}).get('sha256') or report.get('candidate_sha256'))


def sources(report):
    for name, digest in report.get('source_sha256', {}).items():
        assert sha(ROOT / name) == digest, ('Stale source evidence', name)


def main():
    candidate = read('output/merlin38813_native_candidate_tests.json')
    image = candidate['image']; digest = image['sha256']
    assert sha(ROOT / image['image']) == digest
    assert candidate['upstream_tag'] == '3004.388.13'
    assert candidate['full_content_links_modes_owners_readback_verified']
    assert all(image[k] for k in ['vendor_boot_region_unchanged', 'vendor_descriptor_unchanged', 'vendor_wfi_parameters_unchanged'])
    sources(candidate)
    assert candidate['protected_sha256'] == {n: sha(ROOT / n) for n in candidate['protected_sha256']}
    upstream = read('output/merlin38813_upstream_audit.json')
    stage = inventory(ROOT / candidate['rootfs'])
    original = inventory(ROOT / upstream['rootfs'])
    assert hashlib.sha256(encoded(stage)).hexdigest() == candidate['stage_inventory_sha256']
    assert hashlib.sha256(encoded(original)).hexdigest() == upstream['inventory_sha256']
    changed = sorted(n for n in original if original[n] != stage.get(n))
    assert changed == candidate['upstream_paths_changed']
    assert changed == ['rom/etc/profile', 'sbin/rc', 'usr/sbin/httpd', 'usr/sbin/iptables-restore', 'www/Lang_Hdr.txt', 'www/state.js']
    language_pin, language_data = payload()
    assert (ROOT / candidate['rootfs'] / language_pin['path']).read_bytes() == language_data
    for source, saved in [('sbin/rc', 'usr/libexec/localmod/rc.vendor'), ('usr/sbin/httpd', 'usr/libexec/localmod/httpd')]:
        assert sha(ROOT / upstream['rootfs'] / source) == sha(ROOT / candidate['rootfs'] / saved)
    for name in ['usr/lib/libssl.so.1.1', 'usr/lib/libcrypto.so.1.1', 'usr/lib/libssl.so.3', 'usr/lib/libcrypto.so.3']:
        assert original[name] == stage[name], name
    evidence = {}
    rebuild = read('output/merlin38813_build_inputs.json')
    assert rebuild['status'] == 'P7_ADAPTER_RECOMPILE_BYTE_EQUIVALENCE_PASS'
    assert binding(rebuild) == digest and len(rebuild['programs']) == 6
    sources(rebuild)
    for name, expected in rebuild['programs'].items():
        assert sha(ROOT / candidate['rootfs'] / name) == expected
    evidence['output/merlin38813_build_inputs.json'] = dict(
        sha256=sha(ROOT / 'output/merlin38813_build_inputs.json'), status=rebuild['status'])
    expected = {
        'candidate_runtime': 'LOCAL_NATIVE_MERLIN_CANDIDATE_RUNTIME_PASS',
        'sync_aux': 'LOCAL_SYNC_CENTER_HELPER_CONTRACT_PASS',
        'restore_probe': 'LOCAL_NATIVE_RESTORE_NOFLUSH_CONTRACT_PASS',
        'vpn_generation': 'LOCAL_NATIVE_VPN_GENERATION_PASS',
        'real_tunnel': 'LOCAL_NATIVE_REAL_TUNNEL_PROBE_PASS',
        'plugins_fancyss': 'LOCAL_NATIVE_AUTHENTIC_PLUGINS_PASS',
        'plugins_hnd_upgrade': 'LOCAL_NATIVE_AUTHENTIC_PLUGINS_PASS',
        'plugins_hnd_fresh': 'LOCAL_NATIVE_AUTHENTIC_PLUGINS_PASS',
        'native_coexist_probe': 'FINAL_CANDIDATE_HANDSHAKE_RECOVERY_PASS',
        'native_coexist_smoke': 'LOCAL_COEXIST_SMOKE_PASS',
    }
    for suffix, status in expected.items():
        name = 'output/merlin38813_' + suffix + '_tests.json'; report = read(name)
        assert report['status'] == status, (name, report['status'])
        assert binding(report) == digest, ('Wrong candidate', name)
        sources(report)
        assert report['vm']['sealed_inputs_verified_before_and_after']
        log = name.replace('_tests.json', '.log')
        assert report['log_sha256'] == sha(ROOT / log)
        evidence[name] = dict(sha256=sha(ROOT / name), status=status, executed_candidate_sha256=digest)
    runtime = read('output/merlin38813_candidate_runtime_tests.json')['result']
    required = ['candidate_native_https_idle_preconnect_nonblocking_tls_false',
        'candidate_native_https_idle_preconnect_nonblocking_tls_true',
        'candidate_native_component_loader_version_openssl', 'candidate_native_component_loader_version_openvpn',
        'candidate_rc_center_restart_keeps_native_uu_and_private_guard']
    assert set(required) <= set(runtime['checks'])
    uu = read('output/merlin38813_uu_matrix_tests.json')
    assert uu['status'] == 'LOCAL_NATIVE_UU_STARTUP_MATRIX_PASS'
    assert uu['upstream_image_sha256'] == candidate['upstream_image_sha256']
    sources(uu)
    for observation in uu['observations']:
        assert observation['vm']['sealed_inputs_verified_before_and_after']
        assert len(observation['result']['cases']) == 6
        assert all(row['matches_factory_contract'] for row in observation['result']['cases'])
    persistence = read('output/merlin38813_persistence_tests.json')
    assert binding(persistence) == digest and persistence['complete']
    assert set(persistence['cases']) >= {'kill-tree', 'kill-parent', 'real-ddnsgo', 'no-space'}
    boots = 0
    phases = [persistence['foundation']['result']]
    for case in persistence['cases'].values():
        phases.extend(row for row in case.values() if isinstance(row, dict) and 'report' in row)
    for row in phases:
        assert sha(ROOT / row['report']) == row['sha256']
        report = read(row['report']); assert binding(report) == digest
        sources(report); assert report['vm']['sealed_inputs_verified_before_and_after']
        boots += 1
    for suffix in ['persistence', 'uu_matrix']:
        name = 'output/merlin38813_' + suffix + '_tests.json'
        evidence[name] = dict(sha256=sha(ROOT / name), status=read(name)['status'])
    smoke = read('output/merlin38813_native_coexist_smoke_tests.json')['result']
    assert smoke['duration_seconds'] >= 300 and smoke['unplanned_failures'] == 0 and smoke['data_preserved']
    report = dict(status='LOCAL_NATIVE_P7_38813_GATE_PASS_NOT_DEVICE_ACCEPTED',
        candidate=image, upstream_tag=candidate['upstream_tag'], upstream_commit=candidate['upstream_commit'],
        upstream_paths=len(original), total_paths=len(stage), upstream_paths_changed=changed,
        all_other_native_paths_types_bytes_links_modes_retained=True,
        runtime_checks=len(runtime['checks']), online_lifecycle_checks=len(runtime['online']['checks']),
        persistence_cases=sorted(persistence['cases']), persistence_boots=boots,
        soak=dict(seconds=smoke['duration_seconds'], queries=smoke['queries'], events=smoke['events']),
        evidence=evidence, source_sha256={str(Path(__file__).relative_to(ROOT)): sha(Path(__file__))},
        flash_ready=False, physical_router_flashed=False, target_pid1_boot_tested=False,
        actual_uu_cloud_or_game_acceleration_tested=False, full_hardware_feature_acceptance_complete=False,
        p7_one_hour_soak_executed=False,
        limits=['All candidate-bound dynamic reports are fresh P7 executions; the UU matrix separately compares the retained factory and untouched 388.13 userspaces. P6 hour-long results are historical only',
            'No real router, physical NAND/UBIFS, Wi-Fi, hardware NAT, AiMesh, provider/subscription or actual UU account tested',
            'Selected recovery uses synthetic NVRAM and a dedicated ext4 disk; selected tunnels run under Cortex-A53 Linux6.12, not the target Broadcom4.1 kernel',
            'Fancyss local SOCKS/VLESS coexistence does not validate transparent/global routing or every plugin'])
    target = ROOT / 'output/merlin38813_local_gate.json'
    target.write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'], len(evidence), 'bound reports', flush=True)


if __name__ == '__main__':
    main()
