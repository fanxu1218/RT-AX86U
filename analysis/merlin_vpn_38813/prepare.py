#!/usr/bin/env python3
"""Verify the upstream archive and extract one immutable, case-sensitive tree."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import ssl
import sys
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'build'))
from sealed_vm import encoded, inventory, sha
from ubireader.ubi_io import ubi_file
from ubireader.ubifs import ubifs, walk
from ubireader.ubifs.output import extract_files

COMMIT = 'd1a59dcffbe0402c7ac8ac3090cb7c928510fbcd'
TAG = '3004.388.13'


def main():
    base = ROOT / 'upstream/merlin38813'
    archive = base / 'RT-AX86U_3004_388.13_0.zip'
    if not archive.exists():
        partial = archive.with_suffix('.zip.part')
        with zipfile.ZipFile(partial) as z:
            assert z.testzip() is None
        partial.rename(archive)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        members = {Path(n).name: n for n in z.namelist() if not n.endswith('/')}
        assert len(members) == len([n for n in z.namelist() if not n.endswith('/')])
        image_name = 'RT-AX86U_3004_388.13_0_pureubi.w'
        assert image_name in members, sorted(members)
        for name, member in members.items():
            assert name not in ('', '.', '..')
            target = base / name
            data = z.read(member)
            if target.exists():
                assert target.read_bytes() == data
            else:
                target.write_bytes(data)
    image = base / image_name
    checksums = (base / 'sha256sum.sha256').read_text()
    assert sha(image) in checksums and image_name in checksums

    # Update only the small upstream source contracts used by the local probes.
    rows = []
    for manifest in ['sources.json', 'uu_sources.json']:
        old = json.loads((ROOT / 'analysis/merlin_vpn_38812/vendor' / manifest).read_text())
        for row in old['files']:
            url = row['url'].replace(old['source_commit'], COMMIT)
            rows.append((manifest, Path(row['path']).name, url))
    def fetch(row):
        manifest, name, url = row
        cache = HERE / 'vendor' / manifest
        target = HERE / 'vendor' / name
        if cache.is_file() and target.is_file():
            cached = json.loads(cache.read_text())
            matches = [r for r in cached['files'] if Path(r['path']).name == name]
            if cached['source_commit'] == COMMIT and len(matches) == 1:
                assert matches[0]['url'] == url and matches[0]['sha256'] == sha(target)
                return manifest, matches[0]
        for attempt in range(4):
            try:
                data = urllib.request.urlopen(url, timeout=35,
                    context=ssl.create_default_context(cafile='/etc/ssl/cert.pem')).read()
                assert data and not data.startswith(b'<!DOCTYPE')
                target = HERE / 'vendor' / name
                target.write_bytes(data)
                return manifest, dict(path=name, url=url, bytes=len(data), sha256=sha(target))
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(1)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        fetched = list(pool.map(fetch, rows))
    for manifest in ['sources.json', 'uu_sources.json']:
        (HERE / 'vendor' / manifest).write_text(json.dumps(dict(
            source_tag=TAG, source_commit=COMMIT,
            files=[row for group, row in fetched if group == manifest]), indent=2) + '\n')
    pin = dict(schema=1, source_tag=TAG, source_commit=COMMIT,
        source_url='https://github.com/RMerl/asuswrt-merlin.ng/tree/' + COMMIT,
        archive=dict(zip=str(archive.relative_to(ROOT)), zip_bytes=archive.stat().st_size,
            zip_sha256=sha(archive), image=str(image.relative_to(ROOT)),
            image_bytes=image.stat().st_size, image_sha256=sha(image),
            published_image_sha256_matches=True, zip_crc_valid=True,
            download_url='https://sourceforge.net/projects/asuswrt-merlin/files/RT-AX86U/Release/' + archive.name + '/download'))
    (ROOT / 'build/merlin38813_sources.json').write_text(json.dumps(pin, indent=2) + '\n')
    volumes = base / 'carved'
    subprocess.run([sys.executable, str(ROOT / 'build/inspect_upstream.py'),
        str(image), str(volumes)], check=True, stdout=subprocess.DEVNULL)
    layout = json.loads((volumes / 'layout.json').read_text())
    assert layout['whole_crc_valid'] and not any(k.endswith('_bad') and v for k, v in layout['checks'].items())
    parsed = ubifs(ubi_file(str(volumes / 'rootfs_ubifs'), 126976))
    nodes, bad, metadata = {}, [], {}
    walk.index(parsed, parsed.master_node.root_lnum, parsed.master_node.root_offs, nodes, bad)
    assert not bad
    def visit(number, path):
        node = nodes[number]; ino = node['ino']
        metadata[path] = dict(mode=ino.mode, uid=ino.uid, gid=ino.gid,
            inum=number, nlink=ino.nlink, xattr_count=getattr(ino, 'xattr_cnt', 0))
        for entry in node.get('dent', []):
            visit(entry.inum, path.rstrip('/') + '/' + entry.name)
    visit(1, '/')
    tree = ROOT / 'build/casefs/merlin38813_rootfs'
    assert tree.parent.is_mount() and not tree.exists(), 'Never replace an existing upstream extraction'
    tree.mkdir()
    extract_files(parsed, str(tree))
    assert {'/' + p for p in inventory(tree)} | {'/'} == set(metadata)
    for path, row in metadata.items():
        p = tree / path.lstrip('/')
        if not p.is_symlink():
            p.chmod(row['mode'] & 0o7777)
    (base / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    report = dict(status='UPSTREAM_38813_ARCHIVE_AND_TREE_VERIFIED', pin=pin,
        rootfs=str(tree.relative_to(ROOT)), paths=len(inventory(tree)),
        inventory_sha256=hashlib.sha256(encoded(inventory(tree))).hexdigest(),
        zip_crc_verified=True, published_image_digest_verified=True,
        whole_image_and_ubi_crcs_verified=True, fresh_ubifs_readback=True,
        physical_router_flashed=False)
    (ROOT / 'output/merlin38813_upstream_audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'], report['paths'], 'paths', flush=True)


if __name__ == '__main__':
    main()
