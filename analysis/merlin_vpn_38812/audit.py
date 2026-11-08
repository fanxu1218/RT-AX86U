#!/usr/bin/env python3
"""Fresh image readback and source-to-target VPN contract map, without execution."""
import hashlib,json,re,secrets,struct,subprocess,sys,zipfile
from pathlib import Path
from elftools.elf.elffile import ELFFile
from ubireader.ubi_io import ubi_file
from ubireader.ubifs import ubifs,walk
from ubireader.ubifs.output import extract_files
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'build'))
from sealed_vm import inventory,encoded,sha
def elf(p):
 with p.open('rb') as f:
  e=ELFFile(f);s=list(e.get_section_by_name('.dynsym').iter_symbols())
  loads=[dict(offset=x['p_offset'],address=x['p_vaddr'],alignment=x['p_align']) for x in e.iter_segments() if x['p_type']=='PT_LOAD']
  assert all(x['alignment']<=1 or (x['address']-x['offset'])%x['alignment']==0 for x in loads)
  return dict(bits=e.elfclass,machine=e['e_machine'],exports=sorted(x.name for x in s if x['st_shndx']!='SHN_UNDEF'),imports=sorted(x.name for x in s if x['st_shndx']=='SHN_UNDEF'),load_segments=loads)
def handlers(p):
 b=p.read_bytes()
 with p.open('rb') as f:
  e=ELFFile(f)
  def off(a):return next(a-s['p_vaddr']+s['p_offset'] for s in e.iter_segments() if s['p_type']=='PT_LOAD' and s['p_vaddr']<=a<s['p_vaddr']+s['p_filesz'])
  sym=e.get_section_by_name('.dynsym').get_symbol_by_name('ej_handlers')[0];rows=[]
  for pos in range(off(sym['st_value']),off(sym['st_value'])+sym['st_size'],8):
   ptr,fn=struct.unpack_from('<II',b,pos)
   if not ptr:break
   q=off(ptr);rows.append(b[q:b.index(0,q)].decode())
  return set(rows)
def main():
 pin=json.loads((ROOT/'build/merlin_sources.json').read_text());a=pin['archive'];vendor=HERE/'vendor'
 for n in ['zip','image']:assert sha(ROOT/a[n])==a[n+'_sha256']
 with zipfile.ZipFile(ROOT/a['zip']) as z:assert z.testzip() is None
 dl=json.loads((vendor/'sources.json').read_text())
 for row in dl['files']:assert sha(vendor/Path(row['path']).name)==row['sha256']
 parent=ROOT/'build/casefs';assert parent.is_mount()
 job=parent/('merlin-vpn-input-'+secrets.token_hex(8));job.mkdir()
 subprocess.run(['python3',str(ROOT/'build/inspect_upstream.py'),str(ROOT/a['image']),str(job/'volumes')],check=True,stdout=subprocess.DEVNULL)
 layout=json.loads((job/'volumes/layout.json').read_text());assert layout['whole_crc_valid'] and not any(k.endswith('_bad') and v for k,v in layout['checks'].items())
 parsed=ubifs(ubi_file(str(job/'volumes/rootfs_ubifs'),126976));inodes={};bad=[]
 walk.index(parsed,parsed.master_node.root_lnum,parsed.master_node.root_offs,inodes,bad);assert not bad
 fresh=job/'rootfs';fresh.mkdir();extract_files(parsed,str(fresh))
 inv=inventory(fresh);cache=inventory(ROOT/'build/casefs/merlin38812_rootfs')
 def content(tree):return {n:{k:v for k,v in r.items() if k!='mode'} for n,r in tree.items()}
 fresh_content,cached_content=content(inv),content(cache)
 differences=[n for n in set(inv)|set(cache) if fresh_content.get(n)!=cached_content.get(n)]
 assert not differences,('Cached upstream extraction differs from fresh image',differences[:10])
 names=['usr/lib/libovpn.so','usr/lib/libshared.so','usr/lib/libcrypto.so.1.1','usr/lib/libssl.so.1.1','usr/sbin/httpd','sbin/rc']
 artifacts={n:dict(sha256=sha(fresh/n),elf=elf(fresh/n)) for n in names}
 official=ROOT/'build/casefs/official_rootfs';native_handlers=handlers(fresh/'usr/sbin/httpd');factory_handlers=handlers(official/'usr/sbin/httpd')
 pages={}
 for name in ['Advanced_OpenVPNClient_Content.asp','Advanced_VPN_OpenVPN.asp','Advanced_VPNDirector.asp','DNSDirector.asp','Advanced_VPNStatus.asp','ajax_vpn_status.asp']:
  p=fresh/'www'/name;assert p.is_file();text=p.read_text(errors='replace');calls=sorted(set(re.findall(r'<%\s*(\w+)\s*\(',text)))
  pages[name]=dict(sha256=sha(p),bytes=p.stat().st_size,direct_asp_handlers=calls,missing_from_factory_handlers=sorted(set(calls)-factory_handlers),missing_from_merlin_handlers=sorted(set(calls)-native_handlers),copied_to_production_ui=False)
 source=(vendor/'openvpn_control.c').read_text();start=source.index('void ovpn_start_client(int unit)');end=source.index('void ovpn_start_server(int unit)',start)
 assert 'if (getpid() != 1)' in source[start:end] and 'notify_rc(buffer)' in source[start:end]
 assert 'killall_tk_period_wait' in artifacts['usr/lib/libshared.so']['elf']['exports'] and 'killall_tk_period_wait' not in elf(official/'usr/lib/libshared.so')['exports']
 report=dict(status='MERLIN_38812_MIGRATION_CONTRACTS_AUDITED',source_tag=pin['source_tag'],source_commit=pin['source_commit'],image_sha256=a['image_sha256'],zip_crc_verified=True,whole_image_and_ubi_crc_verified=True,fresh_ubifs_readback=True,upstream_tree_entries=len(inv),upstream_content_tree_sha256=hashlib.sha256(encoded(content(inv))).hexdigest(),cached_source_matches_fresh_image=True,artifacts=artifacts,vpn_pages=pages,merlin_only_asp_handlers=sorted(native_handlers-factory_handlers),call_chain=['Merlin VPN ASP/JavaScript','Merlin httpd ASP handlers and apply/upload endpoints','libovpn configuration and key APIs','PID1 native rc service dispatch','libovpn start/stop, routing, firewall and DNS hooks','OpenVPN2.7 runtime and callbacks'],pid1_native_dispatch_required=True,factory_uu_retention_priority=True,current_strategy="retain_factory_base_and_port_in_phases",whole_firmware_upgraded=False,unimplemented=['Native Merlin VPN page rendering and write APIs behind retained factory authentication','Profile/key/custom-directive migration with rollback','PID1 start/stop dispatch and all native VPN callbacks','VPN Director and DNS Director policy integration','Other Merlin UI/services and hardware-dependent features'],source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [HERE/'audit.py',ROOT/'build/inspect_upstream.py',ROOT/'build/merlin_sources.json',vendor/'sources.json']},limits=['Fresh static readback and ABI contracts do not prove functional migration','Presence of direct ASP handler names does not verify semantics, dynamic JavaScript hooks or endpoints','No actual router, real UU account or game traffic accessed'])
 (ROOT/'output/merlin38812_migration_contracts.json').write_text(json.dumps(report,indent=2)+'\n')
 print(report['status'],len(inv),'upstream entries; all source-cache bytes match fresh pinned image')
if __name__=='__main__':main()
