#!/usr/bin/env python3
"""Image-free profile regression tests, also run by the quick CI gate."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import shutil
import tempfile
import unittest
import zlib

from device_config import (DEVICE, DEVICES, ROOT, compiler_flags, leb_size, load_device,
                           mkfs_flags, model_from_image, render_build_job, render_source,
                           require_model, validate_device)
from release_config import CONFIG, resolve_config
from repack_image import repack


def alternate_device():
    device = copy.deepcopy(DEVICE)
    device.update(id='fixture-router', model='FIXTURE-ROUTER')
    device['base'].update(image_prefix='FIXTURE_388_1', version='ASUS fixture', display_version='fixture')
    device['abi']['cpu'] = 'cortex_a7'
    device['plugins'].update(extended_productid=device['model'], extended_marker='fixture_v8')
    device['image'].update(peb_size=32768, min_io_size=512, vid_offset=512, data_offset=1024,
                           rootfs_offset=65536, min_rootfs_lebs=2, max_lebs=64,
                           min_image_bytes=4096, max_image_bytes=1048576, journal_bytes=65536,
                           rootfs_volume_id=2, rootfs_volume_name='fixture_rootfs')
    return validate_device(device)


def synthetic_images(device):
    """Owned structural fixture, not a bootable firmware or vendor binary."""
    g = device['image']
    crc = lambda blob: zlib.crc32(blob) ^ 0xffffffff
    base = bytearray(b'\xff' * (g['rootfs_offset'] + g['peb_size']))
    count = g['min_rootfs_lebs'] + 1
    for offset in range(0, len(base), g['peb_size']):
        ec = bytearray(64)
        ec[:4] = b'UBI#'; ec[4] = 1
        struct.pack_into('>II', ec, 16, g['vid_offset'], g['data_offset'])
        struct.pack_into('>I', ec, 60, crc(ec[:60]))
        base[offset:offset+64] = ec
        vid = bytearray(64)
        vid[:4] = b'UBI!'; vid[4] = 1; vid[5] = 1
        volume = g['layout_volume_id'] if offset < 2*g['peb_size'] else g['rootfs_volume_id']
        struct.pack_into('>II', vid, 8, volume, 0)
        struct.pack_into('>I', vid, 60, crc(vid[:60]))
        at = offset + g['vid_offset']; base[at:at+64] = vid
        if offset < 2*g['peb_size']:
            table = offset + g['data_offset']
            base[table:table+128*172] = bytes(128*172)
            at = table + g['rootfs_volume_id']*172
            row = bytearray(172); name = g['rootfs_volume_name'].encode()
            struct.pack_into('>IIIBBH', row, 0, count, 1, 0, 1, 0, len(name))
            row[16:16+len(name)] = name
            struct.pack_into('>I', row, 168, crc(row[:168]))
            base[at:at+172] = row
    descriptor = bytearray(g['descriptor_size'])
    name = device['model'].encode(); at = g['model_offset']
    descriptor[at:at+len(name)] = name
    base[-g['descriptor_size']:] = descriptor
    base += struct.pack('<I', crc(base)) + bytes(16)
    root = bytearray(b'\xff' * (count * leb_size(device)))
    root[:4] = b'1\x18\x10\x06'; struct.pack_into('<I', root, 80, g['ubifs_format'])
    return bytes(base), bytes(root)


class DeviceProfiles(unittest.TestCase):
    def test_registered_profiles_and_base_contracts(self):
        for path in DEVICES.glob('*.json'):
            device = load_device(path.stem)
            pins = json.loads((ROOT/device['base']['contracts']).read_text())
            self.assertEqual((pins['model'], pins['image']), (device['model'], device['base']['vendor_image']))

    def test_existing_release_identity(self):
        self.assertEqual(CONFIG['base'], DEVICE['base']['version'])
        self.assertEqual(CONFIG['vendor_image'], DEVICE['base']['vendor_image'])
        self.assertEqual(compiler_flags(load_device('rt-ax86u')), ['-target','arm-linux-gnueabi.2.26','-mcpu=cortex_a53'])

    def test_release_cannot_mix_devices_or_override_base(self):
        raw = json.loads((ROOT/'build/release_config.json').read_text())
        for changes in [{'device':'wrong'}, {'image':'output/other.w'}, {'base':'other'}, {'vendor_image':'other.w'}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                resolve_config(dict(raw, **changes), DEVICE)

    def test_unknown_traversal_and_symlink_profiles_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            parent = Path(name)
            for value in ['unknown', '../rt-ax86u', '/rt-ax86u', '']:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    load_device(value, parent)
            (parent/'fixture.json').symlink_to(DEVICES/'rt-ax86u.json')
            with self.assertRaises(ValueError): load_device('fixture',parent)

    def test_bad_geometry_abi_and_shell_values_rejected(self):
        for section, key, value in [('abi','bits',64), ('abi','cpu','x;touch bad'),
                                    ('image','data_offset',1), ('image','rootfs_offset',1),
                                    ('image','trailer_size',24), ('image','ubifs_format',5),
                                    ('plugins','extended_productid','OTHER'),
                                    ('plugins','extended_loader','/lib/../tmp/loader'),
                                    ('base','contracts','../outside.json')]:
            with self.subTest(section=section,key=key), self.assertRaises(ValueError):
                device=copy.deepcopy(DEVICE);device[section][key]=value;validate_device(device)

    def test_alternate_device_propagates_to_build_and_pages(self):
        device=alternate_device()
        raw=json.loads((ROOT/'build/release_config.json').read_text())
        raw.update(device=device['id'],image=f"output/{device['base']['image_prefix']}_localmod2_{raw['revision'].replace('-','_')}_EXPERIMENTAL.w")
        config=resolve_config(raw,device)
        self.assertEqual(compiler_flags(device)[-1],'-mcpu=cortex_a7')
        self.assertEqual(mkfs_flags(device)[mkfs_flags(device).index('-e')+1],str(31744))
        text=render_source('sources/localmod/Module_Localmod.asp',config,device)
        self.assertIn('FIXTURE-ROUTER',text);self.assertNotIn('RT-AX86U',text)
        self.assertIn('官方 fixture',text)
        guard=render_source('sources/localmod/installer-guard.sh',device=device)
        self.assertIn('grep -qx fixture_v8',guard);self.assertIn('= FIXTURE-ROUTER',guard)

    def test_rtax86u_templates_match_pre_refactor_bytes(self):
        # Frozen r9-r2 identity: later release versions need not change this baseline.
        config=dict(CONFIG,variant='localmod2',revision='r9-r2',software_center_version='1.9.60')
        expected={
            'sources/localmod/installer-guard.sh':'ba13e554560c1d9340a39f94df9206ad093bb81f44bcfe6e0fd6c90d165809a4',
            'sources/localmod/Module_Localmod.asp':'dfea5cb799bce3af09faa311036394dad34a56b32aa620955da649fbb0ebe477',
            'sources/localmod/Module_FancyssLocalmod.asp':'15ed32f1227f971f8a3584e175e0d3596236f73cc01607dc653b15743bd81076',
        }
        device=load_device('rt-ax86u')
        for path,digest in expected.items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256(render_source(path,config,device).encode()).hexdigest(),digest)
        job=render_build_job((ROOT/'build/linux_build_job.sh').read_text(),device)
        self.assertEqual(hashlib.sha256(job.encode()).hexdigest(),'58ed32be533d6cd301f9384abe60e7ec9fc57c3335bb7c758a938eb9d95c9419')

    def test_missing_release_values_are_rejected(self):
        with self.assertRaises(ValueError): render_source('sources/localmod/Module_Localmod.asp')

    def test_rendered_plugin_gate_preserves_model_and_loader_checks(self):
        with tempfile.TemporaryDirectory() as name:
            folder=Path(name);loader=folder/'loader';loader.write_text('');loader.chmod(0o755)
            device=alternate_device();device['plugins']['extended_loader']=str(loader)
            guard=folder/'guard.sh';guard.write_text(render_source('sources/localmod/installer-guard.sh',device=device))
            for marker,model,present,accepted in [('hnd','OTHER',False,True),('fixture_v8','FIXTURE-ROUTER',True,True),
                                                   ('fixture_v8','OTHER',True,False),('fixture_v8','FIXTURE-ROUTER',False,False),
                                                   ('other','FIXTURE-ROUTER',True,False)]:
                with self.subTest(marker=marker,model=model,loader=present):
                    loader.chmod(0o755 if present else 0o644);(folder/'.valid').write_text(marker+'\n')
                    script='. "$1"; KS_STAGE=$2; TEST_MODEL=$3; nvram(){ printf "%s\\n" "$TEST_MODEL"; }; ks_platform_valid'
                    result=subprocess.run(['sh','-c',script,'fixture',str(guard),str(folder),model],capture_output=True)
                    self.assertEqual(result.returncode==0,accepted,result.stderr.decode())

    def test_repack_obeys_alternate_geometry_and_preserves_boot_and_footer(self):
        device=alternate_device();base,root=synthetic_images(device)
        image,report=repack(base,root,device)
        g=device['image']
        self.assertEqual(len(image),g['rootfs_offset']+(g['min_rootfs_lebs']+1)*g['peb_size']+20)
        self.assertEqual(model_from_image(image,device),device['model'])
        self.assertEqual(image[2*g['peb_size']:g['rootfs_offset']],base[2*g['peb_size']:g['rootfs_offset']])
        self.assertEqual(image[-84:-20],base[-84:-20]);self.assertTrue(report['vendor_descriptor_unchanged'])
        self.assertEqual(zlib.crc32(image[:-20])^0xffffffff,struct.unpack_from('<I',image,len(image)-20)[0])

    def test_rtax86u_packer_matches_pre_refactor_bytes(self):
        device=load_device('rt-ax86u');base,root=synthetic_images(device)
        image,_=repack(base,root,device)
        self.assertEqual(hashlib.sha256(image).hexdigest(),'46289d81cb9d64025eb54d47ae4a082fa731dca50926fcd68d4492797dae3ed5')

    def test_inspector_uses_selected_profile_geometry(self):
        device=alternate_device();base,root=synthetic_images(device);image,_=repack(base,root,device)
        with tempfile.TemporaryDirectory() as name:
            folder=Path(name);build=folder/'build';(build/'devices').mkdir(parents=True)
            for script in ['device_config.py','inspect_upstream.py']:
                shutil.copyfile(ROOT/'build'/script,build/script)
            (build/'devices'/f"{device['id']}.json").write_text(json.dumps(device))
            (build/'release_config.json').write_text(json.dumps({'device':device['id']}))
            source=folder/'image.w';source.write_bytes(image)
            subprocess.run(['python3',str(build/'inspect_upstream.py'),str(source),str(folder/'out')],
                           check=True,stdout=subprocess.DEVNULL)
            layout=json.loads((folder/'out/layout.json').read_text())
            self.assertTrue(layout['whole_crc_valid'])
            self.assertFalse(any(k.endswith('_bad') and v for k,v in layout['checks'].items()))
            self.assertEqual(layout['volumes'][str(device['image']['rootfs_volume_id'])]['name'],'fixture_rootfs')
            self.assertEqual((folder/'out/fixture_rootfs').stat().st_size,3*leb_size(device))

    def test_repack_rejects_wrong_model_geometry_or_rootfs(self):
        device=alternate_device();base,root=synthetic_images(device)
        with self.assertRaises(ValueError): require_model(base,DEVICE)
        with self.assertRaises(ValueError): repack(base,root,DEVICE)
        wrong=copy.deepcopy(device);wrong['image']['vid_offset']=1024
        with self.assertRaises(AssertionError): repack(base,root,wrong)
        with self.assertRaises(AssertionError): repack(base,b'BAD!'+root[4:],device)
        with self.assertRaises(AssertionError): repack(base,root[:-64]+bytes(64),device)


if __name__=='__main__':
    unittest.main(verbosity=2)
