#!/usr/bin/env python3
"""Repack a private P7 copy with one data backport; never replace P7 evidence."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import selectors
import stat
import subprocess
import sys
import time

from gui24447 import ROOT, PIN, apply, digest, payload
from audit_gui24447 import read_image, write_report


def inventory(root):
    entries, aliases = {}, {}
    def visit(path):
        info = path.lstat(); relative = path.relative_to(root).as_posix()
        name = '/' if relative == '.' else '/' + relative
        row = dict(mode=info.st_mode, uid=0, gid=0)
        if stat.S_ISLNK(info.st_mode):
            row.update(type='link', target=os.readlink(path))
        elif stat.S_ISREG(info.st_mode):
            row.update(type='file', bytes=info.st_size, sha256=digest(path.read_bytes()))
            aliases.setdefault((info.st_dev, info.st_ino), []).append(name)
        else:
            assert stat.S_ISDIR(info.st_mode), name
            row['type'] = 'directory'
        entries[name] = row
        if row['type'] == 'directory':
            for child in sorted(path.iterdir()):
                visit(child)
    visit(root)
    for paths in aliases.values():
        if len(paths) > 1:
            for path in paths:
                entries[path]['hardlink_group'] = min(paths)
    return entries


def main():
    sys.path.insert(0, str(ROOT / 'build'))
    from sealed_vm import acquire_slot
    from device_config import mkfs_flags
    from repack_image import repack
    pin, fixed = payload()
    source = ROOT / pin['target_image']
    assert digest(source.read_bytes()) == pin['target_image_sha256']
    before, _, _, _ = read_image(source, hardlinks=True)
    assert all(row['uid'] == row['gid'] == 0 for row in before.values()), 'Squash-ownership must match P7'
    base = ROOT / 'build/casefs'
    assert base.is_mount()
    work = base / ('gui24447-build-' + secrets.token_hex(8)); work.mkdir(mode=0o700)
    stage = work / 'rootfs'
    from ubireader.ubi_io import ubi_file
    from ubireader.ubifs import ubifs
    from ubireader.ubifs.output import extract_files
    volumes = work / 'volumes'
    subprocess.run([sys.executable, str(ROOT / 'build/inspect_upstream.py'), str(source), str(volumes)],
                   check=True, stdout=subprocess.DEVNULL)
    stage.mkdir()
    extract_files(ubifs(ubi_file(str(volumes / 'rootfs_ubifs'), 126976)), str(stage))
    for path, row in before.items():
        file = stage / path.lstrip('/')
        if row['type'] == 'link':
            os.lchmod(file, stat.S_IMODE(row['mode']))
        else:
            file.chmod(stat.S_IMODE(row['mode']))
    assert inventory(stage) == before, 'P7 extraction differs from the pinned image'
    assert apply(stage)
    expected = inventory(stage)
    assert [p for p in before if before[p] != expected.get(p)] == ['/' + pin['path']]
    protected_names = ['output/merlin38813_native_candidate_tests.json', 'output/merlin38813_local_gate.json',
                       'output/merlin38813_hour_gate.json', 'output/merlin38813_release_delivery.json']
    protected = {p: digest((ROOT / p).read_bytes()) for p in protected_names}
    tools = ROOT / 'build/tools'
    for name in ['LinuxBuilder', 'linux-Image', 'linux-initramfs.gz']:
        assert (tools / name).is_file(), name
    (work / 'build').mkdir()
    script = ('#!/bin/sh\nset -eu\nmkdir /tmp/clean-rootfs\ncp -a /work/rootfs/. /tmp/clean-rootfs/\n' +
              'mkfs.ubifs ' + ' '.join(mkfs_flags()) +
              ' -r /tmp/clean-rootfs -o /work/build/gui24447.ubifs\n')
    (work / 'build/linux_job.sh').write_text(script)
    slot = acquire_slot()
    proc, console = None, bytearray()
    try:
        proc = subprocess.Popen([str(tools / 'LinuxBuilder'), str(tools / 'linux-Image'),
                                 str(tools / 'linux-initramfs.gz'), str(work)],
                                env=dict(os.environ, LOCALMOD_TEST_CPUS='1'), pass_fds=(slot,),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        stream = selectors.DefaultSelector(); stream.register(proc.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            for key, _ in stream.select(.1):
                part = key.fileobj.read1(65536)
                if part:
                    console.extend(part)
                    assert len(console) <= 8 * 1024 * 1024
                    assert b'Kernel panic' not in console and b'Internal error: Oops' not in console
                else:
                    stream.unregister(key.fileobj)
            if (work / 'build/linux-job.status').exists() or proc.poll() is not None:
                break
        else:
            raise TimeoutError('Owned filesystem build exceeded 180 seconds')
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait()
        if proc is not None:
            stream.close()
            console.extend(proc.stdout.read(1024 * 1024))
            proc.stdout.close()
        os.close(slot)
    log = ROOT / 'output/merlin38813_gui24447_build.log'
    with log.open('xb') as stream:
        stream.write(console)
    assert (work / 'build/linux-job.status').read_text().strip() == '0', console.decode(errors='replace')
    assert inventory(stage) == expected and digest(source.read_bytes()) == pin['target_image_sha256']
    packed, packing = repack(source.read_bytes(), (work / 'build/gui24447.ubifs').read_bytes())
    name = 'RT-AX86U_3004_388.13_0_localmod_native_P7_GUI24447_' + packing['sha256'][:8] + '_NOT_FLASH_READY.w'
    image = ROOT / 'output' / name
    with image.open('xb') as stream:
        stream.write(packed)
    actual, actual_data, _, layout = read_image(image, hardlinks=True)
    assert actual == expected, 'Full UBIFS content/mode/owner/link/hardlink readback differs'
    assert actual_data['/' + pin['path']] == fixed
    assert protected == {p: digest((ROOT / p).read_bytes()) for p in protected}
    sources = ['analysis/merlin_vpn_38813/build_gui24447.py', 'analysis/merlin_vpn_38813/gui24447.py',
               'analysis/merlin_vpn_38813/audit_gui24447.py', 'build/asus24447_sources.json',
               pin['source'], 'build/repack_image.py', 'build/LinuxBuilder.swift', 'build/make_initramfs.py']
    report = dict(schema=1, status='P7_GUI24447_BUILT_FULL_READBACK_PASS_NOT_FLASH_READY',
        image=str(image.relative_to(ROOT)), sha256=packing['sha256'], bytes=len(packed),
        base_image=pin['target_image'], base_sha256=pin['target_image_sha256'],
        changed_paths=[pin['path']], readback_paths=len(actual), packing=packing,
        content_modes_owners_symlinks_hardlinks_verified=True, image_and_ubi_crcs_verified=True,
        firmware_base_remains='Merlin 3004.388.13 / P7; ASUS language-name backport only',
        stage=str(stage.relative_to(ROOT)), protected_sha256=protected,
        source_sha256={p: digest((ROOT / p).read_bytes()) for p in sources},
        build_tools_sha256={name: digest((tools / name).read_bytes()) for name in ['LinuxBuilder', 'linux-Image', 'linux-initramfs.gz']},
        build_log_sha256=digest(console), physical_router_accessed=False,
        physical_router_flashed=False, device_or_visual_accepted=False, published=False,
        limits=['Repacked/read back; not a fresh full P7 runtime gate or hour-long test.',
                'Kernel/driver/WAN/Wi-Fi/NAT/AiMesh, actual UU and physical upgrade remain untested.',
                'The original P7 release and its bound evidence remain unchanged.'])
    write_report(ROOT / 'output/merlin38813_gui24447_candidate.json', report)
    with (ROOT / 'output/merlin38813_GUI24447_SHA256SUMS').open('x') as output:
        output.write(packing['sha256'] + '  ' + name + '\n')
    print(report['status'], name, len(actual), 'paths; exactly one changed file')


if __name__ == '__main__':
    main()
