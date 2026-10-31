#!/usr/bin/env python3
"""Round-trip verification of the generated UBI/UBIFS candidate, not a boot test."""
import argparse
import hashlib
import json
import os
import struct
import zlib
from pathlib import Path
from ubireader.ubi_io import ubi_file
from ubireader.ubifs import ubifs,walk
from ubireader.ubifs.output import extract_files

ap=argparse.ArgumentParser();ap.add_argument('image',type=Path);ap.add_argument('report',type=Path);a=ap.parse_args()
root=Path(__file__).resolve().parent.parent
stage=root/'build/casefs/rootfs';target=root/'build/casefs/roundtrip'
assert not target.exists();target.mkdir()
volume=root/'output/recheck/rootfs_ubifs'
image=ubifs(ubi_file(str(volume),126976));extract_files(image,str(target))
expected={'/'+str(p.relative_to(stage)) for p in stage.rglob('*')}|{'/'}
actual={'/'+str(p.relative_to(target)) for p in target.rglob('*')}|{'/'}
errors=[]
for p in sorted(expected|actual):
    if p not in expected or p not in actual:errors.append(['path',p]);continue
    left,right=stage/p.lstrip('/'),target/p.lstrip('/')
    if left.is_symlink():
        if not right.is_symlink() or os.readlink(left)!=os.readlink(right):errors.append(['symlink',p])
    elif left.is_file():
        if not right.is_file() or hashlib.sha256(left.read_bytes()).digest()!=hashlib.sha256(right.read_bytes()).digest():errors.append(['content',p])
    elif not right.is_dir():errors.append(['type',p])
# Independently read metadata from inode nodes, rather than the host extraction.
inodes={};bad=[];walk.index(image,image.master_node.root_lnum,image.master_node.root_offs,inodes,bad)
meta={}
def visit(number,path):
    node=inodes[number];i=node['ino'];meta[path]={k:getattr(i,k) for k in ['mode','uid','gid','xattr_cnt']}
    for dent in node.get('dent',[]):visit(dent.inum,path.rstrip('/')+'/'+dent.name)
visit(1,'/')
source_meta=json.loads((root/'build/staged_metadata.json').read_text())
for p in expected:
    for k in ['mode','uid','gid']:
        if source_meta[p][k]!=meta[p][k]:errors.append(['metadata',p,k,source_meta[p][k],meta[p][k]])
    if meta[p]['xattr_cnt']!=0:errors.append(['unexpected_xattr',p,meta[p]['xattr_cnt']])
raw=a.image.read_bytes();vendor=(root/'upstream/RT-AX86U_3.0.0.4_388_24437-g81951d7_pureubi.w').read_bytes()
crc=lambda b:zlib.crc32(b)^0xffffffff
valid_table=0
for off in [4096,131072+4096]:
    for n in range(128):
        row=raw[off+n*172:off+(n+1)*172]
        if crc(row[:168])!=struct.unpack_from('>I',row,168)[0]:errors.append(['volume_table_crc',off,n])
        else:valid_table+=1
volume_data=volume.read_bytes();pos=0;valid_nodes=0;bad_nodes=[]
while True:
    pos=volume_data.find(b'1\x18\x10\x06',pos)
    if pos<0:break
    if pos+24<=len(volume_data):
        length=struct.unpack_from('<I',volume_data,pos+16)[0];typ=volume_data[pos+20]
        if 24<=length<=126976 and typ<=13 and pos//126976==(pos+length-1)//126976 and pos+length<=len(volume_data):
            if crc(volume_data[pos+8:pos+length])==struct.unpack_from('<I',volume_data,pos+4)[0]:valid_nodes+=1
            else:bad_nodes.append(pos)
    pos+=4
layout=json.loads((root/'output/structure.json').read_text())
checks={
 'all_paths_present':expected==actual,'all_contents_links_and_metadata_match':not errors,
 'no_unreadable_ubifs_blocks':not bad,'ubifs_nodes_crc_valid':not bad_nodes,
 'ubi_headers_crc_valid':not any(k.endswith('_bad') and v for k,v in layout['checks'].items()),
 'whole_image_crc_valid':layout['whole_crc_valid'],
 'all_volume_table_crc_valid':valid_table==256,
 'vendor_boot_region_identical':raw[2*131072:0x400000]==vendor[2*131072:0x400000],
 'vendor_model_footer_identical':raw[-84:-20]==vendor[-84:-20],
 'vendor_rc_identical':(target/'usr/libexec/localmod/rc.vendor').read_bytes()==(root/'build/casefs/official_rootfs/sbin/rc').read_bytes(),
 'vendor_xtables_identical':(target/'usr/sbin/xtables-multi').read_bytes()==(root/'build/casefs/official_rootfs/usr/sbin/xtables-multi').read_bytes(),
 'vendor_uu_page_identical':(target/'www/UUAccelerator.asp').read_bytes()==(root/'build/casefs/official_rootfs/www/UUAccelerator.asp').read_bytes(),
 'vendor_httpd_retained':(target/'usr/libexec/localmod/httpd').read_bytes()==(root/'build/casefs/official_rootfs/usr/sbin/httpd').read_bytes(),
 'vendor_busybox_retained':(target/'bin/busybox').read_bytes()==(root/'build/casefs/official_rootfs/bin/busybox').read_bytes(),
 'vendor_curl_retained':(target/'usr/sbin/curl').read_bytes()==(root/'build/casefs/official_rootfs/usr/sbin/curl').read_bytes(),
 'vendor_kernel_modules_identical':all(p.read_bytes()==(target/p.relative_to(root/'build/casefs/official_rootfs')).read_bytes() for p in (root/'build/casefs/official_rootfs/lib/modules').rglob('*') if p.is_file() and not p.is_symlink()),
 'ubifs_format_4':struct.unpack_from('<I',volume_data,80)[0]==4,
 'no_host_extended_attributes':all(x['xattr_cnt']==0 for x in meta.values()),
}
report={'image':str(a.image),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'status':'EXPERIMENTAL_NOT_DEVICE_TESTED',
        'path_count':len(actual),'valid_ubifs_nodes':valid_nodes,'valid_volume_table_rows':valid_table,
        'checks':checks,'errors':errors,'bad_ubifs_nodes':bad_nodes,
        'not_tested':['physical boot and flash acceptance','real vendor login/TLS and rc event flow on the router','Wi-Fi/NAT and stock 1.4.12.2 xtables on target kernel 4.1','third-party plugins beyond the three pinned locally isolated packages','UU account and actual acceleration']}
a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
assert all(checks.values()), 'Candidate verification failed; see report'
