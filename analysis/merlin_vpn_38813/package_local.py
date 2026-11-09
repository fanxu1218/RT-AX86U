#!/usr/bin/env python3
"""Package the locally verified P7 candidate without publishing or flashing."""
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def pack(path, names):
    assert not path.exists(), 'Preserve the existing local handoff'
    rows = {name: dict(bytes=(ROOT / name).stat().st_size, sha256=sha(ROOT / name)) for name in sorted(names)}
    with tarfile.open(path, 'w:gz', dereference=False) as archive:
        for name in rows:
            archive.add(ROOT / name, arcname=name, recursive=False)
    with tarfile.open(path, 'r:gz') as archive:
        assert set(archive.getnames()) == set(rows)
        for name, row in rows.items():
            member = archive.getmember(name)
            assert member.isfile() and member.size == row['bytes']
            assert hashlib.sha256(archive.extractfile(member).read()).hexdigest() == row['sha256']
    return rows


def main():
    gate_path = ROOT / 'output/merlin38813_local_gate.json'
    gate = json.loads(gate_path.read_text())
    assert gate['status'] == 'LOCAL_NATIVE_P7_38813_GATE_PASS_NOT_DEVICE_ACCEPTED'
    assert not gate['flash_ready'] and not gate['physical_router_flashed']
    image = gate['candidate']; assert sha(ROOT / image['image']) == image['sha256']
    fancyss = 'sources/realplugins/fancyss_hnd_v8_full_3.5.29_localmod2.tar.gz'
    assert sha(ROOT / fancyss) == 'b45d1294022b7914f6ffa6ae67c688e4870ef7aa07f3556657feec37a034d592'
    visible = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard'], cwd=ROOT, text=True).splitlines()
    extensions = {'.py', '.go', '.c', '.h', '.sh', '.json', '.md', '.txt', '.yml', '.yaml'}
    prefixes = ('build/', 'sources/localmod/', 'analysis/merlin_vpn_38812/',
        'analysis/merlin_vpn_38813/', 'analysis/r9r1_coexist/', '.github/')
    sources = {n for n in visible if n.startswith(prefixes) and Path(n).suffix in extensions and (ROOT / n).is_file()}
    sources.update(n for n in visible if n.startswith('output/merlin38813_') and (ROOT / n).is_file())
    guide = 'output/388.13升级与本地验证.md'
    sources.update(['README.md', '.gitignore', guide])
    archive = ROOT / 'output/merlin38813-P7-sources.tar.gz'
    manifest = pack(archive, sources)
    (ROOT / 'output/merlin38813-P7-sources.manifest.json').write_text(json.dumps(dict(
        schema=1, source_archive_sha256=sha(archive), files=manifest,
        external_inputs=['Pinned 388.13 upstream image/ZIP', 'Verified P6 donor image/tree',
            'Pinned toolchain/LinuxBuilder/kernel and authentic plugin packages'],
        no_router_data_or_generated_credentials=True), indent=2) + '\n')
    assets = [image['image'], fancyss, str(archive.relative_to(ROOT)),
        'output/merlin38813-P7-sources.manifest.json', 'output/merlin38813_local_gate.json', guide]
    sums = ROOT / 'output/merlin38813-P7-SHA256SUMS'
    sums.write_text(''.join(sha(ROOT / name) + '  ' + name + '\n' for name in assets))
    assets.append(str(sums.relative_to(ROOT)))
    handoff = ROOT / 'output/merlin38813-P7-local-handoff.tar.gz'
    handoff_manifest = pack(handoff, assets)
    report = dict(status='LOCAL_P7_38813_HANDOFF_COMPLETE_NOT_DEVICE_ACCEPTED',
        candidate=image, handoff=str(handoff.relative_to(ROOT)), handoff_sha256=sha(handoff),
        source_archive=str(archive.relative_to(ROOT)), source_archive_sha256=sha(archive),
        source_files=len(sources), assets=handoff_manifest,
        source_sha256={'analysis/merlin_vpn_38813/package_local.py': sha(Path(__file__))},
        flash_ready=False, physical_router_flashed=False, actual_uu_acceleration_tested=False,
        github_pushed_by_packager=False, github_release_published=False,
        source_push_status='Verify the Git remote separately; this packager only writes local artifacts')
    (ROOT / 'output/merlin38813_local_delivery.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'], len(sources), 'source/evidence files', flush=True)


if __name__ == '__main__':
    main()
