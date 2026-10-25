#!/usr/bin/env python3
"""Prepare an isolated Alpine initramfs for firmware filesystem tools on macOS."""
import concurrent.futures
import gzip
import hashlib
import io
import json
import os
import re
import ssl
import subprocess
import tarfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
PACKAGES = {}
for repo, file in [('main','alpine_APKINDEX.txt'),('community','alpine_community_APKINDEX.txt')]:
    for chunk in (BASE/file).read_text().split('\n\n'):
        info = dict(line.split(':', 1) for line in chunk.splitlines() if ':' in line)
        if 'P' in info:
            info['repo'] = repo
            PACKAGES.setdefault(info['P'], info)
PROVIDES = {}
for name, info in PACKAGES.items():
    for item in info.get('p', '').split():
        PROVIDES[item.split('=')[0]] = name
needed = {'mtd-utils-ubi', 'busybox-static', 'qemu-arm'}
pending = list(needed)
while pending:
    p = pending.pop()
    for dep in PACKAGES[p].get('D', '').split():
        if dep.startswith('so:'):
            n = PROVIDES[dep.split('=')[0]]
            if n not in needed:
                needed.add(n)
                pending.append(n)
needed.add('linux-virt')
cache, root = BASE/'linux-packages', BASE/'linux-root'
cache.mkdir(exist_ok=True)
root.mkdir(exist_ok=True)


def download(name):
    info = PACKAGES[name]
    filename = f"{name}-{info['V']}.apk"
    dest = cache/filename
    if not dest.exists() or dest.stat().st_size != int(info['S']):
        url = 'https://dl-cdn.alpinelinux.org/alpine/v3.22/'+info['repo']+'/aarch64/'+filename
        subprocess.run(['curl', '--fail', '--silent', '--show-error', '--location', '--retry', '3',
                        '--max-time', '180', '-o', str(dest), url], check=True)
    assert dest.stat().st_size == int(info['S']), filename
    return name, dest


with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    downloaded = list(pool.map(download, sorted(needed)))
for name, apk in downloaded:
    raw = gzip.decompress(apk.read_bytes())
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:', ignore_zeros=True) as archive:
        members = [m for m in archive.getmembers() if m.name and not m.name.startswith('.')]
        for m in members:
            assert not m.name.startswith('/') and '..' not in Path(m.name).parts
        archive.extractall(root, members=members, filter='tar')
    print(name, apk.stat().st_size, flush=True)
(BASE/'linux_packages.json').write_text(json.dumps([
    {'package': name, 'version': PACKAGES[name]['V'], 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    for name, path in downloaded], indent=2))
