#!/usr/bin/env python3
"""Repack only rootfs in a pure-UBI ASUS 24437 image; retain vendor boot data."""
import argparse
import hashlib
import json
import math
import struct
import zlib
from pathlib import Path

ap=argparse.ArgumentParser()
ap.add_argument('vendor',type=Path);ap.add_argument('ubifs',type=Path);ap.add_argument('output',type=Path)
a=ap.parse_args()
base=a.vendor.read_bytes();root=a.ubifs.read_bytes()
PEB=131072;DATA=4096;LEB=PEB-DATA;PREFIX=0x400000
crc=lambda b:zlib.crc32(b)^0xffffffff
assert base[:4]==b'UBI#' and (len(base)-20)%PEB==0
assert crc(base[:-20])==struct.unpack_from('<I',base,len(base)-20)[0]
assert len(root)%LEB==0 and root[:4]==b'1\x18\x10\x06'
blocks=len(root)//LEB
assert 32<blocks<2048
prefix=bytearray(base[:PREFIX])
# Layout volume copies occupy the first two PEBs. Only root volume sizing changes.
for offset in [0,PEB]:
    assert struct.unpack_from('>I',prefix,offset+2048+8)[0]==0x7fffefff
    pos=offset+DATA
    assert prefix[pos+16:pos+28]==b'rootfs_ubifs'
    assert struct.unpack_from('>I',prefix,pos+168)[0]==crc(prefix[pos:pos+168])
    struct.pack_into('>I',prefix,pos,blocks)
    struct.pack_into('>I',prefix,pos+168,crc(prefix[pos:pos+168]))
# The original EC/VID fields retain geometry, image sequence, and version.
template=bytearray(base[PREFIX:PREFIX+DATA])
assert struct.unpack_from('>I',template,2048+8)[0]==0 and template[2048+5]==1
out=bytearray(prefix)
for number in range(blocks):
    header=bytearray(template)
    struct.pack_into('>I',header,2048+12,number)
    struct.pack_into('>I',header,2048+60,crc(header[2048:2048+60]))
    out.extend(header);out.extend(root[number*LEB:(number+1)*LEB])
# ASUS embeds a 64-byte model/version descriptor in the final UBIFS padding.
assert out[-64:]==b'\xff'*64, 'Final block has no room for the vendor descriptor'
out[-64:]=base[-84:-20]
out.extend(struct.pack('<I',crc(out))+base[-16:])
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(out)
report={'image':str(a.output),'bytes':len(out),'sha256':hashlib.sha256(out).hexdigest(),
        'rootfs_lebs':blocks,'leb_size':LEB,'rootfs_fmt_version':struct.unpack_from('<I',root,80)[0],
        'vendor_boot_region_unchanged':out[2*PEB:PREFIX]==base[2*PEB:PREFIX],
        'vendor_descriptor_unchanged':out[-84:-20]==base[-84:-20],
        'vendor_wfi_parameters_unchanged':out[-16:]==base[-16:],
        'status':'EXPERIMENTAL_NOT_DEVICE_TESTED'}
assert report['vendor_boot_region_unchanged'] and report['vendor_descriptor_unchanged']
a.output.with_suffix('.build.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
