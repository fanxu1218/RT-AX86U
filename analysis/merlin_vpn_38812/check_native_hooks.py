#!/usr/bin/env python3
"""Exercise real Merlin hook APIs, automatic center start and native UU together.

The integration overlay is RAM-only. The retained stage, candidate, old passing
reports and selected release configuration remain immutable.
"""
import hashlib,json,os,subprocess,sys,shutil,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'build'))
from sealed_vm import SealedWorkspace,inventory,encoded,sha,copy_file
from run_readonly_linux import run
from elftools.elf.elffile import ELFFile

def main():
 os.chdir(ROOT)
 stage=json.loads((ROOT/'output/merlin38812_native_preview_stage.json').read_text());tree=ROOT/stage['rootfs']
 assert hashlib.sha256(encoded(inventory(tree))).hexdigest()==stage['inventory_sha256']
 names=['build/native_runtime_client.go','build/test_online.go','build/coexist_helpers.go',
        'build/native_hw_fixture.c','build/native_uu_transport.c','sources/localmod/runtime.c',
        'sources/localmod/runtime.h','sources/localmod/bounded_log.h',
        'build/real_plugins_setup.sh','build/linux_real_plugins_job.sh','build/sealed_vm.py',
        'build/run_readonly_linux.py',*['analysis/merlin_vpn_38812/'+n for n in
        ['native_preview.go','native_hooks.go','native_boot_bridge.c','native_launcher.c',
         'native_restore.c','native_center_event.sh','native_hook_probe.c','check_native_hooks.py']]]
 sources={n:sha(ROOT/n) for n in names}
 baseline={n:sha(ROOT/n) for n in [*stage['protected_sha256'],'output/merlin38812_native_preview_tests.json','output/merlin38812_uu_matrix_tests.json']}
 work=ROOT/'build/native-hooks';work.mkdir(exist_ok=True)
 compile_dir=work/'compile';compile_dir.mkdir(exist_ok=True)
 files=[]
 for n in ['build/native_runtime_client.go','build/test_online.go','build/coexist_helpers.go','analysis/merlin_vpn_38812/native_hooks.go']:
  text=(ROOT/n).read_text()
  # Native BusyBox sleep lacks fractional seconds; keep the owned fixture
  # heartbeat's intended interval instead of spinning on an invalid argument.
  text=re.sub(r'sleep 0\.1(?![0-9])','usleep 100000',text)
  if n.endswith('test_online.go'):
   assert text.count('u := onlineUUStart(ctx)')==1
   text=text.replace('u := onlineUUStart(ctx)','u := previewUUStart(ctx)')
  p=compile_dir/Path(n).name;p.write_text(text);files.append(str(p))
 original=(HERE/'native_preview.go').read_text()
 start=original.index('func previewUUStart(');end=original.index('func previewForm(')
 function=original[start:end]
 old='LD_PRELOAD=/work/build/native_hw_fixture.so:';assert function.count(old)==1
 function=function.replace(old,'LD_PRELOAD=/work/build/native-hooks/native_boot_bridge.so:/work/build/native_hw_fixture.so:')
 function=function.replace('/work/build/native-preview/clear_preload.so','/work/build/native-hooks/clear_preload.so')
 p=compile_dir/'native_uu.go'
 p.write_text('package main\nimport("context";"crypto/md5";"fmt";"net";"net/http";"os";"os/exec";"strconv";"strings";"time")\n'+function);files.append(str(p))
 subprocess.run(['go','build','-trimpath','-o',str(work/'probe'),*files],check=True,env=dict(os.environ,GOOS='linux',GOARCH='arm64',CGO_ENABLED='0'))
 cc=[str(ROOT/'sources/zig-aarch64-macos-0.15.2/zig'),'cc','-target','arm-linux-gnueabi.2.26','-mcpu=cortex_a53','-O2']
 subprocess.run([*cc,'-shared','-fPIC','-o',str(work/'native_boot_bridge.so'),str(HERE/'native_boot_bridge.c'),str(ROOT/'sources/localmod/runtime.c'),'-ldl'],check=True)
 subprocess.run([*cc,'-o',str(work/'hook-probe'),str(HERE/'native_hook_probe.c'),'-L'+str(tree/'usr/lib'),'-L'+str(tree/'lib'),'-Wl,--no-as-needed','-lshared','-lnvram','-Wl,--allow-shlib-undefined'],check=True)
 with (work/'hook-probe').open('rb') as f:
  elf=ELFFile(f);needed=[t.needed for t in elf.get_section_by_name('.dynamic').iter_tags() if t.entry.d_tag=='DT_NEEDED']
 for n in needed:
  if n.startswith('/'):
   assert n==str(tree/'usr/lib/libshared.so'),n
   subprocess.run([str(ROOT/'build/tools/patchelf-0.18.0'),'--replace-needed',n,'libshared.so',str(work/'hook-probe')],check=True)
 with (work/'hook-probe').open('rb') as f:
  elf=ELFFile(f)
  assert all(s['p_align']<=1 or (s['p_vaddr']-s['p_offset'])%s['p_align']==0 for s in elf.iter_segments() if s['p_type']=='PT_LOAD')
  assert all('/' not in t.needed for t in elf.get_section_by_name('.dynamic').iter_tags() if t.entry.d_tag=='DT_NEEDED')
 for n,flags,extra in [('native_hw_fixture',['-shared','-fPIC'],['-DLOCALMOD_DEVICE_MODEL="RT-AX86U"']),('native-nvram',[],['-DLOCALMOD_DEVICE_MODEL="RT-AX86U"','-DNATIVE_NVRAM_CLI']),('native_uu_transport',['-shared','-fPIC'],['-ldl'])]:
  src='native_hw_fixture' if n=='native-nvram' else n
  subprocess.run([*cc,*flags,'-o',str(work/(n if n=='native-nvram' else n+'.so')),str(ROOT/'build'/(src+'.c')),*extra],check=True)
 for source,target in [(ROOT/'build/uu-matrix/clear_preload.so',work/'clear_preload.so'),(tree/'usr/lib/localmod/httpd_bridge.so',work/'httpd_bridge.so'),(HERE/'native_center_event.sh',work/'native-center-event.sh')]:
  assert not target.is_symlink();target.unlink(missing_ok=True);copy_file(source,target)
 setup=(ROOT/'build/real_plugins_setup.sh').read_text()
 cut='/bin/sh /usr/libexec/localmod/bootstrap.sh prepare ||';assert setup.count(cut)==1
 setup=setup[:setup.index(cut)]+'exec /work/build/native-hooks/probe success\n'
 (work/'setup.sh').write_text(setup)
 job=(ROOT/'build/linux_real_plugins_job.sh').read_text();old='cp -a /work/build/casefs/rootfs/. /router/';assert job.count(old)==1
 export='build/native-hooks-root'
 job=job.replace(old,'cp -a /work/'+export+'/. /router/').replace('/work/build/real_plugins_setup.sh','/work/build/native-hooks/setup.sh')
 marker='chown -Rh 0:0 /router';assert job.count(marker)==1
 job=job.replace(marker,'cp /work/build/native-hooks/native-center-event.sh /router/usr/libexec/localmod/\nchmod 755 /router/usr/libexec/localmod/native-center-event.sh\n'+marker)
 class Workspace(SealedWorkspace):
  def __init__(self):
   super().__init__('candidate-merlin-components',guest_job=job.encode())
   dest=self.workspace/export;before=inventory(tree);shutil.copytree(tree,dest,symlinks=True,copy_function=copy_file)
   assert before==inventory(tree)==inventory(dest);self.inputs[export]=hashlib.sha256(encoded(before)).hexdigest()
   for p in work.rglob('*'):
    if not p.is_file():continue
    n=p.relative_to(ROOT);target=self.workspace/n;target.parent.mkdir(parents=True,exist_ok=True);copy_file(p,target);self.inputs[str(n)]=sha(p)
   for n in ['native_hw_fixture.so','native_uu_transport.so','native-nvram','httpd_bridge.so']:
    target=self.workspace/'build'/n;target.unlink();copy_file(work/n,target);self.inputs['build/'+n]=sha(work/n)
   self.before=self.current_inventory();self.manifest_sha256=hashlib.sha256(encoded(self.before)).hexdigest();(self.job/'manifest.json').write_bytes(encoded(self.before));self.verify()
 log=ROOT/'output/merlin38812_native_hooks.log';receipt={}
 console=run(log,sealed=Workspace(),timeout=360,cpus=1,receipt=receipt)
 rows=[json.loads(l.removeprefix('NATIVE_HOOKS_RESULT ')) for l in console.splitlines() if l.startswith('NATIVE_HOOKS_RESULT ')];assert len(rows)==1
 assert sources=={n:sha(ROOT/n) for n in sources} and baseline=={n:sha(ROOT/n) for n in baseline}
 assert hashlib.sha256(encoded(inventory(tree))).hexdigest()==stage['inventory_sha256']
 report=dict(status='LOCAL_NATIVE_MERLIN_HOOK_AUGMENTATION_PASS',result=rows[0],stage=stage,source_sha256=sources,baseline_preserved_sha256=baseline,vm=receipt,log_sha256=sha(log),limits=['Native libshared APIs under QEMU-user with owned board/NVRAM; target PID1 boot not executed','New native hook bridge/event helper loaded only into the owned test; RC launcher/restore not staged or runtime-validated','No cross-boot recovery, physical router, true UU account/game acceleration or firmware release acceptance'])
 (ROOT/'output/merlin38812_native_hooks_tests.json').write_text(json.dumps(report,indent=2)+'\n')
 print(report['status'],len(rows[0]['checks']),'native hook checks plus',len(rows[0]['online']['checks']),'online lifecycle checks')
if __name__=='__main__':main()
