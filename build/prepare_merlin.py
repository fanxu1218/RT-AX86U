#!/usr/bin/env python3
"""Stage the six pinned ARM applications; do not replace vendor global libraries."""
from device_config import leb_size, DEVICE
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIN_PATH = ROOT / DEVICE['sources']['merlin']
PIN = json.loads(PIN_PATH.read_text())
SOURCE = ROOT / 'build/casefs/merlin38812_rootfs'


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def ensure_source():
    """Reconstruct missing immutable input from the pinned image, on casefs."""
    if SOURCE.exists():
        return
    assert SOURCE.parent.is_mount(), 'Mount the case-sensitive build volume first'
    scratch = Path(tempfile.mkdtemp(prefix='merlin-input-', dir=SOURCE.parent))
    subprocess.run(['python3', str(ROOT/'build/inspect_upstream.py'),
                    str(ROOT/PIN['archive']['image']), str(scratch/'volumes')],
                   check=True, stdout=subprocess.DEVNULL)
    layout = json.loads((scratch/'volumes/layout.json').read_text())
    assert layout['whole_crc_valid'] and not any(k.endswith('_bad') and v for k,v in layout['checks'].items())
    extraction = ('from ubireader.ubi_io import ubi_file;from ubireader.ubifs import ubifs;'
                  'from ubireader.ubifs.output import extract_files;import sys;'
                  'extract_files(ubifs(ubi_file(sys.argv[1],int(sys.argv[3]))),sys.argv[2])')
    (scratch/'rootfs').mkdir()
    subprocess.run([str(ROOT/'analysis/.venv/bin/python'), '-c', extraction,
                    str(scratch/'volumes'/DEVICE['image']['rootfs_volume_name']), str(scratch/'rootfs'), str(leb_size())], check=True)
    # Never replace an existing input tree. Failed generated inputs stay in scratch.
    assert not SOURCE.exists()
    (scratch/'rootfs').rename(SOURCE)


def validate():
    a = PIN['archive']
    for key in ['zip', 'image']:
        p = ROOT / a[key]
        assert p.stat().st_size == a[key + '_bytes'] and sha(p) == a[key + '_sha256'], p
    ensure_source()
    for entry in list(PIN['programs'].values()) + list(PIN['libraries'].values()):
        p = SOURCE / entry['path']
        assert p.is_file() and p.resolve().is_relative_to(SOURCE.resolve())
        assert (os.readlink(p) if p.is_symlink() else None) == entry.get('source_link')
        assert p.stat().st_size == entry['bytes'] and sha(p) == entry['sha256'], p
    notice = PIN['notice']
    assert sha(ROOT/notice['path']) == notice['sha256']
    for name, entry in PIN['patchelf'].items():
        p = ROOT / name
        assert p.stat().st_size == entry['bytes'] and sha(p) == entry['sha256'], p


def stage(stage_root, put, metadata):
    validate()
    tool = ROOT / 'build/tools/patchelf-0.18.0'
    assert subprocess.check_output([str(tool), '--version'], text=True).strip() == 'patchelf 0.18.0'
    official = ROOT / 'build/casefs/official_rootfs'
    entries = {}
    # These are generated files in the owned target stage, never the source.
    for category in ['programs', 'libraries']:
        for name, entry in PIN[category].items():
            if category == 'programs':
                target = 'usr/libexec/localmod/merlin/bin/' + name
                put(official / entry['path'], 'usr/libexec/localmod/merlin/vendor/' + name, 0o555)
                put(ROOT / ('build/merlin-' + name + '-launcher'), entry['path'], 0o555)
            else:
                target = 'usr/lib/localmod/merlin/' + name
            put(SOURCE / entry['path'], target, 0o555)
            p = stage_root / target
            # A private, transitive RPATH works without LD_LIBRARY_PATH leaking
            # into VPN hooks, DHCP scripts or SSH login shells.
            if category == 'programs':
                subprocess.run([str(tool), '--page-size', '4096', '--force-rpath',
                                '--set-rpath', PIN['rpath'], str(p)], check=True)
            entries[target] = dict(upstream_sha256=entry['sha256'], staged_sha256=sha(p),
                                   bytes=p.stat().st_size, patch='ELF DT_RPATH only' if category == 'programs' else 'none; transitive executable RPATH')
    aliases = {n: 'dropbearmulti' for n in ['dropbear','dropbearkey','dbclient','ssh']}
    aliases.update({f'vpn{kind}{n}': 'openvpn' for kind in ['client','server'] for n in range(1,6)})
    for family in ['bin', 'vendor']:
        for name, target in aliases.items():
            path = 'usr/libexec/localmod/merlin/' + family + '/' + name
            (stage_root / path).symlink_to(target)
            metadata['/' + path] = dict(mode=stat.S_IFLNK | 0o777, uid=0, gid=0, inum=-1, nlink=1, xattr_count=0)
    receipt = dict(source_tag=PIN['source_tag'], source_commit=PIN['source_commit'],
                   pin_sha256=sha(PIN_PATH), files=entries,
                   disable_marker='/jffs/localmod-merlin-disabled',
                   global_vendor_libraries_replaced=False)
    path = ROOT / 'build/merlin-components.json'
    path.write_text(json.dumps(receipt, indent=2) + '\n')
    put(path, 'rom/etc/localmod-merlin.json', 0o444)
    put(ROOT/PIN['notice']['path'], 'rom/etc/localmod-merlin-notice.txt', 0o444)
    return receipt


def verify(root):
    receipt = json.loads((root / 'rom/etc/localmod-merlin.json').read_text())
    assert receipt['pin_sha256'] == sha(PIN_PATH)
    assert sha(root/'rom/etc/localmod-merlin-notice.txt') == PIN['notice']['sha256']
    for name, entry in receipt['files'].items():
        assert sha(root / name) == entry['staged_sha256'], name
    official = ROOT / 'build/casefs/official_rootfs'
    for name, entry in PIN['programs'].items():
        assert (root / ('usr/libexec/localmod/merlin/vendor/' + name)).read_bytes() == (official / entry['path']).read_bytes()
        assert (root / entry['path']).read_bytes() == (ROOT / ('build/merlin-' + name + '-launcher')).read_bytes()
    for name in ['usr/lib/libssl.so.1.1', 'usr/lib/libcrypto.so.1.1', 'usr/lib/libshared.so',
                 'lib/libnvram.so', 'lib/ld-linux.so.3', 'lib/libc.so.6', 'usr/lib/libip4tc.so.0']:
        assert (root / name).read_bytes() == (official / name).read_bytes(), name
    return receipt
