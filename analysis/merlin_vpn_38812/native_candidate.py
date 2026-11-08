#!/usr/bin/env python3
"""Build/read back an independent NOT_FLASH_READY full-Merlin candidate.

This does not select a production release, publish or flash. Native target PID1,
cross-boot plugin recovery and authentic plugin coexistence remain later gates.
"""
import hashlib,json,os,re,secrets,shutil,stat,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'build'))
from sealed_vm import inventory,encoded,sha,copy_file
from device_config import mkfs_flags
import model_private
from fancyss_policy import stage_policy
from repack_image import repack
from ubireader.ubi_io import ubi_file
from ubireader.ubifs import ubifs,walk
from ubireader.ubifs.output import extract_files

def main():
 os.chdir(ROOT)
 release=json.loads((HERE/'release.json').read_text())
 assert release['model']=='RT-AX86U' and release['base']=='3004.388.12_2' and not release['flash_ready'] and not release['published']
 assert re.fullmatch(r'[a-z0-9][a-z0-9._-]{1,79}',release['release_tag'])
 parent=json.loads((ROOT/'output/merlin38812_native_preview_stage.json').read_text())
 hooks=json.loads((ROOT/'output/merlin38812_native_hooks_tests.json').read_text())
 assert hooks['status']=='LOCAL_NATIVE_MERLIN_HOOK_AUGMENTATION_PASS'
 for n in ['native_boot_bridge.c','native_launcher.c','native_restore.c','native_center_event.sh']:
  path='analysis/merlin_vpn_38812/'+n
  assert sha(ROOT/path)==hooks['source_sha256'][path],('Hook evidence must match candidate source',n)
 source=ROOT/parent['rootfs'];assert hashlib.sha256(encoded(inventory(source))).hexdigest()==parent['inventory_sha256']
 protected={n:sha(ROOT/n) for n in [*parent['protected_sha256'],'output/merlin38812_native_preview_tests.json','output/merlin38812_native_hooks_tests.json','output/merlin38812_uu_matrix_tests.json']}
 work=ROOT/'build/casefs'/('merlin-native-candidate-'+secrets.token_hex(8));work.mkdir()
 stage=work/'rootfs';shutil.copytree(source,stage,symlinks=True,copy_function=copy_file)
 meta=json.loads((ROOT/parent['metadata']).read_text());tools=work/'tools';tools.mkdir()
 cc=[str(ROOT/'sources/zig-aarch64-macos-0.15.2/zig'),'cc','-target','arm-linux-gnueabi.2.26','-mcpu=cortex_a53','-O2','-s']
 for output,n,extra in [('native_boot_bridge.so','native_boot_bridge.c',['-shared','-fPIC',str(ROOT/'sources/localmod/runtime.c'),'-ldl']),('native-rc','native_launcher.c',[]),('native-restore','native_restore.c',[str(ROOT/'sources/localmod/runtime.c')]),('compat-sleep','center_sleep.c',[])]:
  subprocess.run([*cc,'-o',str(tools/output),str(HERE/n),*extra],check=True)
 def put(src,path,mode):
  dst=stage/path;dst.parent.mkdir(parents=True,exist_ok=True)
  if dst.is_file() or dst.is_symlink():dst.unlink()
  copy_file(src,dst);dst.chmod(mode)
  meta['/'+path]=dict(mode=stat.S_IFREG|mode,uid=0,gid=0,inum=-1,nlink=1,xattr_count=0)
 put(source/'sbin/rc','usr/libexec/localmod/rc.vendor',0o500)
 put(tools/'native-rc','sbin/rc',0o500)
 put(tools/'native_boot_bridge.so','usr/lib/localmod/native_boot_bridge.so',0o444)
 put(HERE/'native_center_event.sh','usr/libexec/localmod/native-center-event.sh',0o755)
 put(tools/'native-restore','usr/sbin/iptables-restore',0o500)
 fancyss=stage_policy(source,tools,put)
 # Keep native-base labeling and planned asset URLs independent of the old
 # official-base donor's human-readable preview label.
 for path in ['www/Module_Localmod.asp','www/Module_FancyssLocalmod.asp']:
  page=(stage/path).read_text()
  if path.endswith('Module_Localmod.asp'):
   before='官方 3004.388.12_2 preview';assert page.count(before)==1
   page=page.replace(before,'Asuswrt-Merlin '+release['base']).replace('localmod2-Merlin native preview','localmod-native-'+release['revision'])
  else:
   old=re.findall(r"softcenter_home_url:'([^']+)'",page);assert len(old)==1
   home=release['repository']+'/releases/download/'+release['release_tag']
   page=page.replace(old[0],home).replace('通过原厂登录和 HTTPS 管理','通过路由器登录和 HTTPS 管理')
   before='<button id="install"';assert page.count(before)==1
   page=page.replace(before,'<p class="note">默认下载地址在对应版本发布后可用。尚未发布时，请在软件中心离线安装同批交付的兼容包。</p>\n'+before)
   assert not any(c.isspace() for c in home)
  p=tools/Path(path).name;p.write_text(page);put(p,path,meta['/'+path]['mode']&0o7777)
 # The native BusyBox sleep accepts integer seconds only. Keep the managed
 # recovery-abort wait at 100 ms using its existing usleep applet.
 bootstrap=(source/'usr/libexec/localmod/bootstrap.sh').read_text()
 assert bootstrap.count('sleep 0.1')==1
 assert (source/'bin/usleep').is_symlink()
 fixed_bootstrap=tools/'bootstrap.sh';fixed_bootstrap.write_text(bootstrap.replace('sleep 0.1','/bin/usleep 100000'))
 put(fixed_bootstrap,'usr/libexec/localmod/bootstrap.sh',0o755)
 # Give center scripts fractional-second sleep without replacing the
 # native applet or a plugin's existing /koolshare/bin/sleep. Keep this path
 # after plugin tools and before the stock shell tools.
 put(tools/'compat-sleep','usr/libexec/localmod/compat-bin/sleep',0o755)
 core_base=stage/'rom/etc/koolshare/scripts/base.sh'
 base_text=core_base.read_text();needle='export PATH=$KSROOT/bin:$KSROOT/scripts:${NEW_PATH}'
 assert base_text.count(needle)==1
 core_base.write_text(base_text.replace(needle,'export PATH=$KSROOT/bin:$KSROOT/scripts:/usr/libexec/localmod/compat-bin:${NEW_PATH}'))
 core_id=hashlib.sha256()
 for p in sorted((stage/'rom/etc/koolshare').rglob('*')):
  core_id.update(str(p.relative_to(stage/'rom/etc/koolshare')).encode())
  if p.is_symlink():core_id.update(os.readlink(p).encode())
  elif p.is_file():core_id.update(p.read_bytes())
 identity_core=stage/'rom/etc/localmod-core-id';identity_core.chmod(0o644);identity_core.write_text(core_id.hexdigest()+'\n')
 identity=stage/'rom/etc/localmod-release.json'
 identity.chmod(0o644)
 identity.write_text(json.dumps(dict(base='3004.388.12_2',variant='localmod-native-preview',
  revision=release['revision'],release_tag=release['release_tag'],status='NOT_FLASH_READY',software_center='1.9.60',
  merlin_framework='complete pinned native image with center augmentation',
  uu='native NTP callback retained; territory-gated capability; real acceleration unverified',
  automatic_center_hook_augmentation=True,target_pid1_boot_tested=False),indent=2)+'\n')
 # Restore native/donor hardlinks within this new tree, never to a source inode.
 groups={};native_paths=set(json.loads((ROOT/'upstream/merlin/metadata.json').read_text()))
 for path,row in meta.items():
  p=stage/path.lstrip('/')
  if row['inum']>=0 and stat.S_ISREG(row['mode']) and p.is_file() and not p.is_symlink():
   origin='merlin' if path in native_paths else 'center'
   groups.setdefault((origin,row['inum']),[]).append(p)
 for paths in groups.values():
  for p in paths[1:]:
   assert sha(p)==sha(paths[0]);p.unlink();os.link(paths[0],p)
 stage.chmod(meta['/']['mode']&0o7777)
 for p in stage.rglob('*'):
  name='/'+p.relative_to(stage).as_posix()
  if name not in meta:
   assert p.is_dir() and not p.is_symlink(),name
   meta[name]=dict(mode=stat.S_IFDIR|0o755,uid=0,gid=0,inum=-1,nlink=1,xattr_count=0)
  if not p.is_symlink():p.chmod(meta[name]['mode']&0o7777)
 expected=inventory(stage);stage_sha=hashlib.sha256(encoded(expected)).hexdigest()
 (work/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
 for n in ['usr/lib/libovpn.so','usr/lib/libshared.so','usr/sbin/helper.sh','www/UUAccelerator.asp','www/Advanced_OpenVPNClient_Content.asp','www/Advanced_VPNDirector.asp']:
  assert sha(stage/n)==sha(source/n),n
 assert sha(stage/'usr/libexec/localmod/rc.vendor')==sha(source/'sbin/rc')
 name='RT-AX86U_3004_388.12_2_localmod_native_'+release['revision']+'_'+stage_sha[:8]+'_NOT_FLASH_READY.w'
 image=ROOT/'output'/name;assert not image.exists(),'Keep the existing candidate for review'
 output=ROOT/'build/model-draft-results'/('run-'+secrets.token_hex(12));receipt={}
 original_job=model_private.ModelJob
 class Job(original_job):
  def __init__(self,*args,**kwargs):
   super().__init__(*args,**kwargs)
   dest=self.workspace/'build/casefs/rootfs'
   assert dest.is_dir() and not dest.is_symlink() and self.workspace in dest.parents
   shutil.rmtree(dest);model_private.copy_tree(stage,dest)
   assert model_private.tree_inventory(dest)==model_private.tree_inventory(stage)
   self.sources['build/casefs/rootfs']=hashlib.sha256(encoded(model_private.tree_inventory(stage))).hexdigest()
   self.before=self.immutable();self.manifest_sha256=hashlib.sha256(encoded(self.before)).hexdigest();(self.job/'manifest.json').write_bytes(encoded(self.before))
 model_private.ModelJob=Job
 job=b'''set -eu
mkdir /tmp/native-rootfs
cp -a /work/build/casefs/rootfs/. /tmp/native-rootfs/
mkfs.ubifs '''+' '.join(mkfs_flags()).encode()+b''' -r /tmp/native-rootfs -o /work/build/localmod-rootfs.ubifs
echo NATIVE_CANDIDATE_UBIFS_BUILT
'''
 console=model_private.run_model('build',timeout=180,guest_script=job,receipt=receipt,output_root=output)
 (ROOT/'output/merlin38812_native_candidate_build.log').write_text(console)
 pin=json.loads((ROOT/'build/merlin_sources.json').read_text());base=ROOT/pin['archive']['image']
 assert sha(base)==pin['archive']['image_sha256']
 packed,packing=repack(base.read_bytes(),(output/'localmod-rootfs.ubifs').read_bytes())
 image.write_bytes(packed);packing['image']=str(image.relative_to(ROOT))
 image.with_suffix('.build.json').write_text(json.dumps(packing,indent=2)+'\n')
 volumes=work/'readback-volumes'
 subprocess.run([sys.executable,str(ROOT/'build/inspect_upstream.py'),str(image),str(volumes)],check=True,stdout=subprocess.DEVNULL)
 layout=json.loads((volumes/'layout.json').read_text());assert layout['whole_crc_valid'] and not any(k.endswith('_bad') and v for k,v in layout['checks'].items())
 parsed=ubifs(ubi_file(str(volumes/'rootfs_ubifs'),126976));inodes={};bad=[]
 walk.index(parsed,parsed.master_node.root_lnum,parsed.master_node.root_offs,inodes,bad);assert not bad
 actual_meta={}
 def visit(number,path):
  node=inodes[number];ino=node['ino'];actual_meta[path]=dict(mode=ino.mode,uid=ino.uid,gid=ino.gid,xattrs=getattr(ino,'xattr_cnt',0))
  for d in node.get('dent',[]):visit(d.inum,path.rstrip('/')+'/'+d.name)
 visit(1,'/')
 assert set(meta)==set(actual_meta)
 for n,r in actual_meta.items():
  assert r['mode']==meta[n]['mode'] and r['uid']==r['gid']==r['xattrs']==0,(n,r,meta[n])
 fresh=work/'readback-rootfs';fresh.mkdir();extract_files(parsed,str(fresh));actual=inventory(fresh)
 def content(rows):return {n:{k:v for k,v in r.items() if k!='mode'} for n,r in rows.items()}
 assert content(actual)==content(expected),'New image content/link readback mismatch'
 assert expected==inventory(stage) and protected=={n:sha(ROOT/n) for n in protected}
 report=dict(status='NATIVE_MERLIN_CANDIDATE_BUILT_READBACK_PASS_NOT_FLASH_READY',image=packing,
  rootfs=str(stage.relative_to(ROOT)),stage_inventory_sha256=stage_sha,readback_entries=len(actual),
  full_content_links_modes_owners_readback_verified=True,native_boot_and_kernel_region_retained=True,
  native_recovery_subsecond_wait_uses_usleep=True,
  center_fractional_sleep_private_path=True,
  fancyss_policy=fancyss,
  protected_sha256=protected,build_vm=receipt,whole_upgrade_complete=False,release_selected=False,
  remaining=['Native RC launcher and target PID1 integration','Cross-boot plugin recovery with persistent JFFS fixture','Authentic Fancyss/HND plugins with native DNS/postconf and full VPN framework','Integrated candidate long-run and full regression gates','Physical boot/UU acceleration excluded from current no-flash scope'],
  source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [HERE/'native_candidate.py',HERE/'release.json',HERE/'center_sleep.c',HERE/'native_restore.c',HERE/'fancyss_policy.py',HERE/'vendor/fancyss_uninstall_p1.json',ROOT/'sources/localmod/restore.c',ROOT/'build/prepare_fancyss.py',ROOT/'build/fancyss_sources.json',ROOT/'build/fancyss_inputs.json',ROOT/'build/repack_image.py',ROOT/'build/model_private.py',ROOT/'build/device_config.py']})
 (work/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
 (ROOT/'output/merlin38812_native_candidate_tests.json').write_text(json.dumps(report,indent=2)+'\n')
 print(report['status'],name,len(actual),'paths')
if __name__=='__main__':main()
