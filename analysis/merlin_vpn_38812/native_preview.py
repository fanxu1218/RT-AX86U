#!/usr/bin/env python3
"""Prepare an independent full-Merlin userspace preview; never select a release.

The existing candidate is an immutable donor for the managed software center.
Native rc, VPN, libraries, kernel modules and pages come from the pinned Merlin
image. Automatic center hooks and a flashable artifact are separate work.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'build'))
from sealed_vm import inventory, encoded, sha, copy_file
from ubireader.ubi_io import ubi_file
from ubireader.ubifs import ubifs, walk
from ubireader.ubifs.output import extract_files


def content(tree):
    return {n: {k: v for k, v in row.items() if k != 'mode'} for n, row in tree.items()}


def prepare():
    os.chdir(ROOT)
    gate = json.loads((ROOT / 'output/release_gates.json').read_text())
    pin = json.loads((ROOT / 'build/merlin_sources.json').read_text())
    protected = {n: sha(ROOT / n) for n in [gate['config']['image'],
                 'output/release_gates.json', 'output/local_delivery.json',
                 'build/release_config.json']}
    assert sha(ROOT / pin['archive']['image']) == pin['archive']['image_sha256']
    assert protected[gate['config']['image']] == gate['candidate_sha256']
    parent = ROOT / 'build/casefs'
    assert parent.is_mount()
    work = parent / ('merlin-native-preview-' + secrets.token_hex(8))
    work.mkdir()
    stage = work / 'rootfs'
    original = ROOT / 'build/casefs/merlin38812_rootfs'
    source_inventory = inventory(original)
    audit = json.loads((ROOT / 'output/merlin38812_migration_contracts.json').read_text())
    assert hashlib.sha256(encoded(content(source_inventory))).hexdigest() == audit['upstream_content_tree_sha256']
    assert audit['image_sha256'] == pin['archive']['image_sha256']
    shutil.copytree(original, stage, symlinks=True, copy_function=copy_file)
    meta = json.loads((ROOT / 'upstream/merlin/metadata.json').read_text())

    # Re-read the pinned candidate, rather than trusting a mutable staged core.
    volumes = work / 'donor-volumes'
    subprocess.run([sys.executable, str(ROOT / 'build/inspect_upstream.py'),
                    str(ROOT / gate['config']['image']), str(volumes)],
                   check=True, stdout=subprocess.DEVNULL)
    layout = json.loads((volumes / 'layout.json').read_text())
    assert layout['whole_crc_valid'] and not any(k.endswith('_bad') and v for k, v in layout['checks'].items())
    parsed = ubifs(ubi_file(str(volumes / 'rootfs_ubifs'), 126976))
    inodes, bad, donor_meta = {}, [], {}
    walk.index(parsed, parsed.master_node.root_lnum, parsed.master_node.root_offs, inodes, bad)
    assert not bad
    def visit(number, path):
        node = inodes[number]; ino = node['ino']
        donor_meta[path] = dict(mode=ino.mode, uid=ino.uid, gid=ino.gid,
                                inum=number, nlink=ino.nlink,
                                xattr_count=getattr(ino, 'xattr_cnt', 0))
        for dent in node.get('dent', []):
            visit(dent.inum, path.rstrip('/') + '/' + dent.name)
    visit(1, '/')
    donor = work / 'donor-rootfs'; donor.mkdir()
    extract_files(parsed, str(donor))

    overlay = []
    def put(source, path, mode=None):
        dest = stage / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        assert not source.is_symlink() or mode is None
        if dest.is_symlink() or dest.is_file(): dest.unlink()
        if source.is_symlink(): dest.symlink_to(os.readlink(source))
        else: copy_file(source, dest)
        row = dict(donor_meta.get('/' + path, {}))
        if mode is not None:
            row = dict(mode=stat.S_IFREG | mode, uid=0, gid=0, inum=-1, nlink=1, xattr_count=0)
        assert row
        meta['/' + path] = row
        overlay.append(path)
    def tree(path):
        for p in sorted((donor / path).rglob('*')):
            n = p.relative_to(donor).as_posix()
            if p.is_symlink() or p.is_file(): put(p, n)
            elif p.is_dir():
                (stage / n).mkdir(parents=True, exist_ok=True)
                meta['/' + n] = dict(donor_meta['/' + n])
    tree('rom/etc/koolshare')
    helpers = ['archive-guard','bootstrap.sh','busybox','dispatch.sh',
               'fancyss-packages.sha256','installer-guard.sh','localmod-event',
               'localmod-status','log-limit','plugin-compat.sh','plugin-run','plugin-txn']
    for n in helpers: put(donor / 'usr/libexec/localmod' / n, 'usr/libexec/localmod/' + n)
    # Keep Merlin's full helper.sh, including addon settings and WebUI helpers.
    # The old compatibility subset would silently remove these native APIs.
    for n in ['usr/bin/skipd','usr/bin/dbus','usr/bin/jffsinit.sh',
              'www/Module_FancyssLocalmod.asp',
              'www/Module_Localmod.asp','rom/etc/localmod-core-id']:
        put(donor / n, n)
    for path, target in [('koolshare','jffs/.koolshare'),
                         ('usr/bin/tee','/usr/libexec/localmod/busybox'),
                         ('usr/bin/xargs','/usr/libexec/localmod/busybox')]:
        p = stage / path
        # Merlin already supplies these BusyBox applets: preserve them.
        if path != 'koolshare' and (p.exists() or p.is_symlink()): continue
        assert not p.exists() and not p.is_symlink(), path
        p.symlink_to(target)
        meta['/' + path] = dict(mode=stat.S_IFLNK | 0o777, uid=0, gid=0,
                                inum=-1, nlink=1, xattr_count=0)
        overlay.append(path)

    tools = work / 'tools'; tools.mkdir()
    cc = [str(ROOT / 'sources/zig-aarch64-macos-0.15.2/zig'), 'cc',
          '-target', 'arm-linux-gnueabi.2.26', '-mcpu=cortex_a53', '-O2']
    subprocess.run([*cc, '-shared', '-fPIC', '-o', str(tools / 'httpd_bridge.so'),
                    str(ROOT / 'sources/localmod/httpd_bridge.c'), '-ldl'], check=True)
    subprocess.run([*cc, '-o', str(tools / 'httpd-launcher'),
                    str(ROOT / 'sources/localmod/launcher.c')], check=True)
    # The authenticated native server and its entire native libraries remain
    # unchanged. Only its entry launcher and narrowly scoped center relay vary.
    put(original / 'usr/sbin/httpd', 'usr/libexec/localmod/httpd', 0o500)
    put(tools / 'httpd-launcher', 'usr/sbin/httpd', 0o500)
    put(tools / 'httpd_bridge.so', 'usr/lib/localmod/httpd_bridge.so', 0o444)
    state = stage / 'www/state.js'
    old = (donor / 'www/state.js').read_text()
    marker = '// localmod-software-center-entry:'
    assert old.count(marker) == 1
    state.write_text(state.read_text() + '\n' + old[old.index(marker):])
    overlay.append('www/state.js')
    profile = stage / 'rom/etc/profile'
    marker = '# localmod center tools for SSH sessions'
    old = (donor / 'rom/etc/profile').read_text()
    assert old.count(marker) == 1
    profile.write_text(profile.read_text() + '\n' + old[old.index(marker):])
    overlay.append('rom/etc/profile')
    # Preview labels must not inherit the old candidate's version claim.
    for n in ['www/Module_Localmod.asp', 'www/Module_FancyssLocalmod.asp']:
        p = stage / n
        p.write_text(p.read_text().replace('3.0.0.4.388_24437', '3004.388.12_2 preview')
                     .replace('r9-r2', 'Merlin native preview'))
    release = stage / 'rom/etc/localmod-release.json'
    release.write_text(json.dumps(dict(base=pin['source_tag'], variant='native-preview',
        status='INCOMPLETE_NOT_A_FLASH_RELEASE', software_center='1.9.60',
        native_uu='native NTP callback retained; real acceleration not verified',
        automatic_center_startup_integrated=False), indent=2) + '\n')
    meta['/rom/etc/localmod-release.json'] = dict(mode=stat.S_IFREG | 0o444,
        uid=0, gid=0, inum=-1, nlink=1, xattr_count=0)
    overlay.append('rom/etc/localmod-release.json')

    for p in stage.rglob('*'):
        n = '/' + p.relative_to(stage).as_posix()
        if n not in meta:
            assert p.is_dir() and not p.is_symlink(), n
            meta[n] = dict(mode=stat.S_IFDIR | 0o755, uid=0, gid=0,
                           inum=-1, nlink=1, xattr_count=0)
        if not p.is_symlink(): p.chmod(meta[n]['mode'] & 0o7777)
    final = inventory(stage)
    changed = [n for n, row in source_inventory.items()
               if content({n:row}) != content({n:final.get(n, {})})]
    assert set(changed) == {'usr/sbin/httpd','www/state.js','rom/etc/profile'}
    for path in ['sbin/rc','sbin/init','usr/lib/libovpn.so','usr/lib/libshared.so',
                 'usr/sbin/helper.sh','www/UUAccelerator.asp','www/Advanced_VPNDirector.asp',
                 'www/Advanced_OpenVPNClient_Content.asp']:
        expected = dict(source_inventory[path])
        if expected['type'] != 'link': expected['mode'] = meta['/'+path]['mode'] & 0o7777
        # macOS lstat reports its own symlink permissions. Link targets are
        # preserved; the firmware inode mode remains in the authoritative table.
        assert final[path] == expected, path
    assert content(source_inventory) == content(inventory(original))
    assert protected == {n:sha(ROOT/n) for n in protected}
    manifest = dict(status='FULL_MERLIN_USERSPACE_PREVIEW_STAGED_NOT_RELEASED',
        rootfs=str(stage.relative_to(ROOT)), metadata=str((work/'metadata.json').relative_to(ROOT)),
        base_image_sha256=pin['archive']['image_sha256'],
        center_donor_image_sha256=gate['candidate_sha256'],
        original_paths_changed=changed, overlay_paths=sorted(set(overlay)),
        inventory_sha256=hashlib.sha256(encoded(final)).hexdigest(),
        protected_sha256=protected, automatic_center_startup_integrated=False,
        firmware_image_built=False, physical_router_flashed=False,
        limits=['Staging and content equivalence only; no native boot or feature acceptance',
                'No release selection changed; preview is an isolated test input'])
    (work/'metadata.json').write_text(json.dumps(meta, indent=2)+'\n')
    (work/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    (ROOT/'output/merlin38812_native_preview_stage.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(manifest['status'], manifest['rootfs'])
    return manifest


if __name__ == '__main__': prepare()
