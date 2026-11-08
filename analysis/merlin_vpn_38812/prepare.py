#!/usr/bin/env python3
"""Prepare a private, opt-in prototype; never modify the r9-r2 stage or image."""
import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
PAYLOAD=ROOT/'build/merlin-vpn-phase1/payload'
PIN=ROOT/'build/merlin_sources.json'
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def prepare():
 sys.path.insert(0,str(ROOT/'build'))
 from prepare_merlin import validate
 validate();pin=json.loads(PIN.read_text())
 inputs=json.loads((HERE/'inputs.json').read_text())
 assert pin['source_tag']=='3004.388.12_2' and pin['source_commit']=='433fc608f5fc1689f3d3c3ab5cd2a7d57102260f'
 upstream=ROOT/'build/casefs/merlin38812_rootfs'
 assert inputs['image_sha256']==pin['archive']['image_sha256']
 for n,row in inputs['libraries'].items():assert sha(upstream/'usr/lib'/n)==row['sha256'],n
 out=PAYLOAD.parent;out.mkdir(exist_ok=True)
 private='usr/lib/localmod/vpn38812/'
 paths={private+n:'usr/lib/'+n for n in ['libovpn.so','libshared.so','libcrypto.so.1.1','libssl.so.1.1']}
 for target,origin in paths.items():
  source=upstream/origin;dest=PAYLOAD/target;dest.parent.mkdir(parents=True,exist_ok=True)
  if dest.exists():dest.chmod(0o755)
  shutil.copyfile(source,dest);dest.chmod(0o755)
  dest.chmod(0o555)
 binary=PAYLOAD/'usr/libexec/localmod/merlin-vpn-model';binary.parent.mkdir(parents=True,exist_ok=True)
 link=ROOT/'build/merlin-vpn-phase1-link-only';link.mkdir(exist_ok=True)
 for n in ['crypto','ssl']:
  p=link/('lib'+n+'.so');p.unlink(missing_ok=True);p.symlink_to(PAYLOAD/private/('lib'+n+'.so.1.1'))
 subprocess.run([str(ROOT/'sources/zig-aarch64-macos-0.15.2/zig'),'cc','-target','arm-linux-gnueabi.2.26','-mcpu=cortex_a53','-O2','-Wall','-Wextra','-Werror','-o',str(binary),str(HERE/'model.c'),'-Wl,--no-as-needed,--allow-shlib-undefined,-rpath,/usr/lib/localmod/vpn38812','-L'+str(PAYLOAD/private),'-lovpn','-lshared','-L'+str(link),'-lcrypto','-lssl','-L'+str(ROOT/'build/casefs/official_rootfs/lib'),'-lnvram','-ldl'],check=True)
 check='from elftools.elf.elffile import ELFFile;import sys,json;f=open(sys.argv[1],"rb");e=ELFFile(f);assert all(s["p_align"]<=1 or (s["p_vaddr"]-s["p_offset"])%s["p_align"]==0 for s in e.iter_segments() if s["p_type"]=="PT_LOAD");print(json.dumps([t.needed for s in e.iter_sections() if s.name==".dynamic" for t in s.iter_tags() if t.entry.d_tag=="DT_NEEDED"]))'
 needed=json.loads(subprocess.check_output([str(ROOT/'analysis/.venv/bin/python'),'-c',check,str(binary)],text=True))
 # These two upstream DSOs omit SONAME. Zig records its resolved build path;
 # shorten those entries in our new helper only, never in upstream libraries.
 for n in needed:
  if n.startswith('/'):
   assert n in {str(PAYLOAD/private/'libovpn.so'),str(PAYLOAD/private/'libshared.so')},n
   subprocess.run([str(ROOT/'build/tools/patchelf-0.18.0'),'--replace-needed',n,Path(n).name,str(binary)],check=True)
 needed=json.loads(subprocess.check_output([str(ROOT/'analysis/.venv/bin/python'),'-c',check,str(binary)],text=True))
 assert {'libovpn.so','libshared.so','libcrypto.so.1.1','libssl.so.1.1','libnvram.so'}<=set(needed),needed
 sources={str(p.relative_to(ROOT)):sha(p) for p in [HERE/'model.c',HERE/'prepare.py',HERE/'inputs.json',PIN,*sorted((HERE/'vendor').glob('*'))] if p.is_file()}
 manifest=dict(status='PRIVATE_READ_ONLY_PROTOTYPE',source_tag=pin['source_tag'],source_commit=pin['source_commit'],upstream_image_sha256=pin['archive']['image_sha256'],paths={t:dict(origin=o,upstream_sha256=sha(upstream/o),staged_sha256=sha(PAYLOAD/t)) for t,o in paths.items()},helper_sha256=sha(binary),source_sha256=sources,product_menu_registered=False,service_control_enabled=False,production_stage_modified=False,full_firmware_upgrade_complete=False)
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');return manifest
if __name__=='__main__':
 os.chdir(ROOT);print(json.dumps(prepare(),indent=2))
