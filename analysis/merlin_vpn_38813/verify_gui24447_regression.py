#!/usr/bin/env python3
"""Verify fresh GUI24447 executions, keeping original P7 release evidence intact."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PREFIX = 'merlin38813gui24447'
PROFILE = ROOT / 'analysis/merlin_vpn_38813gui24447'
sys.path.insert(0, str(ROOT / 'build'))
sys.path.insert(0, str(HERE))
from sealed_vm import sha, inventory, encoded
from audit_gui24447 import read_image, write_report
from build_gui24447 import inventory as full_inventory

EVENTS = {'abort','partial','backend','center','ddns','uu','tls','signals','dns','ssh',
          'upnp','vpn-client','fancy-client','nat','proxy-upstream','vpn-upstream'}
CASES = {'download','checkpoint','kill-parent','kill-tree','offline','fresh','real-ddnsgo',
         'before-commit','after-commit','committed-cleanup','no-space'}


def read(name): return json.loads((ROOT / name).read_text())


def binding(report):
    return (report.get('candidate_sha256') or report.get('executed_candidate_sha256')
        or report.get('stage', {}).get('image', {}).get('sha256')
        or report.get('candidate', {}).get('sha256') or report.get('image', {}).get('sha256'))


def sources(report):
    for name, expected in report.get('source_sha256', {}).items():
        assert sha(ROOT / name) == expected, ('Changed source', name)
    for name, expected in report.get('baseline_preserved_sha256', {}).items():
        assert sha(ROOT / name) == expected, ('Changed immutable input', name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-only', action='store_true', help='Check existing evidence; no VM, reconstruction or evidence rewrites')
    args = parser.parse_args()
    original = read('output/merlin38813_gui24447_candidate.json')
    digest = original['sha256']; assert sha(ROOT / original['image']) == digest
    stage = ROOT / original['stage']
    raw, _, _, _ = read_image(ROOT / original['image'], hardlinks=True)
    assert full_inventory(stage) == raw
    sources(original)
    for name, expected in original['protected_sha256'].items(): assert sha(ROOT / name) == expected
    current = read('output/' + PREFIX + '_native_candidate_tests.json')
    assert current['image']['sha256'] == digest and current['rootfs'] == original['stage']
    assert hashlib.sha256(encoded(inventory(stage))).hexdigest() == current['stage_inventory_sha256']
    sources(current)
    evidence, reports = {}, []
    expected = {
        'candidate_runtime':'LOCAL_NATIVE_MERLIN_CANDIDATE_RUNTIME_PASS',
        'sync_aux':'LOCAL_SYNC_CENTER_HELPER_CONTRACT_PASS',
        'restore_probe':'LOCAL_NATIVE_RESTORE_NOFLUSH_CONTRACT_PASS',
        'vpn_generation':'LOCAL_NATIVE_VPN_GENERATION_PASS',
        'real_tunnel':'LOCAL_NATIVE_REAL_TUNNEL_PROBE_PASS',
        'plugins_fancyss':'LOCAL_NATIVE_AUTHENTIC_PLUGINS_PASS',
        'plugins_hnd_upgrade':'LOCAL_NATIVE_AUTHENTIC_PLUGINS_PASS',
        'plugins_hnd_fresh':'LOCAL_NATIVE_AUTHENTIC_PLUGINS_PASS',
        'native_coexist_probe':'FINAL_CANDIDATE_HANDSHAKE_RECOVERY_PASS',
        'native_coexist_smoke':'LOCAL_COEXIST_SMOKE_PASS',
        'native_coexist_60m':'LOCAL_60_MINUTE_COEXIST_PASS'}
    def retain(name, report):
        sources(report); evidence[name] = dict(sha256=sha(ROOT / name), status=report['status'])
        reports.append(report)
    for suffix, status in expected.items():
        name = 'output/' + PREFIX + '_' + suffix + '_tests.json'; report = read(name)
        assert report['status'] == status and binding(report) == digest, name
        vm = report['vm']; assert vm['sealed_inputs_verified_before_and_after'] and vm['guest_network_devices'] == 0
        for tool in ['LinuxBuilder','linux-Image','linux-initramfs.gz']:
            assert vm['inputs']['build/tools/'+tool] == sha(ROOT/'build/tools'/tool)
        assert report['log_sha256'] == sha(ROOT / name.replace('_tests.json', '.log'))
        retain(name, report)
    runtime = read('output/' + PREFIX + '_candidate_runtime_tests.json')['result']
    assert len(runtime['checks']) == 36 and len(runtime['online']['checks']) == 7
    assert 'candidate_native_https_renders_utf8_language_menu_from_backported_data' in runtime['checks']
    name = 'output/' + PREFIX + '_build_inputs.json'; compiled = read(name)
    assert binding(compiled) == digest and len(compiled['programs']) == 6
    for name2, expected_hash in compiled['programs'].items(): assert sha(stage / name2) == expected_hash
    retain(name, compiled)
    name = 'output/' + PREFIX + '_uu_matrix_tests.json'; uu = read(name)
    assert binding(uu) == digest
    selected = [o for o in uu['observations'] if o['result']['base'] == 'merlin']; assert len(selected) == 1
    assert len(selected[0]['result']['cases']) == 6 and all(x['matches_factory_contract'] for x in selected[0]['result']['cases'])
    assert selected[0]['vm']['sealed_inputs_verified_before_and_after']
    assert selected[0]['vm']['inputs']['build/' + PREFIX + '-uu-matrix-merlin-root'] == current['stage_inventory_sha256']
    retain(name, uu)
    # The archived r8 observation is retained verbatim as a historical reference.
    # It is not the GUI24447 candidate and does not determine its UU gate.
    factory_reference = [dict(base=o['result']['base'], cases=len(o['result']['cases']),
        contract_matches=sum(x['matches_factory_contract'] for x in o['result']['cases']))
        for o in uu['observations'] if o['result']['base'] != 'merlin']
    name = 'output/' + PREFIX + '_persistence_tests.json'; persistence = read(name)
    assert binding(persistence) == digest and persistence['complete'] and persistence['all_standard_scenarios_complete']
    assert set(persistence['cases']) == CASES
    phases = [persistence['foundation']['result']]
    for case in persistence['cases'].values(): phases.extend(x for x in case.values() if isinstance(x, dict) and 'report' in x)
    assert len(phases) == 24
    for row in phases:
        assert sha(ROOT / row['report']) == row['sha256']
        report = read(row['report']); assert binding(report) == digest
        assert report['vm']['sealed_inputs_verified_before_and_after']
        retain(row['report'], report)
    retain(name, persistence)
    name = 'output/' + PREFIX + '_frontend_tests.json'; frontend = read(name)
    assert frontend['candidate_sha256'] == digest and len(frontend['checks']) == 7 and all(frontend['checks'].values())
    assert frontend['source_sha256'] == sha(ROOT / ('build/' + PREFIX + '-frontend.mjs'))
    assert frontend['frontend_sha256'] == sha(stage / 'rom/etc/koolshare/res/soft-v19/assets/index-DhXhkv_Y.js')
    evidence[name] = dict(sha256=sha(ROOT/name), status=frontend['status'])
    hour = read('output/' + PREFIX + '_native_coexist_60m_tests.json'); result = hour['result']
    assert hour['requested_seconds'] == result['requested_seconds'] == 3600
    assert hour['host_elapsed_seconds'] >= 3600 and result['duration_seconds'] >= 3600
    assert result['unplanned_failures'] == 0 and result['data_preserved'] and result['queries'] >= 360
    assert set(result['event_kinds']) == EVENTS and all(result['counts'].get(x,0) >= 2 for x in EVENTS)
    assert len(result['samples']) >= 100 and not result['actual_fancyss_global_proxy_enabled']
    for key in ['proxy_queries','dns_queries','ssh_queries','tun_traffic','upnp_cycles','curl_wget_https_pairs','core_page_queries']:
        assert result['service_checks'][key] > 0
    assert all(w['queries'] > 0 and (w['unavailable'] == 0 or w['name'] in {'center_restart','ddns_restart'})
               for w in hour['maintenance_windows'])
    lineage = read('output/' + PREFIX + '_lineage.json')
    for name2, row in lineage['files'].items():
        assert sha(ROOT / row['source']) == row['source_sha256'] and sha(ROOT / name2) == row['generated_sha256']
    for name2, expected_hash in lineage['preserved_sha256'].items(): assert sha(ROOT / name2) == expected_hash
    assert lineage['generator_sha256'] == sha(HERE / 'regress_gui24447.py')
    recovered = read('output/' + PREFIX + '_inputs_verification.json')
    assert len(recovered['packages']) == 6 and all(p['all_payload_files_modes_versions_and_sizes_identical'] for p in recovered['packages'])
    assert recovered['fixture_manifest_sha256'] == sha(ROOT/'build/real_plugin_inputs.json')
    assert recovered['source_sha256'] == sha(HERE/'rehydrate_gui24447.py')
    final_path = 'output/' + PREFIX + '_full_gate.json'
    if args.verify_only:
        previous = read(final_path); archive_receipt = previous['runtime_source_archive']
        assert sha(ROOT/archive_receipt['path']) == archive_receipt['sha256']
        assert sha(ROOT/archive_receipt['manifest']) == archive_receipt['manifest_sha256']
        manifest = read(archive_receipt['manifest']); assert manifest['candidate_sha256'] == digest
        with tarfile.open(ROOT/archive_receipt['path'], 'r:gz') as stream:
            assert set(stream.getnames()) == set(manifest['files'])
            for name2, row in manifest['files'].items():
                member = stream.getmember(name2); assert member.isfile() and member.size == row['bytes']
                assert hashlib.sha256(stream.extractfile(member).read()).hexdigest() == row['sha256']
    else:
        from archive_gui24447_runtime import archive
        archive_receipt = archive(reports, persistence, digest)
    report = dict(schema=1, status='GUI24447_FULL_LOCAL_RUNTIME_REGRESSION_PASS_NOT_DEVICE_ACCEPTED',
        candidate_image=original['image'], candidate_sha256=digest,
        test_selector_manifest=dict(path='output/'+PREFIX+'_native_candidate_tests.json',
            sha256=sha(ROOT/('output/'+PREFIX+'_native_candidate_tests.json')),
            actual_build_receipt='output/merlin38813_gui24447_candidate.json',
            inherited_parent_reference_fields=['metadata','build_vm','overlay_donor_sha256'],
            note='The selector chooses the patched image/rootfs; inherited P7 ancestry fields are historical references. GUI24447 build/readback facts are in the separate actual build receipt.'),
        native_checks=len(runtime['checks']), online_checks=len(runtime['online']['checks']),
        compiled_adapters=6, candidate_uu_cases=6, frontend_checks=7,
        persistence_cases=sorted(CASES), persistence_boots=len(phases),
        measured_hour_seconds=result['duration_seconds'], host_elapsed_seconds=hour['host_elapsed_seconds'],
        hour_queries=result['queries'], hour_events=result['events'], resource_samples=len(result['samples']),
        event_counts={x:result['counts'][x] for x in sorted(EVENTS)}, service_checks=result['service_checks'],
        unplanned_failures=0, data_preserved=True, evidence=evidence,
        legacy_factory_reference=factory_reference,
        runtime_source_archive=archive_receipt,
        source_sha256={str(Path(__file__).relative_to(ROOT)):sha(Path(__file__)),
            'analysis/merlin_vpn_38813/archive_gui24447_runtime.py':sha(HERE/'archive_gui24447_runtime.py')},
        original_p7_evidence_unchanged=True, firmware_bytes_unchanged_during_regression=True,
        flash_ready=False, physical_router_accessed=False, physical_router_flashed=False,
        target_pid1_boot_tested=False, actual_uu_cloud_account_or_game_tested=False,
        real_wan_wifi_nat_aimesh_tested=False, browser_visual_accepted=False, published=False,
        limits=['All runtime gates concern the exact GUI24447 candidate, under isolated Linux 6.12.115/QEMU fixtures.',
            'The archived r8 UU observation is a separate reference, not a pass/fail result for this candidate; its raw differences are retained.',
            'The old-core upgrade fixture is the actual archived r8 1.9.50 core, distinct from the historical r9 fixture.',
            'Plugin payloads retain all historical file bytes/modes/versions; changed archive containers and DDNSTO recovery are documented.',
            'No target Broadcom4.1/PID1, physical NAND/UBIFS, Wi-Fi/NAT/AiMesh, real providers/UU, or live browser/device acceptance.',
            'One bounded hour and per-process RSS/FD observations cannot prove multi-day stability or absence of leaks.'])
    if args.verify_only:
        assert report == previous, 'Completed gate differs from its current evidence bindings'
        print('GUI24447_EXISTING_FULL_EVIDENCE_VERIFIED_NO_VM_NO_EVIDENCE_REWRITE', len(evidence), 'bound reports')
    else:
        write_report(ROOT / final_path, report)
        print(report['status'], len(evidence), 'bound reports;', result['duration_seconds'], 'seconds')


if __name__ == '__main__': main()
