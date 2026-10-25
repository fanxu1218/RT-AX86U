#!/usr/bin/env python3
import hashlib,json,struct
from pathlib import Path
from elftools.elf.elffile import ELFFile
root=Path(__file__).resolve().parent.parent
rc=root/'build/casefs/official_rootfs/sbin/rc'
with rc.open('rb') as f:
 elf=ELFFile(f);imports={s.name for s in elf.get_section_by_name('.dynsym').iter_symbols() if s['st_shndx']=='SHN_UNDEF'}
required={'nvram_get','nvram_set','strsep','mount','umount','umount2','sigwaitinfo','_eval'}
assert required<=imports, required-imports
assert (root/'build/casefs/official_rootfs/bin/nvram').is_file(), 'Pinned vendor nvram CLI is missing'
names={}
for label in ['official','koolcenter']:
 path=root/f'build/casefs/{label}_rootfs/usr/sbin/httpd'
 with path.open('rb') as f:
  elf=ELFFile(f);data=path.read_bytes();symbol=elf.get_section_by_name('.dynsym').get_symbol_by_name('ej_handlers')[0]
  def off(address):
   return next(address-s['p_vaddr']+s['p_offset'] for s in elf.iter_segments() if s['p_type']=='PT_LOAD' and s['p_vaddr']<=address<s['p_vaddr']+s['p_filesz'])
  base=off(symbol['st_value']);names[label]=[]
  for i in range(symbol['st_size']//8):
   pointer,fn=struct.unpack_from('<II',data,base+8*i)
   if not pointer:break
   start=off(pointer);names[label].append(data[start:data.index(0,start)].decode())
extra=set(names['koolcenter'])-set(names['official'])
assert not any('dbus' in n for n in extra)
report={'vendor_rc_sha256':hashlib.sha256(rc.read_bytes()).hexdigest(),'rc_imports_verified':sorted(required),'donor_additional_asp_handlers':sorted(extra),'donor_dbus_asp_extensions':False,'scope':'Pinned RT-AX86U 24437 imports and KoolCenter 388.11_0 handler inventory; not an on-device test'}
(root/'output/vendor_contracts.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS vendor imported hook anchors; donor software center has no additional DBus ASP handlers')
