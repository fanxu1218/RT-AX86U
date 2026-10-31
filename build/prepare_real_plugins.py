#!/usr/bin/env python3
"""Fetch pinned real packages; inspect only, never execute or extract on the host."""
import copy
import gzip
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def source_package(blob, module):
    """Package unchanged files from a pinned upstream git tree, deterministically."""
    result = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(blob)) as source, tarfile.open(fileobj=result, mode='w') as target:
        for original in source:
            relative = original.name.split('/', 1)[1] if '/' in original.name else ''
            if not relative.startswith(module + '/'):
                continue
            assert original.isfile() or original.isdir(), original.name
            item = copy.copy(original)
            item.name = relative
            item.uid = item.gid = item.mtime = 0
            item.uname = item.gname = ''
            item.pax_headers = {}
            target.addfile(item, source.extractfile(original) if item.isfile() else None)
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode='wb', filename='', mtime=0) as zipped:
        zipped.write(result.getvalue())
    return output.getvalue()


def inspect(blob, module):
    files, modes, size = {}, {}, 0
    with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
        for item in archive:
            parts = PurePosixPath(item.name).parts
            assert parts and parts[0] == module and '..' not in parts and not item.name.startswith('/')
            assert item.isdir() or item.isfile(), item.name
            if not item.isfile():
                continue
            name = '/'.join(parts[1:])
            assert name and name not in files and item.size <= 16 * 1024 * 1024
            data = archive.extractfile(item).read()
            size += len(data)
            assert size <= 32 * 1024 * 1024
            files[name], modes[name] = digest(data), item.mode
            if name == 'version':
                version = data.decode().strip()
    assert 'install.sh' in files and 'uninstall.sh' in files and 'version' in files
    return {'internal_version': version, 'files': files, 'modes': modes, 'expanded_bytes': size}


def prepare():
    manifest = json.loads((ROOT / 'build/real_plugin_sources.json').read_text())
    for package in manifest['packages']:
        path = ROOT / package['path']
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or digest(path.read_bytes()) != package['sha256']:
            downloaded = path.with_suffix('.download')
            subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error',
                            '--max-time', '90', '--output', str(downloaded), package['source_url']], check=True)
            blob = downloaded.read_bytes()
            if package['packaging'] == 'unchanged-upstream-source-tree':
                assert digest(blob) == package['source_archive_sha256']
                blob = source_package(blob, package['module'])
            assert digest(blob) == package['sha256'], package['path']
            path.write_bytes(blob)
            downloaded.unlink()
        blob = path.read_bytes()
        assert digest(blob) == package['sha256'] and hashlib.md5(blob).hexdigest() == package['md5']
        details = inspect(blob, package['module'])
        assert details['internal_version'] == package['internal_version']
        package.update(details)
    (ROOT / 'build/real_plugin_inputs.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    data = prepare()
    print('Verified', len(data['packages']), 'pinned real plugin archives; no host extraction/execution')
