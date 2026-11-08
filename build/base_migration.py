#!/usr/bin/env python3
"""Read-only official-base migration audit; never edits staging or release config."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import struct
import subprocess
from elftools.elf.elffile import ELFFile
from ubireader.ubi_io import ubi_file
from ubireader.ubifs import ubifs, walk
from ubireader.ubifs.output import extract_files
from sealed_vm import ROOT, inventory, encoded, sha
from device_config import DEVICE, DEVICE_INPUTS, leb_size, model_from_image

PINS = ROOT / DEVICE['base']['contracts']
CRITICAL = ['sbin/rc', 'usr/sbin/httpd', 'usr/lib/libssl.so.1.1', 'usr/lib/libcrypto.so.1.1', 'usr/lib/libshared.so',
            'lib/ld-linux.so.3', 'lib/libc.so.6', 'usr/sbin/openssl', 'usr/sbin/gencert.sh',
            'usr/sbin/wget', 'usr/sbin/curl', 'usr/sbin/xtables-multi', 'bin/busybox', 'bin/nvram',
            'www/Main_Login.asp', 'www/UUAccelerator.asp', 'www/state.js', 'rom/etc/profile']
RC_IMPORTS = {'nvram_get', 'nvram_set', 'strsep', 'mount', 'umount', 'umount2', 'sigwaitinfo', '_eval'}
HTTP_EXPORTS = {'auth_result', 'url_do_auth', 'ej_handlers'}
SSL_EXPORTS = {'SSL_read', 'SSL_get_error', 'SSL_get_fd', 'SSL_accept', 'SSL_get_SSL_CTX',
               'SSL_CTX_ctrl', 'SSL_CTX_get_timeout', 'SSL_CTX_set_timeout'}


def metadata(image):
    inodes, bad = {}, []
    walk.index(image, image.master_node.root_lnum, image.master_node.root_offs, inodes, bad)
    assert not bad, 'Unreadable UBIFS index nodes'
    result = {}
    def visit(number, path):
        node = inodes[number]
        result[path] = {k: getattr(node['ino'], k) for k in ['mode', 'uid', 'gid']}
        for dent in node.get('dent', []):
            visit(dent.inum, path.rstrip('/') + '/' + dent.name)
    visit(1, '/')
    return result


def tree(folder, meta):
    data = inventory(folder)
    result = {}
    for name, item in data.items():
        entry = dict(item)
        entry.pop('mode')
        entry.update({k: meta['/' + name][k] for k in ['mode', 'uid', 'gid']})
        result[name] = entry
    result['/'] = dict(type='directory', **{k: meta['/'][k] for k in ['mode', 'uid', 'gid']})
    assert set(meta) == {'/' + p if p != '/' else '/' for p in result}
    return result


def elf(path):
    # These named ABI anchors are regular files in the pinned base. Refuse
    # symbolic substitutes rather than following a target outside extraction.
    assert path.is_file() and not path.is_symlink(), 'Missing regular ELF: ' + str(path)
    with path.open('rb') as f:
        e = ELFFile(f)
        symbols = list(e.get_section_by_name('.dynsym').iter_symbols())
        return dict(machine=e['e_machine'], bits=e.elfclass, little_endian=e.little_endian,
                    imports=sorted({s.name for s in symbols if s['st_shndx'] == 'SHN_UNDEF'}),
                    exports=sorted({s.name for s in symbols if s['st_shndx'] != 'SHN_UNDEF'}),
                    needed=sorted(t.needed for s in e.iter_sections() if s.name == '.dynamic'
                                  for t in s.iter_tags() if t.entry.d_tag == 'DT_NEEDED'))


def contracts(folder, entries):
    errors, objects = [], {}
    required = {'sbin/rc': ('imports', RC_IMPORTS), 'usr/sbin/httpd': ('exports', HTTP_EXPORTS),
                'usr/lib/libssl.so.1.1': ('exports', SSL_EXPORTS),
                'usr/lib/libshared.so': ('exports', {'check_if_file_exist'})}
    for name, (side, symbols) in required.items():
        try:
            obj = elf(folder / name)
            objects[name] = obj
            abi=DEVICE['abi']
            if (obj['machine'], obj['bits'], obj['little_endian']) != (abi['elf_machine'], abi['bits'], abi['little_endian']):
                errors.append(name + ': ARM32 little-endian ABI required')
            missing = symbols - set(obj[side])
            if missing:
                errors.append(name + ': missing ' + ','.join(sorted(missing)))
        except Exception as error:
            errors.append(name + ': ' + str(error))
    for name in CRITICAL:
        if name not in entries or entries[name]['type'] != 'file':
            errors.append(name + ': required regular file missing')
    for name, needles in {'sbin/rc': [b'router.uu.163.com', b'uuplugin'],
                          'www/UUAccelerator.asp': [b'uu_accel'],
                          'www/Main_Login.asp': [b'login_authorization']}.items():
        if name in entries and entries[name]['type'] == 'file':
            raw = (folder / name).read_bytes()
            for needle in needles:
                if needle not in raw:
                    errors.append(name + ': expected flow marker missing: ' + needle.decode())
    return errors, objects


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--image', type=Path)
    ap.add_argument('--output', type=Path, default=ROOT / 'output/base_migration_tests.json')
    args = ap.parse_args()
    os.chdir(ROOT)
    source_names = ['build/base_migration.py', DEVICE['base']['contracts'], 'build/inspect_upstream.py', 'build/sealed_vm.py'] + DEVICE_INPUTS
    source_inputs = {p: sha(ROOT / p) for p in source_names}
    protected = ['build/release_config.json', 'build/dependencies.lock.json', 'upstream/official/metadata.json']
    before = {p: sha(ROOT / p) for p in protected}
    pins = json.loads(PINS.read_text())
    assert pins['model']==DEVICE['model'] and pins['image']==DEVICE['base']['vendor_image'], 'Device/base contracts mismatch'
    lock = json.loads((ROOT / 'build/dependencies.lock.json').read_text())
    assert pins['image_sha256'] == lock['files'][pins['image']]['sha256']
    assert sha(ROOT / pins['image']) == pins['image_sha256']
    assert sha(ROOT / 'upstream/official/metadata.json') == lock['files']['upstream/official/metadata.json']['sha256']
    baseline_root = ROOT / 'build/casefs/official_rootfs'
    baseline = tree(baseline_root, json.loads((ROOT / 'upstream/official/metadata.json').read_text()))
    assert hashlib.sha256(encoded(baseline)).hexdigest() == pins['tree_sha256'], 'Pinned official extraction changed'
    assert {p: baseline[p]['sha256'] for p in CRITICAL} == pins['critical_sha256']
    path = (args.image or ROOT / pins['image']).resolve()
    geometry=DEVICE['image']
    assert geometry['min_image_bytes'] <= path.stat().st_size <= geometry['max_image_bytes']
    raw = path.read_bytes()
    image_sha256 = hashlib.sha256(raw).hexdigest()
    model_ok = model_from_image(raw) == DEVICE['model']
    assert model_ok, 'Model footer mismatch: expected ' + DEVICE['model']
    parent = ROOT / 'build/casefs/migration-private'
    assert not parent.is_symlink() and (ROOT / 'build/casefs').is_mount()
    parent.mkdir(mode=0o700, exist_ok=True)
    parent.chmod(0o700)
    job = parent / ('audit-' + secrets.token_hex(12))
    job.mkdir(mode=0o700)
    try:
        subprocess.run([str(ROOT / 'analysis/.venv/bin/python'), 'build/inspect_upstream.py', str(path), str(job)],
                       check=True, stdout=subprocess.DEVNULL)
        layout = json.loads((job / 'layout.json').read_text())
        assert layout['sha256'] == image_sha256, 'Selected image changed before carving'
        assert layout['whole_crc_valid'] and not any(k.endswith('_bad') and v for k, v in layout['checks'].items())
        volume = job / DEVICE['image']['rootfs_volume_name']
        assert volume.is_file() and struct.unpack_from('<I', volume.read_bytes(), 80)[0] == geometry['ubifs_format']
        parsed = ubifs(ubi_file(str(volume), leb_size()))
        meta = metadata(parsed)
        assert len(meta) <= 20000
        for name in meta:
            assert name.startswith('/') and len(name) <= 4096
            parts = name.split('/')[1:]
            assert name == '/' or all(p and p not in {'.', '..'} and '\0' not in p for p in parts)
            for index in range(1, len(parts)):
                parent_name = '/' + '/'.join(parts[:index])
                assert meta[parent_name]['mode'] & 0o170000 == 0o040000, 'Extraction parent is not a directory'
        folder = job / 'rootfs'
        folder.mkdir()
        extract_files(parsed, str(folder))
        target = tree(folder, meta)
        errors, objects = contracts(folder, target)
        changes = [dict(path=p, before=baseline.get(p), after=target.get(p))
                   for p in sorted(set(baseline) | set(target)) if baseline.get(p) != target.get(p)]
        if image_sha256 == pins['image_sha256']:
            assert not changes, 'Identical official image must have an identical extracted inventory'
        checks = dict(pinned_baseline_verified=True, candidate_image_carved_and_crc_verified=True,
                      candidate_rootfs_and_metadata_extracted_from_selected_image=True, model_footer_matches=True,
                      required_abi_and_flow_anchors_present=not errors)
        checks['same_image_has_identical_tree_or_different_base_is_reported'] = image_sha256 != pins['image_sha256'] or not changes
        # Deterministic failure controls exercise the same contract checker.
        for removed in ['usr/lib/libssl.so.1.1', 'sbin/rc', 'www/UUAccelerator.asp']:
            altered = dict(target)
            altered.pop(removed, None)
            refused, _ = contracts(folder, altered)
            assert any(removed in e for e in refused), removed
            checks['missing_' + removed.replace('/', '_') + '_refused'] = True
        # Mutate only freshly extracted, disposable ELF bytes. Nothing is
        # executed; both controls use the same production contract parser.
        rc_path = folder / 'sbin/rc'
        original = rc_path.read_bytes()
        changed = bytearray(original)
        struct.pack_into('<H', changed, 18, 183)
        try:
            rc_path.write_bytes(changed)
            refused, _ = contracts(folder, target)
            assert any('ARM32 little-endian ABI required' in e for e in refused)
            checks['wrong_elf_machine_refused'] = True
        finally:
            rc_path.write_bytes(original)
        ssl_path = folder / 'usr/lib/libssl.so.1.1'
        original = ssl_path.read_bytes()
        assert b'SSL_CTX_ctrl\0' in original
        try:
            ssl_path.write_bytes(original.replace(b'SSL_CTX_ctrl\0', b'SSL_CTX_xtrl\0'))
            refused, _ = contracts(folder, target)
            assert any('missing SSL_CTX_ctrl' in e for e in refused)
            checks['missing_actual_tls_symbol_refused'] = True
        finally:
            ssl_path.write_bytes(original)
        assert tree(folder, meta) == target, 'Control mutations were not restored'
        assert before == {p: sha(ROOT / p) for p in before}
        assert source_inputs == {p: sha(ROOT / p) for p in source_inputs}
        assert sha(ROOT / pins['image']) == pins['image_sha256'] and sha(path) == image_sha256
        checks['release_config_and_dependency_pins_unchanged'] = True
        checks['selected_image_and_audit_sources_unchanged'] = True
        report = dict(schema=1, status='LOCAL_BASE_MIGRATION_AUDIT_PASS' if not errors else 'BASE_ADAPTATION_REQUIRED',
                      baseline_image=pins['image'], baseline_sha256=pins['image_sha256'],
                      candidate_image=str(path), candidate_sha256=image_sha256, candidate_is_pinned_base=image_sha256 == pins['image_sha256'],
                      checks=checks, errors=errors, changes=changes, changed_paths=len(changes),
                      critical_changes=[p for p in CRITICAL if baseline.get(p) != target.get(p)],
                      boot_region_changed=raw[2*geometry['peb_size']:geometry['rootfs_offset']] != (ROOT / pins['image']).read_bytes()[2*geometry['peb_size']:geometry['rootfs_offset']],
                      kernel_module_changes=[x['path'] for x in changes if x['path'].startswith('lib/modules/')],
                      elf_contracts=objects, source_sha256=source_inputs,
                      rebuild_required=image_sha256 != pins['image_sha256'], automatic_migration_or_flash=False,
                      limits=['ABI symbol presence is a prerequisite, not proof of authentication/TLS/UU or plugin compatibility',
                              'Any different official image requires explicit dependency/release updates, a new stage/build/readback and all local gates',
                              'Kernel/Wi-Fi/NAT, real UU/proxy traffic, physical upgrade and power-loss still require device acceptance'])
        args.output.write_text(json.dumps(report, indent=2) + '\n')
        if errors:
            raise RuntimeError('Base contract changes require review: ' + '; '.join(errors))
        shutil.rmtree(job)
        print('PASS official-base audit;', len(changes), 'changed paths; no automatic configuration changes', flush=True)
    except BaseException:
        print('Base audit stopped; owned extraction retained at', job, flush=True)
        raise


if __name__ == '__main__':
    main()
