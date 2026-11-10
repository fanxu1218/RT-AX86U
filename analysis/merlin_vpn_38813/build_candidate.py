#!/usr/bin/env python3
"""Rebase only the verified P6 augmentation onto the complete 388.13 image."""
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
from device_config import mkfs_flags
import model_private
from repack_image import repack
from ubireader.ubi_io import ubi_file
from ubireader.ubifs import ubifs, walk
from ubireader.ubifs.output import extract_files
from gui24447 import apply as apply_gui24447


def main():
    os.chdir(ROOT)
    release = json.loads((HERE / 'release.json').read_text())
    assert release['base'] == '3004.388.13' and release['revision'] == 'P7'
    assert not release['flash_ready'] and not release['published']
    pin = json.loads((ROOT / 'build/merlin38813_sources.json').read_text())
    audit = json.loads((ROOT / 'output/merlin38813_upstream_audit.json').read_text())
    original = ROOT / audit['rootfs']
    upstream = inventory(original)
    assert hashlib.sha256(encoded(upstream)).hexdigest() == audit['inventory_sha256']
    prior = json.loads((ROOT / 'output/merlin38812_native_candidate_tests.json').read_text())
    donor = ROOT / prior['rootfs']
    assert sha(ROOT / prior['image']['image']) == prior['image']['sha256']
    donor_inventory = inventory(donor)
    assert hashlib.sha256(encoded(donor_inventory)).hexdigest() == prior['stage_inventory_sha256']
    old = inventory(ROOT / 'build/casefs/merlin38812_rootfs')
    old_meta = json.loads((ROOT / 'upstream/merlin/metadata.json').read_text())
    # The historical extraction predates mode normalization. Compare against
    # its authoritative UBIFS permissions without mutating that old tree.
    for n, row in old.items():
        if row['type'] != 'link': row['mode'] = old_meta['/' + n]['mode'] & 0o7777
    overrides = {'rom/etc/profile', 'sbin/rc', 'usr/sbin/httpd', 'usr/sbin/iptables-restore', 'www/state.js'}
    delta = {n for n in old if old[n] != donor_inventory.get(n)}
    assert delta == overrides, delta
    protected_names = ['output/merlin38812_native_candidate_tests.json',
        'output/merlin38812_local_gate.json', 'output/merlin38812_release_documentation_delivery.json',
        prior['image']['image'], 'build/merlin_sources.json', 'build/release_config.json']
    protected = {n: sha(ROOT / n) for n in protected_names}
    work = ROOT / 'build/casefs' / ('merlin38813-candidate-' + secrets.token_hex(8))
    work.mkdir(); stage = work / 'rootfs'; tools = work / 'tools'; tools.mkdir()
    shutil.copytree(original, stage, symlinks=True, copy_function=copy_file)
    meta = json.loads((ROOT / 'upstream/merlin38813/metadata.json').read_text())
    prior_meta = json.loads((donor.parent / 'metadata.json').read_text())
    def put(src, name, mode=None):
        dst = stage / name; dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.is_symlink() or dst.is_file(): dst.unlink()
        if src.is_symlink(): dst.symlink_to(os.readlink(src))
        elif src.is_dir(): dst.mkdir(exist_ok=True)
        else: copy_file(src, dst)
        row = dict(prior_meta.get('/' + name, {}))
        if mode is not None:
            row = dict(mode=stat.S_IFREG | mode, uid=0, gid=0, inum=-1, nlink=1, xattr_count=0)
        assert row, name
        # These copied files have independent inodes; upstream hardlink numbers
        # from the old base must never join a different new-base inode group.
        row['inum'] = -1
        meta['/' + name] = row
    added = sorted(set(donor_inventory) - set(old))
    for name in added:
        assert name not in upstream, ('New upstream path conflicts with an overlay', name)
        put(donor / name, name)
    for name in ['rom/etc/profile', 'www/state.js']:
        marker = '# localmod center tools for SSH sessions' if name.endswith('profile') else '// localmod-software-center-entry:'
        text = (donor / name).read_text(); assert text.count(marker) == 1
        native = (stage / name).read_text(); assert marker not in native
        (stage / name).write_text(native + '\n' + text[text.index(marker):])
    cc = [str(ROOT / 'sources/zig-aarch64-macos-0.15.2/zig'), 'cc',
        '-target', 'arm-linux-gnueabi.2.26', '-mcpu=cortex_a53', '-O2', '-s']
    for output, source, flags in [
        ('native_boot_bridge.so', HERE / 'native_boot_bridge.c', ['-shared', '-fPIC', str(ROOT / 'sources/localmod/runtime.c'), '-ldl']),
        ('native-rc', HERE / 'native_launcher.c', []),
        ('native-restore', HERE / 'native_restore.c', [str(ROOT / 'sources/localmod/runtime.c')]),
        ('compat-sleep', HERE / 'center_sleep.c', []),
        ('httpd_bridge.so', ROOT / 'sources/localmod/httpd_bridge.c', ['-shared', '-fPIC', '-ldl']),
        ('httpd-launcher', ROOT / 'sources/localmod/launcher.c', [])]:
        subprocess.run([*cc, '-o', str(tools / output), str(source), *flags], check=True)
    for src, name, mode in [
        (original / 'sbin/rc', 'usr/libexec/localmod/rc.vendor', 0o500),
        (original / 'usr/sbin/httpd', 'usr/libexec/localmod/httpd', 0o500),
        (tools / 'native-rc', 'sbin/rc', 0o500),
        (tools / 'native-restore', 'usr/sbin/iptables-restore', 0o500),
        (tools / 'native_boot_bridge.so', 'usr/lib/localmod/native_boot_bridge.so', 0o444),
        (tools / 'httpd_bridge.so', 'usr/lib/localmod/httpd_bridge.so', 0o444),
        (tools / 'httpd-launcher', 'usr/sbin/httpd', 0o500),
        (tools / 'compat-sleep', 'usr/libexec/localmod/compat-bin/sleep', 0o755)]:
        put(src, name, mode)
    for name in ['www/Module_Localmod.asp', 'www/Module_FancyssLocalmod.asp', 'usr/libexec/localmod/fancyss-uninstall-NOTICE.txt']:
        p = stage / name; p.chmod(0o644)
        p.write_text(p.read_text().replace('3004.388.12_2', release['base']).replace('localmod-native-P6', 'localmod-native-P7').replace('localmod-native-38812-p6-experimental', release['release_tag']))
    identity = stage / 'rom/etc/localmod-release.json'; identity.chmod(0o644)
    data = json.loads(identity.read_text()); data.update(base=release['base'], revision='P7', release_tag=release['release_tag'])
    identity.write_text(json.dumps(data, indent=2) + '\n')
    apply_gui24447(stage)
    # Restore only the new upstream's native hardlinks.
    groups = {}
    for name, row in meta.items():
        p = stage / name.lstrip('/')
        if row['inum'] >= 0 and stat.S_ISREG(row['mode']) and name.lstrip('/') not in overrides:
            groups.setdefault(row['inum'], []).append(p)
    for paths in groups.values():
        for p in paths[1:]:
            assert sha(p) == sha(paths[0]); p.unlink(); os.link(paths[0], p)
    for name, row in meta.items():
        p = stage / name.lstrip('/')
        if not p.is_symlink(): p.chmod(row['mode'] & 0o7777)
    final = inventory(stage)
    changed = {n for n in upstream if final.get(n) != upstream[n]}
    assert changed == overrides | {'www/Lang_Hdr.txt'}, changed
    assert sha(stage / 'usr/libexec/localmod/rc.vendor') == sha(original / 'sbin/rc')
    assert sha(stage / 'usr/libexec/localmod/httpd') == sha(original / 'usr/sbin/httpd')
    stage_sha = hashlib.sha256(encoded(final)).hexdigest()
    (work / 'metadata.json').write_text(json.dumps(meta, indent=2) + '\n')
    name = 'RT-AX86U_3004_388.13_0_localmod_native_P7_' + stage_sha[:8] + '_NOT_FLASH_READY.w'
    image = ROOT / 'output' / name; assert not image.exists()
    output = ROOT / 'build/model-draft-results' / ('run-' + secrets.token_hex(12))
    receipt = {}; original_job = model_private.ModelJob
    class Job(original_job):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            dest = self.workspace / 'build/casefs/rootfs'
            shutil.rmtree(dest); model_private.copy_tree(stage, dest)
            assert model_private.tree_inventory(dest) == model_private.tree_inventory(stage)
            self.sources['build/casefs/rootfs'] = hashlib.sha256(encoded(model_private.tree_inventory(stage))).hexdigest()
            self.before = self.immutable(); self.manifest_sha256 = hashlib.sha256(encoded(self.before)).hexdigest()
            (self.job / 'manifest.json').write_bytes(encoded(self.before))
    model_private.ModelJob = Job
    job = ('set -eu\nmkdir /tmp/native-rootfs\ncp -a /work/build/casefs/rootfs/. /tmp/native-rootfs/\nmkfs.ubifs ' +
        ' '.join(mkfs_flags()) + ' -r /tmp/native-rootfs -o /work/build/localmod-rootfs.ubifs\necho NATIVE_CANDIDATE_UBIFS_BUILT\n').encode()
    console = model_private.run_model('build', timeout=180, guest_script=job, receipt=receipt, output_root=output)
    (ROOT / 'output/merlin38813_native_candidate_build.log').write_text(console)
    base = ROOT / pin['archive']['image']; assert sha(base) == pin['archive']['image_sha256']
    packed, packing = repack(base.read_bytes(), (output / 'localmod-rootfs.ubifs').read_bytes())
    image.write_bytes(packed); packing['image'] = str(image.relative_to(ROOT))
    image.with_suffix('.build.json').write_text(json.dumps(packing, indent=2) + '\n')
    volumes = work / 'readback-volumes'
    subprocess.run([sys.executable, str(ROOT / 'build/inspect_upstream.py'), str(image), str(volumes)], check=True, stdout=subprocess.DEVNULL)
    layout = json.loads((volumes / 'layout.json').read_text())
    assert layout['whole_crc_valid'] and not any(k.endswith('_bad') and v for k, v in layout['checks'].items())
    parsed = ubifs(ubi_file(str(volumes / 'rootfs_ubifs'), 126976)); nodes, bad, actual_meta = {}, [], {}
    walk.index(parsed, parsed.master_node.root_lnum, parsed.master_node.root_offs, nodes, bad); assert not bad
    def visit(number, path):
        node = nodes[number]; ino = node['ino']
        actual_meta[path] = dict(mode=ino.mode, uid=ino.uid, gid=ino.gid, xattr_count=getattr(ino, 'xattr_cnt', 0))
        for d in node.get('dent', []): visit(d.inum, path.rstrip('/') + '/' + d.name)
    visit(1, '/')
    assert set(actual_meta) == set(meta)
    for path, row in actual_meta.items():
        assert row == {k: meta[path][k] for k in row}, path
    fresh = work / 'readback-rootfs'; fresh.mkdir(); extract_files(parsed, str(fresh))
    content = lambda rows: {n: {k: v for k, v in row.items() if k != 'mode'} for n, row in rows.items()}
    assert content(inventory(fresh)) == content(final)
    assert final == inventory(stage) and upstream == inventory(original)
    assert protected == {n: sha(ROOT / n) for n in protected}
    report = dict(status='NATIVE_MERLIN_CANDIDATE_BUILT_READBACK_PASS_NOT_FLASH_READY',
        image=packing, rootfs=str(stage.relative_to(ROOT)), metadata=str((work / 'metadata.json').relative_to(ROOT)),
        stage_inventory_sha256=stage_sha, inventory_sha256=stage_sha, readback_entries=len(final),
        full_content_links_modes_owners_readback_verified=True, native_boot_and_kernel_region_retained=True,
        upstream_tag=pin['source_tag'], upstream_commit=pin['source_commit'],
        upstream_image_sha256=pin['archive']['image_sha256'], upstream_paths_changed=sorted(changed),
        overlay_donor_sha256=prior['image']['sha256'], protected_sha256=protected, build_vm=receipt,
        physical_router_flashed=False, target_pid1_boot_tested=False, actual_uu_acceleration_tested=False,
        source_sha256={str(p.relative_to(ROOT)): sha(p) for p in [HERE / 'build_candidate.py', HERE / 'release.json', HERE / 'native_boot_bridge.c', HERE / 'native_launcher.c', HERE / 'native_restore.c', HERE / 'center_sleep.c', HERE / 'gui24447.py', ROOT / 'sources/localmod/httpd_bridge.c', ROOT / 'sources/localmod/launcher.c', ROOT / 'sources/localmod/Lang_Hdr.txt', ROOT / 'build/asus24447_sources.json', ROOT / 'build/merlin38813_sources.json']})
    (work / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    for suffix in ['native_candidate_tests', 'native_preview_stage']:
        (ROOT / ('output/merlin38813_' + suffix + '.json')).write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'], name, len(final), 'paths', flush=True)


if __name__ == '__main__':
    main()
