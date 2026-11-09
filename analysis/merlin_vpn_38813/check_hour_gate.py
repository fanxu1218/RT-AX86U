#!/usr/bin/env python3
"""Validate a fresh, complete P7 hour without rewriting the published gate."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'build'))
from sealed_vm import encoded, inventory, sha

EXPECTED_EVENTS = {'abort', 'partial', 'backend', 'center', 'ddns', 'uu', 'tls',
    'signals', 'dns', 'ssh', 'upnp', 'vpn-client', 'fancy-client', 'nat',
    'proxy-upstream', 'vpn-upstream'}


def read(name):
    return json.loads((ROOT / name).read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-only', action='store_true', help='Recheck the existing hour evidence without running a VM or rewriting artifacts')
    args = parser.parse_args()
    candidate = read('output/merlin38813_native_candidate_tests.json')
    digest = candidate['image']['sha256']
    assert sha(ROOT / candidate['image']['image']) == digest
    assert candidate['upstream_tag'] == '3004.388.13'
    assert hashlib.sha256(encoded(inventory(ROOT / candidate['rootfs']))).hexdigest() == candidate['stage_inventory_sha256']
    for name, expected in candidate['protected_sha256'].items():
        assert sha(ROOT / name) == expected, ('Protected build input changed', name)
    for name, expected in candidate['source_sha256'].items():
        assert sha(ROOT / name) == expected, ('Candidate source changed', name)
    publication = read('output/merlin38813_release_delivery.json')
    assert publication['main_firmware_sha256'] == digest and publication['prerelease']
    original_gate_name = 'output/merlin38813_local_gate.json'
    gate_digest = sha(ROOT / original_gate_name)
    assert publication['assets']['merlin38813_local_gate.json']['sha256'] == gate_digest
    original_gate = read(original_gate_name)
    assert original_gate['candidate']['sha256'] == digest and not original_gate['flash_ready']

    name = 'output/merlin38813_native_coexist_60m_tests.json'
    hour = read(name); result = hour['result']
    assert hour['status'] == 'LOCAL_60_MINUTE_COEXIST_PASS'
    assert hour['candidate_sha256'] == digest
    assert hour['requested_seconds'] == result['requested_seconds'] == 3600
    assert hour['host_elapsed_seconds'] >= 3600 and result['duration_seconds'] >= 3600
    assert result['queries'] >= 360 and result['unplanned_failures'] == 0 and result['data_preserved']
    assert not result['actual_fancyss_global_proxy_enabled']
    assert set(result['event_kinds']) == EXPECTED_EVENTS
    assert result['events'] >= 32 and all(result['counts'].get(event, 0) >= 2 for event in EXPECTED_EVENTS)
    assert len(result['samples']) >= 100
    checks = result['service_checks']
    required_checks = {'proxy_queries', 'dns_queries', 'ssh_queries', 'tun_traffic',
        'upnp_cycles', 'curl_wget_https_pairs', 'core_page_queries'}
    assert required_checks <= set(checks) and all(checks[key] > 0 for key in required_checks)
    for name2, expected in hour['source_sha256'].items():
        assert sha(ROOT / name2) == expected, ('Hour source changed during execution', name2)
    for name2, expected in hour['baseline_preserved_sha256'].items():
        assert sha(ROOT / name2) == expected, ('Hour immutable input changed', name2)
    log = 'output/merlin38813_native_coexist_60m.log'
    assert hour['log_sha256'] == sha(ROOT / log)
    vm = hour['vm']
    assert vm['host_export_readonly'] and vm['guest_network_devices'] == 0
    assert vm['sealed_inputs_verified_before_and_after']
    assert vm['inputs']['build/casefs/rootfs'] == candidate['stage_inventory_sha256']
    assert hour['maintenance_windows'] and all(w['queries'] > 0 and
        (w['unavailable'] == 0 or w['name'] in {'center_restart', 'ddns_restart'})
        for w in hour['maintenance_windows'])
    rows = result['samples']
    for before, after in zip(rows, rows[1:]):
        assert before['elapsed_seconds'] <= after['elapsed_seconds']
        assert before['queries'] <= after['queries'] and before['events'] <= after['events']
    assert rows[-1]['elapsed_seconds'] >= 3600

    # Preserve only the small generated inputs needed to audit transformations.
    expected_members = {name: digest2 for name, digest2 in vm['inputs'].items()
        if name.startswith('build/merlin38813-native-soak/') and Path(name).suffix in {'.py', '.go', '.sh', '.c', '.h', '.json'}}
    assert expected_members and len(expected_members) < 100
    archive = ROOT / 'output/merlin38813_hour_generated_inputs.tar.gz'
    if not archive.exists():
        assert not args.verify_only, 'Completed generated-input archive is required for a read-only evidence check'
        for relative, expected in expected_members.items():
            assert sha(ROOT / relative) == expected, ('Generated input no longer matches VM', relative)
        with tarfile.open(archive, 'w:gz', dereference=False) as stream:
            for relative in sorted(expected_members): stream.add(ROOT / relative, arcname=relative, recursive=False)
    members = {}
    with tarfile.open(archive, 'r:gz') as stream:
        assert set(stream.getnames()) == set(expected_members)
        for relative, expected in expected_members.items():
            member = stream.getmember(relative)
            assert member.isfile() and member.size < 1024 * 1024
            assert hashlib.sha256(stream.extractfile(relative).read()).hexdigest() == expected
            members[relative] = dict(bytes=member.size, sha256=expected)

    # Group contiguous process lifetimes rather than merging recycled PIDs or
    # comparing memory before and after deliberate service restarts.
    helper = ROOT / 'analysis/merlin_vpn_38812/check_local_gate.py'
    spec = importlib.util.spec_from_file_location('hour_resource_summary', helper)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    resources = sorted(module.resources(rows), key=lambda row: (row['name'], row['pid'], row['observed_seconds'], row['samples']))
    report = dict(status='P7_ONE_HOUR_LOCAL_VALIDATION_PASS_NOT_DEVICE_ACCEPTED',
        candidate=candidate['image'], upstream_tag=candidate['upstream_tag'],
        upstream_commit=candidate['upstream_commit'], published_source_commit=publication['source_commit'],
        existing_release_url=publication['url'], original_published_gate_sha256=gate_digest,
        original_published_gate_unchanged=True,
        hour_report=dict(path=name, sha256=sha(ROOT / name), log_sha256=sha(ROOT / log)),
        measured_seconds=result['duration_seconds'], host_elapsed_seconds=hour['host_elapsed_seconds'],
        started_utc=result['started_utc'], finished_utc=result['finished_utc'],
        queries=result['queries'], events=result['events'],
        event_counts={event: result['counts'][event] for event in sorted(EXPECTED_EVENTS)},
        query_counts={name2: count for name2, count in result['counts'].items() if name2 not in EXPECTED_EVENTS},
        service_checks=checks, resource_sample_count=len(rows), resource_lifetimes=resources,
        data_preserved=True, unexpected_failures=0,
        generated_inputs_archive=dict(path=str(archive.relative_to(ROOT)), bytes=archive.stat().st_size,
            sha256=sha(archive), files=members),
        source_sha256={str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__).resolve(), helper]},
        p7_one_hour_soak_executed=True, flash_ready=False, physical_router_flashed=False,
        target_pid1_boot_tested=False, real_uu_cloud_account_or_game_acceleration_tested=False,
        limits=['Fresh complete P7 hour; the published five-minute gate remains an immutable historical artifact',
            'No physical router or target Broadcom4.1 kernel/PID1; TUN tests use Cortex-A53/Linux6.12 system emulation',
            'UU native startup/download/checksum uses an owned monitor, not a real UU account or game acceleration',
            'Actual Fancyss SOCKS/VLESS and VPN traffic use owned endpoints; subscriptions, transparent/global routing and WAN providers remain unverified',
            'RSS/FD observations are per process lifetime and may include runtime/emulator overhead; one bounded hour does not prove multi-day stability or absence of memory leaks'])
    target = ROOT / 'output/merlin38813_hour_gate.json'
    if args.verify_only:
        assert target.is_file() and json.loads(target.read_text()) == report, 'Existing hour evidence or its bindings changed'
        print('P7_EXISTING_HOUR_EVIDENCE_REUSE_PASS_NO_VM_NO_REWRITE', report['queries'], 'queries')
    else:
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(report['status'], report['measured_seconds'], 'seconds', report['queries'], 'queries', report['events'], 'events')


if __name__ == '__main__': main()
