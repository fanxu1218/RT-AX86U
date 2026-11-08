#!/usr/bin/env python3
"""Read the target IKCONFIG from the pinned image; execute no router code."""
import gzip,hashlib,json,lzma,struct,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def digest(data):return hashlib.sha256(data).hexdigest()
def carve_kernel(image):
 peb,payload=131072,4096
 start=image.index(b'UBI#');blocks=[]
 table=image[start+payload+10*172:start+payload+11*172]
 assert table[16:16+struct.unpack_from('>H',table,14)[0]]==b'filestruct_full.bin'
 assert (zlib.crc32(table[:168])^0xffffffff)==struct.unpack_from('>I',table,168)[0]
 for off in range(start,len(image)-peb+1,peb):
  vid=image[off+2048:off+2112]
  if struct.unpack_from('>I',vid,8)[0]!=10:continue
  ec=image[off:off+64]
  assert ec[:4]==b'UBI#' and vid[:4]==b'UBI!'
  assert all((zlib.crc32(h[:60])^0xffffffff)==struct.unpack_from('>I',h,60)[0] for h in [ec,vid])
  assert vid[5]==2
  number,size=struct.unpack_from('>I',vid,12)[0],struct.unpack_from('>I',vid,20)[0]
  data=image[off+payload:off+payload+size]
  assert (zlib.crc32(data)^0xffffffff)==struct.unpack_from('>I',vid,32)[0]
  blocks.append((number,data))
 blocks.sort();assert [n for n,_ in blocks]==list(range(len(blocks)))
 raw=b''.join(b for _,b in blocks);offset=0;kernel=None
 while offset+16<=len(raw):
  total,header,size,crc=struct.unpack_from('>IIII',raw,offset)
  if not total or total>len(raw)-offset or not 8<=header<=total:break
  name=raw[offset+16:offset+8+header].split(b'\0')[0]
  data=raw[offset+8+header:offset+8+header+size]
  assert len(data)==size
  if name==b'vmlinux.lz':assert kernel is None;kernel=data
  offset+=total+4
 assert kernel is not None and kernel[12:16]==b'BRCM'
 return raw,kernel,len(blocks)
def main():
 config=json.loads((ROOT/'build/release_config.json').read_text())
 gate=json.loads((ROOT/'output/release_gates.json').read_text())
 lock=json.loads((ROOT/'build/dependencies.lock.json').read_text())
 vendor=(ROOT/config['vendor_image']).read_bytes();candidate=(ROOT/config['image']).read_bytes()
 assert digest(vendor)==lock['files'][config['vendor_image']]['sha256']
 assert digest(candidate)==gate['candidate_sha256'] and config['revision']=='r9-r2'
 vraw,vkernel,vblocks=carve_kernel(vendor);craw,ckernel,cblocks=carve_kernel(candidate)
 assert vraw==craw and vkernel==ckernel and vblocks==cblocks
 kernel=lzma.decompress(ckernel[20:]);begin=kernel.index(b'IKCFG_ST')+8;end=kernel.index(b'IKCFG_ED',begin)
 ikconfig=gzip.decompress(kernel[begin:end]);lines=ikconfig.decode().splitlines()
 assert '# Linux/arm64 4.1.52 Kernel Configuration' in lines
 assert '# CONFIG_TRANSPARENT_HUGEPAGE is not set' in lines
 assert 'CONFIG_ARM64=y' in lines and 'CONFIG_COMPAT=y' in lines
 r=dict(status='TARGET_KERNEL_CONFIGURATION_READBACK_COMPLETE',candidate_image=config['image'],candidate_sha256=digest(candidate),vendor_image=config['vendor_image'],vendor_sha256=digest(vendor),boot_volume_sha256=digest(craw),boot_static_volume_crc_verified_blocks=cblocks,kernel_compressed_sha256=digest(ckernel),kernel_decompressed_sha256=digest(kernel),ikconfig_sha256=digest(ikconfig),kernel_configuration_header='# Linux/arm64 4.1.52 Kernel Configuration',thp_enabled_in_target_kernel_build=False,target_configuration_lines=[l for l in lines if 'TRANSPARENT_HUGEPAGE' in l or l in ['CONFIG_ARM64=y','CONFIG_COMPAT=y']],vendor_and_candidate_kernel_identical=True,source_sha256={str(Path(__file__).resolve().relative_to(ROOT)):digest(Path(__file__).read_bytes()),'build/dependencies.lock.json':digest((ROOT/'build/dependencies.lock.json').read_bytes()),'build/release_config.json':digest((ROOT/'build/release_config.json').read_bytes()),'output/release_gates.json':digest((ROOT/'output/release_gates.json').read_bytes())},limits=['Static image readback, not physical boot evidence','The observed Linux6.12 THP promotion cannot be attributed to this target4.1.52 kernel build','No inference of exact target RSS, page reclaim performance or leak freedom'])
 (ROOT/'output/r9r2_diagnostic_kernel_tests.json').write_text(json.dumps(r,indent=2)+'\n')
 print(r['status'],'target THP disabled; candidate and pinned vendor kernel identical; IKCONFIG',r['ikconfig_sha256'])
if __name__=='__main__':main()
