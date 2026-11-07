#!/usr/bin/env python3
"""Prepare the pinned isolated test engine; no test-engine files enter ROM."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
from sealed_vm import ROOT, inventory, encoded

PIN = ROOT / 'build/merlin_system_sources.json'


def prepare():
    pin = json.loads(PIN.read_text())
    assert pin['schema'] == 1 and len(pin['packages']) <= 100
    packages = []
    for entry in pin['packages']:
        relative = Path(entry['path'])
        assert relative.parts[:2] == ('build','linux-packages') and len(relative.parts) == 3
        path = ROOT / relative
        url = entry['url']
        assert url.startswith(('https://dl-cdn.alpinelinux.org/alpine/v3.22/main/aarch64/',
                               'https://dl-cdn.alpinelinux.org/alpine/v3.22/community/aarch64/'))
        assert url.rsplit('/',1)[-1] == path.name
        if not path.exists():
            path.parent.mkdir(exist_ok=True)
            temporary = path.with_suffix('.download')
            assert not temporary.exists()
            subprocess.run(['curl','--fail','--silent','--show-error','--location','--retry','2',
                            '--max-time','120',url,'-o',str(temporary)],check=True)
            assert temporary.stat().st_size == entry['bytes']
            assert hashlib.sha256(temporary.read_bytes()).hexdigest() == entry['sha256']
            temporary.rename(path)
        assert path.is_file() and not path.is_symlink() and path.stat().st_size == entry['bytes']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256'], path
        packages.append(path)
    target = ROOT / 'build/merlin-system'
    if not target.exists():
        scratch = Path(tempfile.mkdtemp(prefix='merlin-system-',dir=ROOT/'build'))
        # Retain partial generated output if extraction or validation fails.
        for path in packages:
            raw = gzip.decompress(path.read_bytes())
            assert len(raw) < 256 * 1024 * 1024
            with tarfile.open(fileobj=io.BytesIO(raw),mode='r:',ignore_zeros=True) as tar:
                for member in tar.getmembers():
                    if not member.name or member.name.startswith('.'):
                        continue
                    assert not member.name.startswith('/') and '..' not in Path(member.name).parts
                    destination = scratch / member.name
                    if destination.is_symlink():
                        destination.unlink()
                    tar.extract(member,scratch,filter='tar')
        assert hashlib.sha256(encoded(inventory(scratch))).hexdigest() == pin['tree_sha256']
        scratch.rename(target)
    assert not target.is_symlink()
    assert hashlib.sha256(encoded(inventory(target))).hexdigest() == pin['tree_sha256'], 'Test engine cache changed; retained for review'
    return pin


if __name__ == '__main__':
    print('Prepared pinned full-system test engine packages:',len(prepare()['packages']))
