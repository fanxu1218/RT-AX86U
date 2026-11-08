#!/usr/bin/env python3
"""Repack the selected device's pure-UBI rootfs; retain vendor boot data."""
import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path
from device_config import DEVICE, leb_size, require_model

def repack(base, root, device=DEVICE):
    g=device['image']
    PEB=g['peb_size'];DATA=g['data_offset'];VID=g['vid_offset'];LEB=leb_size(device);PREFIX=g['rootfs_offset']
    TRAILER=g['trailer_size'];DESCRIPTOR=g['descriptor_size']
    require_model(base, device)
    assert struct.unpack_from('>II',base,16)==(VID,DATA), 'Vendor UBI geometry does not match device'
    crc=lambda b:zlib.crc32(b)^0xffffffff
    assert base[:4]==b'UBI#' and (len(base)-20)%PEB==0
    assert crc(base[:-20])==struct.unpack_from('<I',base,len(base)-20)[0]
    assert len(root)%LEB==0 and root[:4]==b'1\x18\x10\x06'
    blocks=len(root)//LEB
    assert g['min_rootfs_lebs']<blocks<g['max_lebs']
    assert struct.unpack_from('<I',root,80)[0]==g['ubifs_format']
    prefix=bytearray(base[:PREFIX])
    # Layout volume copies occupy the first two PEBs. Only root volume sizing changes.
    for offset in [0,PEB]:
        assert struct.unpack_from('>I',prefix,offset+VID+8)[0]==g['layout_volume_id']
        pos=offset+DATA
        pos+=g['rootfs_volume_id']*172
        assert prefix[pos+16:pos+16+len(g['rootfs_volume_name'])]==g['rootfs_volume_name'].encode()
        assert struct.unpack_from('>I',prefix,pos+168)[0]==crc(prefix[pos:pos+168])
        struct.pack_into('>I',prefix,pos,blocks)
        struct.pack_into('>I',prefix,pos+168,crc(prefix[pos:pos+168]))
    # The original EC/VID fields retain geometry, image sequence, and version.
    template=bytearray(base[PREFIX:PREFIX+DATA])
    assert struct.unpack_from('>I',template,VID+8)[0]==g['rootfs_volume_id'] and template[VID+5]==1
    out=bytearray(prefix)
    for number in range(blocks):
        header=bytearray(template)
        struct.pack_into('>I',header,VID+12,number)
        struct.pack_into('>I',header,VID+60,crc(header[VID:VID+60]))
        out.extend(header);out.extend(root[number*LEB:(number+1)*LEB])
    # ASUS embeds a 64-byte model/version descriptor in the final UBIFS padding.
    assert out[-DESCRIPTOR:]==b'\xff'*DESCRIPTOR, 'Final block has no room for the vendor descriptor'
    out[-DESCRIPTOR:]=base[-(DESCRIPTOR+TRAILER):-TRAILER]
    out.extend(struct.pack('<I',crc(out))+base[-(TRAILER-4):])
    assert g['min_image_bytes']<=len(out)<=g['max_image_bytes'], 'Packed image exceeds device bounds'
    report={'image':None,'bytes':len(out),'sha256':hashlib.sha256(out).hexdigest(),
            'rootfs_lebs':blocks,'leb_size':LEB,'rootfs_fmt_version':struct.unpack_from('<I',root,80)[0],
            'vendor_boot_region_unchanged':out[2*PEB:PREFIX]==base[2*PEB:PREFIX],
            'vendor_descriptor_unchanged':out[-(DESCRIPTOR+TRAILER):-TRAILER]==base[-(DESCRIPTOR+TRAILER):-TRAILER],
            'vendor_wfi_parameters_unchanged':out[-16:]==base[-16:],
            'status':'EXPERIMENTAL_NOT_DEVICE_TESTED'}
    assert report['vendor_boot_region_unchanged'] and report['vendor_descriptor_unchanged']
    return bytes(out), report


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('vendor',type=Path);ap.add_argument('ubifs',type=Path);ap.add_argument('output',type=Path)
    a=ap.parse_args()
    out,report=repack(a.vendor.read_bytes(),a.ubifs.read_bytes())
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(out)
    report['image']=str(a.output)
    a.output.with_suffix('.build.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
