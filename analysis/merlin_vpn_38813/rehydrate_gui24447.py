#!/usr/bin/env python3
"""Recover test packages while pinning every historical payload byte and mode."""
import argparse
import copy
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'build'))
from prepare_real_plugins import inspect, source_package

DDNSTO_COMMIT = 'd86e8bd3ae524bf557d0e95b070ecc1ccf3cda1f'


def sha(data): return hashlib.sha256(data).hexdigest()


def fetch(url, path):
    subprocess.run(['curl', '-L', '--fail', '--retry', '1', '--max-time', '100', '-sS',
                    url, '-o', str(path)], check=True)
    return path.read_bytes()


def verify(blob, package):
    actual = inspect(blob, package['module'])
    for key in ['files', 'modes', 'internal_version', 'expanded_bytes']:
        assert actual[key] == package[key], (package['path'], key)
    return actual


def recover(package, path):
    blob = fetch(package['source_url'], path.with_suffix('.download'))
    if package['packaging'] == 'unchanged-upstream-source-tree':
        blob = source_package(blob, package['module'])
    if package['module'] == 'ddnsto' and package['phase'] == 'fresh':
        # The live catalog has advanced. Recover the three changed files from
        # their immutable upstream revision, and retain all other pinned bytes.
        observed = inspect(blob, package['module'])
        changed = {name for name in set(observed['files']) | set(package['files'])
                   if observed['files'].get(name) != package['files'].get(name)}
        assert changed <= {'bin/ddnsto_arm', 'bin/ddnsto_aarch64', 'version'}
        replacements = {}
        for name in sorted(changed):
            url = 'https://raw.githubusercontent.com/koolshare/rogsoft/' + DDNSTO_COMMIT + '/ddnsto/ddnsto/' + name
            data = fetch(url, path.with_name('historical-ddnsto-' + Path(name).name))
            assert sha(data) == package['files'][name], name
            replacements['ddnsto/' + name] = data
        if replacements:
            output = io.BytesIO()
            with tarfile.open(fileobj=io.BytesIO(blob)) as source, tarfile.open(fileobj=output, mode='w', format=tarfile.USTAR_FORMAT) as target:
                for member in source:
                    item = copy.copy(member); item.uid = item.gid = item.mtime = 0
                    item.uname = item.gname = ''; item.pax_headers = {}
                    data = None
                    if member.isfile():
                        data = replacements.get(member.name, source.extractfile(member).read())
                        item.size = len(data)
                    target.addfile(item, io.BytesIO(data) if data is not None else None)
            blob = gzip.compress(output.getvalue(), mtime=0)
    verify(blob, package)
    path.write_bytes(blob)
    return blob


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    history_path = ROOT / 'output/real_plugin_tests.json'
    history = json.loads(history_path.read_text())['sources']
    records, packages = [], []
    for package in history['packages']:
        path = ROOT / 'sources/realplugins' / ('gui24447-' + Path(package['path']).name)
        if path.exists(): blob = path.read_bytes()
        else:
            assert not args.verify_only, str(path)
            blob = recover(package, path)
        actual = verify(blob, package)
        digest = sha(blob)
        packages.append(dict(package, historical_path=package['path'], historical_archive_sha256=package['sha256'],
                             path=str(path.relative_to(ROOT)), sha256=digest, md5=hashlib.md5(blob).hexdigest()))
        records.append(dict(path=str(path.relative_to(ROOT)), historical_archive_sha256=package['sha256'],
            archive_sha256=digest, payload_files=len(actual['files']),
            all_payload_files_modes_versions_and_sizes_identical=True))
    target = ROOT / 'build/real_plugin_inputs.json'
    if args.verify_only:
        current = json.loads(target.read_text())
        for expected, actual in zip(packages, current['packages'], strict=True):
            assert all(expected[k] == actual[k] for k in ['path', 'sha256', 'md5', 'files', 'modes', 'internal_version'])
    else:
        manifest = dict(history, packages=packages,
            rehydration_note='Every historical payload byte/path/mode/version/expanded size is retained; archive containers may differ')
        target.write_text(json.dumps(manifest, indent=2) + '\n')
    report = dict(status='SIX_HISTORICAL_PLUGIN_PAYLOADS_VERIFIED', packages=records,
        historical_report_sha256=sha(history_path.read_bytes()), fixture_manifest_sha256=sha(target.read_bytes()),
        ddnsto_payload_source_commit=DDNSTO_COMMIT, source_sha256=sha(Path(__file__).read_bytes()),
        note='Fixture container differences are explicit; original production dependency/source pins remain unchanged')
    (ROOT / 'output/merlin38813gui24447_inputs_verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'], len(packages))


if __name__ == '__main__': main()
