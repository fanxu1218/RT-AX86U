#!/usr/bin/env python3
"""Bind the native development handoff to its image and local evidence.

This is a local validation gate, never a flash or publication approval. P5
executions remain P5 evidence; only the checked production-file equivalence
connects them to P6. Actual P6 handshake and soak executions are required.
"""
import hashlib
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'build'))
from sealed_vm import inventory, encoded, sha


def read(name):
    return json.loads((ROOT / name).read_text())


def bound_image(report):
    return (report.get('stage', {}).get('image', {}).get('sha256')
            or report.get('image', {}).get('sha256')
            or report.get('candidate', {}).get('sha256')
            or report.get('candidate_sha256'))


def check_sources(report):
    for name, expected in report.get('source_sha256', {}).items():
        assert sha(ROOT / name) == expected, ('stale source evidence', name)


def resources(samples):
    # Contiguous lifetimes prevent merging a recycled numeric PID after a
    # service restart. The producer does not record /proc starttime.
    active, groups = {}, []
    for sample in samples:
        now = sample['elapsed_seconds']
        roles = {n for n, row in sample.items()
                 if isinstance(row, dict) and 'pid' in row}
        for name in set(active) - roles:
            del active[name]
        for name in roles:
            row = sample[name]
            group = active.get(name)
            if group is None or group['pid'] != row['pid']:
                group = dict(name=name, pid=row['pid'], rows=[])
                active[name] = group
                groups.append(group)
            group['rows'].append((now, row))
    result = []
    for group in groups:
        rows = group['rows']
        width = min(3, len(rows))
        values = [r for _, r in rows]
        result.append(dict(name=group['name'], pid=group['pid'],
            observed_seconds=rows[-1][0] - rows[0][0], samples=len(rows),
            executable=values[0]['executable'],
            rss_min_kib=min(r['rss_kib'] for r in values),
            rss_max_kib=max(r['rss_kib'] for r in values),
            end_minus_start_rss_median_kib=(
                statistics.median(r['rss_kib'] for r in values[-width:]) -
                statistics.median(r['rss_kib'] for r in values[:width])),
            fd_min=min(r['fds'] for r in values),
            fd_max=max(r['fds'] for r in values),
            end_minus_start_fd_median=(
                statistics.median(r['fds'] for r in values[-width:]) -
                statistics.median(r['fds'] for r in values[:width]))))
    return result


