#!/usr/bin/env python3
"""Package the verified native development candidate for a local handoff.

Never changes the legacy production selection, flashes a router, creates a
commit, pushes GitHub, or publishes the planned release URL.
"""
import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    gate_path = ROOT / 'output/merlin38812_local_gate.json'
    gate = json.loads(gate_path.read_text())
    assert gate['status'] == 'LOCAL_NATIVE_P6_VALIDATION_GATE_PASS_NOT_DEVICE_ACCEPTED'
    assert not gate['flash_ready'] and not gate['physical_router_flashed']
    for name, expected in gate['source_sha256'].items():
        assert sha(ROOT / name) == expected
    snapshot = json.loads((ROOT / 'output/merlin38812_source_snapshot.json').read_text())
    assert snapshot['candidate_sha256'] == gate['candidate']['sha256']
    assert sha(ROOT / snapshot['archive']) == snapshot['sha256']
    release = json.loads((ROOT / 'analysis/merlin_vpn_38812/release.json').read_text())
    assert release['revision'] == 'P6' and not release['published'] and not release['flash_ready']
    revision = release['revision']
    image = gate['candidate']
    assert sha(ROOT / image['image']) == image['sha256']
    names = {image['image'], snapshot['archive'],
        'output/merlin38812_local_gate.json', 'output/merlin38812_source_snapshot.json',
        'output/merlin38812_P5_P6_equivalence.json',
        'output/merlin38812_native_candidate_tests.json',
        'output/merlin38812_migration_state.json',
        'output/388.12_2原生框架进度.md', 'output/388.12_2本地交付与手动推送.md',
        'analysis/merlin_vpn_38812/release.json'}
    for name in gate['evidence']:
        names.add(name)
        # Frozen P5 report names differ from their original log name. Store
        # only the named logs/receipts when they exist and match the evidence.
        report = json.loads((ROOT / name).read_text())
        log = ROOT / name.replace('_tests.json', '.log')
        if 'log_sha256' in report:
            if not log.exists() and '/merlin38812_P5_' in str(log):
                log = Path(str(log).replace('/merlin38812_P5_', '/merlin38812_'))
            assert log.is_file() and sha(log) == report['log_sha256'], name
            names.add(log.relative_to(ROOT).as_posix())
            receipt = log.with_suffix(log.suffix + '.vm.json')
            if receipt.is_file():
                names.add(receipt.relative_to(ROOT).as_posix())
    persistence = json.loads((ROOT / 'output/merlin38812_P5_persistence_tests.json').read_text())
    leaves = [persistence['foundation']['result']]
    for case in persistence['cases'].values():
        leaves += [r for r in case.values() if isinstance(r, dict) and 'report' in r]
    for leaf in leaves:
        assert sha(ROOT / leaf['report']) == leaf['sha256']
        names.add(leaf['report'])
    fancy = json.loads((ROOT / 'build/fancyss_inputs.json').read_text())
    current = next(p for p in fancy['packages'] if p['phase'] == 'current')
    assert sha(ROOT / current['adapted_path']) == current['adapted_sha256']
    names.add(current['adapted_path'])
    files = {n: dict(bytes=(ROOT / n).stat().st_size, sha256=sha(ROOT / n))
             for n in sorted(names)}
    manifest = dict(schema=1, status='LOCAL_DEVELOPMENT_HANDOFF_NOT_DEVICE_ACCEPTED',
        revision=revision, base='3004.388.12_2', model='RT-AX86U',
        candidate_sha256=image['sha256'], source_snapshot_sha256=snapshot['sha256'],
        source_snapshot_contains_uncommitted_device_profile_dependencies=True,
        local_gate_sha256=sha(gate_path), files=files,
        flash_ready=False, agent_pushed_or_published=False, github_push_owner='user',
        planned_release_tag=release['release_tag'], planned_release_published=False,
        excluded=gate['excluded_acceptance'])
    archive = ROOT / f'output/merlin38812-native-{revision}-local-handoff.tar.gz'
    assert not archive.exists(), 'Keep the existing handoff for review'
    with archive.open('xb') as output, gzip.GzipFile(filename='', mode='wb',
            fileobj=output, mtime=0, compresslevel=1) as zipped, tarfile.open(
            fileobj=zipped, mode='w|') as tar:
        for name, record in files.items():
            info = tarfile.TarInfo(name)
            info.size = record['bytes']
            info.mode = 0o644
            with (ROOT / name).open('rb') as source:
                tar.addfile(info, source)
        data = (json.dumps(manifest, indent=2) + '\n').encode()
        info = tarfile.TarInfo('LOCAL_HANDOFF.json')
        info.size = len(data)
        info.mode = 0o644
        tar.addfile(info, io.BytesIO(data))
    with tarfile.open(archive, 'r:gz') as tar:
        assert len(tar.getmembers()) == len(files) + 1
        for name, record in files.items():
            assert hashlib.sha256(tar.extractfile(name).read()).hexdigest() == record['sha256']
            assert sha(ROOT / name) == record['sha256']
    digest = sha(archive)
    archive.with_suffix(archive.suffix + '.sha256').write_text(digest + '  ' + archive.name + '\n')
    archive.with_suffix('.manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    result = dict(status='LOCAL_NATIVE_HANDOFF_SAVED_NOT_DEVICE_ACCEPTED',
        archive=archive.relative_to(ROOT).as_posix(), bytes=archive.stat().st_size,
        sha256=digest, entries=len(files), candidate=image,
        source_snapshot=snapshot, local_gate_sha256=sha(gate_path),
        git_commit_created=False, agent_pushed_or_published=False,
        github_push_owner='user', flash_ready=False)
    (ROOT / 'output/merlin38812_native_local_delivery.json').write_text(
        json.dumps(result, indent=2) + '\n')
    print(result['status'], archive.name, digest)


if __name__ == '__main__':
    main()
