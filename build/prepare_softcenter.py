#!/usr/bin/env python3
"""Apply a pinned published HND core payload as data, never run its installer."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tarfile
from sealed_vm import ROOT, encoded, inventory, sha
from device_config import DEVICE

PIN = ROOT / DEVICE['sources']['softcenter']


def read_payload():
    pin = json.loads(PIN.read_text())
    package = ROOT / pin['package_path']
    assert package.is_file() and not package.is_symlink()
    assert package.stat().st_size == pin['package_bytes'] and sha(package) == pin['package_sha256']
    assert hashlib.md5(package.read_bytes()).hexdigest() == pin['published_md5']
    rows, total = {}, 0
    with tarfile.open(package) as archive:
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            assert path.parts and path.parts[0] == 'softcenter' and not path.is_absolute()
            assert all(p not in ['.', '..'] for p in path.parts) and len(member.name) <= 1024
            name = '/'.join(path.parts[1:])
            if not name:
                assert member.isdir()
                continue
            assert name not in rows and len(rows) < 512
            assert member.isdir() or member.isfile() or member.issym()
            assert member.uid == member.gid == 0 and not member.mode & 0o7000
            row = dict(mode=member.mode & 0o777, type='directory' if member.isdir() else 'link' if member.issym() else 'file')
            if member.isfile():
                assert 0 <= member.size <= 4 * 1024 * 1024
                total += member.size
                assert total <= 16 * 1024 * 1024
                row['data'] = archive.extractfile(member).read()
                assert len(row['data']) == member.size
            elif member.issym():
                target = PurePosixPath(member.linkname)
                assert not target.is_absolute() and all(p not in ['.', '..'] for p in target.parts)
                row['target'] = member.linkname
            rows[name] = row
    for name in rows:
        for parent in PurePosixPath(name).parents:
            if str(parent) != '.':
                assert rows[str(parent)]['type'] == 'directory', 'Payload parent must be a directory'
    assert rows['.soft_ver']['data'].decode().strip() == pin['version']
    assert rows['.valid']['data'].decode().strip() == pin['platform']
    return pin, rows


def patch_frontend(text):
    # Both the inline release ASP and its distributed JS contain this link.
    old = 'R=d?`http://${d}:3032`:""'
    assert text.count(old) == 1
    return text.replace(old, 'R="/Module_Localmod.asp"')


def prepare():
    pin, rows = read_payload()
    donor = ROOT / 'build/casefs/koolcenter_rootfs/rom/etc/koolshare'
    parent = ROOT / 'build/casefs/softcenter-private'
    assert (ROOT / 'build/casefs').is_mount() and not parent.is_symlink()
    parent.mkdir(mode=0o700, exist_ok=True)
    script_sha = sha(Path(__file__).resolve())
    destination = parent / ('core-' + pin['package_sha256'][:16] + '-' + sha(PIN)[:8] + '-' + script_sha[:8])
    metadata_path = parent / (destination.name + '.metadata.json')
    if destination.exists():
        assert not destination.is_symlink() and metadata_path.is_file()
        cache = json.loads(metadata_path.read_text())
        assert cache['package_sha256'] == pin['package_sha256'] and cache['input_sha256'] == sha(PIN)
        assert cache['preparer_sha256'] == script_sha
        assert cache['tree'] == inventory(destination)
        return destination, cache['metadata']
    assert not metadata_path.exists()
    shutil.copytree(donor, destination, symlinks=True)
    # The upstream release replaces its frontend. Remove only the old owned
    # frontend directory from this fresh ROM copy; no JFFS/plugin data involved.
    old_ui = destination / 'res/soft-v19'
    assert old_ui.is_dir() and not old_ui.is_symlink()
    shutil.rmtree(old_ui)
    prefix = '/rom/etc/koolshare'
    donor_meta = json.loads((ROOT / 'upstream/koolcenter/metadata.json').read_text())
    metadata = {p: dict(m) for p, m in donor_meta.items() if p == prefix or p.startswith(prefix + '/')}
    for p in list(metadata):
        if p == prefix + '/res/soft-v19' or p.startswith(prefix + '/res/soft-v19/'):
            del metadata[p]
    for name, row in rows.items():
        if name == 'install.sh':
            continue  # updater program is not part of its installed runtime.
        target = destination / name
        if row['type'] == 'directory':
            assert not target.is_symlink()
            target.mkdir(parents=True, exist_ok=True)
        else:
            assert target.parent.is_dir() and not target.parent.is_symlink()
            if target.exists() or target.is_symlink():
                assert not target.is_dir() or target.is_symlink()
                target.unlink()
            if row['type'] == 'link':
                target.symlink_to(row['target'])
            else:
                target.write_bytes(row['data'])
        if row['type'] != 'link':
            target.chmod(row['mode'])
        kind = stat.S_IFDIR if row['type'] == 'directory' else stat.S_IFLNK if row['type'] == 'link' else stat.S_IFREG
        # Linux symlinks have mode0777; their access control comes from the
        # parent and target. mkfs.ubifs uses that host link mode and cannot
        # represent this payload tar's decorative0755 via its device table.
        mode = 0o777 if row['type'] == 'link' else row['mode']
        metadata[prefix + '/' + name] = dict(mode=kind | mode, uid=0, gid=0, inum=-1, nlink=1, xattr_count=0)
    assert (destination / '.soft_ver').read_text().strip() == pin['version']
    cache = dict(package_sha256=pin['package_sha256'], input_sha256=sha(PIN), preparer_sha256=script_sha, metadata=metadata, tree=inventory(destination))
    metadata_path.write_bytes(encoded(cache) + b'\n')
    return destination, metadata


if __name__ == '__main__':
    path, metadata = prepare()
    print('Verified published HND core payload:', path, len(metadata), 'metadata entries')
