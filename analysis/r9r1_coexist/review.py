#!/usr/bin/env python3
"""Review a completed coexistence run without joining different process lifetimes."""
import hashlib
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def digest(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def main():
    source = ROOT / 'output/r9r2_coexist_60m_tests.json'
    r = json.loads(source.read_text())
    assert r['status'] == 'LOCAL_60_MINUTE_COEXIST_PASS'
    assert r['candidate_sha256'] == digest(ROOT / r['candidate_image'])
    assert r['result']['duration_seconds'] >= 3600 and r['result']['unplanned_failures'] == 0
    bridge = digest(ROOT / 'build/casefs/roundtrip/usr/lib/localmod/httpd_bridge.so')
    assert r['vm']['inputs']['build/httpd_bridge.so'] == bridge
    assert r['vm']['sealed_inputs_verified_before_and_after']
    grouped, last = {}, {}
    for sample in r['result']['samples']:
        for name, row in sample.items():
            if not isinstance(row, dict) or 'pid' not in row:
                continue
            previous = last.get(name)
            generation = 1 if previous is None else previous[2]
            if previous is not None and previous[:2] != (row['pid'], row['executable']):
                generation += 1
            last[name] = (row['pid'], row['executable'], generation)
            grouped.setdefault((name, generation), []).append(dict(row, elapsed_seconds=sample['elapsed_seconds']))
    lifetimes = []
    for (name, generation), rows in sorted(grouped.items()):
        rows.sort(key=lambda x: x['elapsed_seconds'])
        pid = rows[0]['pid']
        assert all(x['pid'] == pid for x in rows)
        assert len({x['executable'] for x in rows}) == 1
        rss = [x['rss_kib'] for x in rows]
        fds = [x['fds'] for x in rows]
        head, tail = rows[:5], rows[-5:]
        # A sustained FD step is a review signal, not a diagnosis of a leak.
        fd_step = len(rows) >= 15 and min(x['fds'] for x in tail) > max(x['fds'] for x in head)
        lifetimes.append(dict(name=name, pid=pid, lifetime_index=generation, executable=rows[0]['executable'], samples=len(rows),
            first_seconds=rows[0]['elapsed_seconds'], last_seconds=rows[-1]['elapsed_seconds'],
            observed_seconds=rows[-1]['elapsed_seconds']-rows[0]['elapsed_seconds'],
            fd_min=min(fds), fd_max=max(fds), fd_first=fds[0], fd_last=fds[-1],
            fd_sustained_step_review=fd_step, rss_min_kib=min(rss), rss_max_kib=max(rss),
            rss_first_five_median_kib=statistics.median(x['rss_kib'] for x in head),
            rss_last_five_median_kib=statistics.median(x['rss_kib'] for x in tail),
            rss_median_change_kib=statistics.median(x['rss_kib'] for x in tail)-statistics.median(x['rss_kib'] for x in head)))
    roles = []
    for name in sorted({x['name'] for x in lifetimes}):
        rows = [x for x in lifetimes if x['name'] == name]
        longest = max(rows, key=lambda x: x['observed_seconds'])
        roles.append(dict(name=name, pids=len({x['pid'] for x in rows}), lifetimes=len(rows), samples=sum(x['samples'] for x in rows),
            fd_min=min(x['fd_min'] for x in rows), fd_max=max(x['fd_max'] for x in rows),
            max_within_pid_fd_span=max(x['fd_max']-x['fd_min'] for x in rows),
            sustained_fd_step_pids=[x['pid'] for x in rows if x['fd_sustained_step_review']],
            rss_min_kib=min(x['rss_min_kib'] for x in rows), rss_max_kib=max(x['rss_max_kib'] for x in rows),
            longest_observed_pid=longest['pid'], longest_observed_seconds=longest['observed_seconds'],
            longest_lifetime_index=longest['lifetime_index'],
            longest_pid_rss_median_change_kib=longest['rss_median_change_kib']))
    windows = r['maintenance_windows']
    assert all(x['unavailable'] == 0 or x['name'] in ['center_restart','ddns_restart'] for x in windows)
    own = Path(__file__).resolve()
    report = dict(status='LOCAL_SOAK_RESOURCE_REVIEW_COMPLETED', candidate_sha256=r['candidate_sha256'],
        measured_seconds=r['result']['duration_seconds'], queries=r['result']['queries'],
        events=r['result']['events'], sample_count=len(r['result']['samples']),
        validated_runtime_bridge_sha256=bridge, roles=roles, lifetimes=lifetimes,
        maintenance_windows=windows, service_checks=r['result']['service_checks'],
        source_sha256={str(source.relative_to(ROOT)):digest(source), str(own.relative_to(ROOT)):digest(own)},
        limits=['Lifetimes split on sampled PID/executable transitions, including when a PID returns after another PID; very short restarts between samples may be missed',
                'RSS includes shared pages, native runtime caches and QEMU-user overhead when executable is qemu-arm',
                'This workload has scheduled restarts and no dedicated idle control; RSS deltas alone do not establish a leak',
                'No sustained FD step is not proof of no descriptor leak, and one hour is not multi-day device acceptance'])
    out = ROOT / 'output/r9r2_coexist_resources_tests.json'
    out.write_text(json.dumps(report, indent=2)+'\n')
    print('Resource review:',len(lifetimes),'lifetimes,',len(roles),'roles,',len(r['result']['samples']),'samples')
    for x in roles:
        print(x['name'], 'FD',str(x['fd_min'])+'..'+str(x['fd_max']),
            'within_pid_span',x['max_within_pid_fd_span'],'RSS_KiB',str(x['rss_min_kib'])+'..'+str(x['rss_max_kib']),
            'sustained_fd_step_pids',x['sustained_fd_step_pids'])

if __name__ == '__main__':
    main()