def main():
    candidate = read('output/merlin38812_native_candidate_tests.json')
    image = candidate['image']
    assert image['sha256'] == sha(ROOT / image['image'])
    assert candidate['full_content_links_modes_owners_readback_verified']
    assert candidate['native_boot_and_kernel_region_retained']
    current = inventory(ROOT / candidate['rootfs'])
    assert hashlib.sha256(encoded(current)).hexdigest() == candidate['stage_inventory_sha256']
    for name, expected in candidate['protected_sha256'].items():
        assert sha(ROOT / name) == expected, ('protected legacy input changed', name)
    check_sources(candidate)

    # Audit every upstream path, including all its model-supported pages,
    # components, libraries, scripts and kernel modules.
    original = inventory(ROOT / 'build/casefs/merlin38812_rootfs')
    upstream = read('build/merlin_sources.json')
    audit = read('output/merlin38812_migration_contracts.json')
    assert upstream['source_tag'] == audit['source_tag'] == '3004.388.12_2'
    assert upstream['source_commit'] == audit['source_commit'] == '433fc608f5fc1689f3d3c3ab5cd2a7d57102260f'
    assert sha(ROOT / upstream['archive']['image']) == upstream['archive']['image_sha256'] == audit['image_sha256']
    content = {n: {k: v for k, v in row.items() if k != 'mode'}
               for n, row in original.items()}
    assert hashlib.sha256(encoded(content)).hexdigest() == audit['upstream_content_tree_sha256']
    metadata = read('upstream/merlin/metadata.json')
    permitted = {'sbin/rc', 'usr/sbin/httpd', 'usr/sbin/iptables-restore',
                 'www/state.js', 'rom/etc/profile'}
    changed = []
    for name, row in original.items():
        expected = dict(row)
        if expected['type'] != 'link':
            expected['mode'] = metadata['/' + name]['mode'] & 0o7777
        if current.get(name) != expected:
            changed.append(name)
    assert set(changed) == permitted, changed
    for native, saved in [('sbin/rc', 'usr/libexec/localmod/rc.vendor'),
                          ('usr/sbin/httpd', 'usr/libexec/localmod/httpd')]:
        assert current[saved]['sha256'] == original[native]['sha256']
    for name, marker in [('www/state.js', '// localmod-software-center-entry:'),
                         ('rom/etc/profile', '# localmod center tools for SSH sessions')]:
        native = (ROOT / 'build/casefs/merlin38812_rootfs' / name).read_bytes()
        augmented = (ROOT / candidate['rootfs'] / name).read_bytes()
        assert augmented.startswith(native) and augmented.count(marker.encode()) == 1

    equivalence = read('output/merlin38812_P5_P6_equivalence.json')
    assert equivalence['current_image'] == image
    prior = read('output/merlin38812_P5_native_candidate_tests.json')
    assert prior['image'] == equivalence['prior_image']
    assert sha(ROOT / prior['image']['image']) == prior['image']['sha256']
    old = inventory(ROOT / prior['rootfs'])
    differing = {n for n in set(old) | set(current) if old.get(n) != current.get(n)}
    assert differing == {'rom/etc/localmod-release.json',
                         'www/Module_FancyssLocalmod.asp', 'www/Module_Localmod.asp'}
    assert len(current) - len(differing) == equivalence['identical_paths'] == 3553
    evidence = {}
    for name, expected in equivalence['prior_frozen_validation_reports'].items():
        assert sha(ROOT / name) == expected
        report = read(name)
        assert bound_image(report) == prior['image']['sha256'], name
        assert 'PASS' in report['status'], name
        check_sources(report)
        evidence[name] = dict(sha256=expected, status=report['status'],
            executed_candidate_sha256=bound_image(report),
            relation='P5 execution; production binaries/scripts identical to P6')

    # Persistence summary binds 24 individually recorded VM phases.
    persistence = read('output/merlin38812_P5_persistence_tests.json')
    assert persistence['all_standard_scenarios_complete'] and persistence['complete']
    leaves = [persistence['foundation']['result']]
    for case in persistence['cases'].values():
        leaves += [r for r in case.values() if isinstance(r, dict) and 'report' in r]
    assert len(leaves) == 24
    for leaf in leaves:
        assert sha(ROOT / leaf['report']) == leaf['sha256']
        report = read(leaf['report'])
        assert bound_image(report) == prior['image']['sha256']
        check_sources(report)

    for label, status in [('probe', 'FINAL_CANDIDATE_HANDSHAKE_RECOVERY_PASS'),
                          ('smoke', 'LOCAL_COEXIST_SMOKE_PASS'),
                          ('60m', 'LOCAL_60_MINUTE_COEXIST_PASS')]:
        name = f'output/merlin38812_native_coexist_{label}_tests.json'
        report = read(name)
        assert report['status'] == status and bound_image(report) == image['sha256']
        assert not report.get('source_overlay_used', False)
        assert report['vm']['host_export_readonly'] and report['vm']['guest_network_devices'] == 0
        assert report['vm']['sealed_inputs_verified_before_and_after']
        assert report['log_sha256'] == sha(ROOT / f'output/merlin38812_native_coexist_{label}.log')
        check_sources(report)
        evidence[name] = dict(sha256=sha(ROOT / name), status=status,
            executed_candidate_sha256=image['sha256'], relation='Actual P6 execution')
    soak = read('output/merlin38812_native_coexist_60m_tests.json')
    result = soak['result']
    assert result['duration_seconds'] >= 3600 and soak['host_elapsed_seconds'] >= 3600
    assert result['unplanned_failures'] == 0 and result['data_preserved']
    assert len(result['event_kinds']) == 16 and all(result['counts'][k] >= 2 for k in result['event_kinds'])
    report = dict(status='LOCAL_NATIVE_P6_VALIDATION_GATE_PASS_NOT_DEVICE_ACCEPTED',
        candidate=image, stage_inventory_sha256=candidate['stage_inventory_sha256'],
        upstream_tag=upstream['source_tag'], upstream_commit=upstream['source_commit'],
        upstream_image_sha256=audit['image_sha256'],
        upstream_paths=len(original), upstream_paths_changed=sorted(changed),
        all_other_native_paths_types_bytes_links_modes_retained=True,
        full_model_supported_native_framework_inherited=True,
        p5_binary_script_equivalence_paths=3553, evidence=evidence,
        source_sha256={name: sha(ROOT / name) for name in [
            'analysis/merlin_vpn_38812/check_local_gate.py',
            'build/sealed_vm.py', 'build/merlin_sources.json',
            'upstream/merlin/metadata.json']},
        persistence_vm_phases=len(leaves),
        soak=dict(seconds=result['duration_seconds'], queries=result['queries'],
                  events=result['events'], counts=result['counts'], samples=len(result['samples'])),
        resources=resources(result['samples']),
        resource_limits=['Contiguous sampled PID lifetimes; no /proc starttime available',
                         'RSS includes program/runtime caches; finite observation is not a leak-freedom proof'],
        flash_ready=False, physical_router_flashed=False, target_pid1_boot_tested=False,
        actual_uu_cloud_or_game_acceleration_tested=False,
        full_hardware_feature_acceptance_complete=False, agent_pushed_or_published=False,
        github_push_owner='user',
        local_scope='Native image integration and bounded isolated tests only',
        excluded_acceptance=['Target Broadcom 4.1 kernel/PID1 boot and firmware updater acceptance',
                             'Physical Wi-Fi/NAT/flash reliability and UU real account/game acceleration',
                             'Every external VPN provider, plugin and transparent/global proxy combination'])
    target = ROOT / 'output/merlin38812_local_gate.json'
    target.write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'], image['sha256'])


if __name__ == '__main__':
    main()
