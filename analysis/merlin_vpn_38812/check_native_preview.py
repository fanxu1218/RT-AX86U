#!/usr/bin/env python3
"""Native Merlin login/pages/save + center lifecycle with an owned UU worker."""
import hashlib,json,os,subprocess,sys,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'build'))
from sealed_vm import SealedWorkspace,inventory,encoded,sha,copy_file
from run_readonly_linux import run

def main():
 os.chdir(ROOT)
 stage=json.loads((ROOT/'output/merlin38812_native_preview_stage.json').read_text())
 tree=ROOT/stage['rootfs']
 assert hashlib.sha256(encoded(inventory(tree))).hexdigest()==stage['inventory_sha256']
 baseline={n:sha(ROOT/n) for n in stage['protected_sha256']}
 assert baseline==stage['protected_sha256']
 work=ROOT/'build/native-preview';work.mkdir(exist_ok=True)
 names=['build/native_runtime_client.go','build/test_online.go','build/coexist_helpers.go',
        'build/native_hw_fixture.c','build/native_uu_transport.c','sources/localmod/httpd_bridge.c',
        'build/real_plugins_setup.sh','build/linux_real_plugins_job.sh','build/sealed_vm.py',
        'build/run_readonly_linux.py','analysis/merlin_vpn_38812/native_preview.go',
        'analysis/merlin_vpn_38812/native_preview.py','analysis/merlin_vpn_38812/check_native_preview.py']
 sources={n:sha(ROOT/n) for n in names}
 compile_dir=work/'compile';compile_dir.mkdir(exist_ok=True)
 files=[]
 for n in names:
  if n.endswith('.go'):
   dest=compile_dir/Path(n).name;dest.write_bytes((ROOT/n).read_bytes());files.append(str(dest))
 subprocess.run(['go','build','-trimpath','-o',str(work/'probe'),*files],check=True,env=dict(os.environ,GOOS='linux',GOARCH='arm64',CGO_ENABLED='0'))
 cc=[str(ROOT/'sources/zig-aarch64-macos-0.15.2/zig'),'cc','-target','arm-linux-gnueabi.2.26','-mcpu=cortex_a53','-O2']
 for n,flags,extra in [('native_hw_fixture',['-shared','-fPIC'],['-DLOCALMOD_DEVICE_MODEL="RT-AX86U"']),('native-nvram',[],['-DLOCALMOD_DEVICE_MODEL="RT-AX86U"','-DNATIVE_NVRAM_CLI']),('native_uu_transport',['-shared','-fPIC'],['-ldl'])]:
  src='native_hw_fixture' if n=='native-nvram' else n
  subprocess.run([*cc,*flags,'-o',str(work/(n if n=='native-nvram' else n+'.so')),str(ROOT/'build'/(src+'.c')),*extra],check=True)
 for source,target in [(ROOT/'build/uu-matrix/clear_preload.so',work/'clear_preload.so'),(tree/'usr/lib/localmod/httpd_bridge.so',work/'httpd_bridge.so')]:
  assert not target.is_symlink()
  target.unlink(missing_ok=True);copy_file(source,target)
 setup=(ROOT/'build/real_plugins_setup.sh').read_text()
 old='exec /work/build/test-merlin "$phase"';assert setup.count(old)==1
 setup=setup.replace(old,'exec /work/build/native-preview/probe "$phase"')
 (work/'setup.sh').write_text(setup)
 job=(ROOT/'build/linux_real_plugins_job.sh').read_text()
 old='cp -a /work/build/casefs/rootfs/. /router/';assert job.count(old)==1
 export='build/native-preview-root'
 job=job.replace(old,'cp -a /work/'+export+'/. /router/').replace('/work/build/real_plugins_setup.sh','/work/build/native-preview/setup.sh')
 class Workspace(SealedWorkspace):
  def __init__(self):
   super().__init__('candidate-merlin-components',guest_job=job.encode())
   dest=self.workspace/export
   before=inventory(tree);shutil.copytree(tree,dest,symlinks=True,copy_function=copy_file)
   assert before==inventory(tree)==inventory(dest)
   self.inputs[export]=hashlib.sha256(encoded(before)).hexdigest()
   for p in work.rglob('*'):
    if not p.is_file():continue
    n=p.relative_to(ROOT);target=self.workspace/n;target.parent.mkdir(parents=True,exist_ok=True);copy_file(p,target);self.inputs[str(n)]=sha(p)
   for n in ['native_hw_fixture.so','native_uu_transport.so','native-nvram','httpd_bridge.so']:
    target=self.workspace/'build'/n;target.unlink();copy_file(work/n,target);self.inputs['build/'+n]=sha(work/n)
   self.before=self.current_inventory();self.manifest_sha256=hashlib.sha256(encoded(self.before)).hexdigest();(self.job/'manifest.json').write_bytes(encoded(self.before));self.verify()
 log=ROOT/'output/merlin38812_native_preview.log';receipt={}
 console=run(log,sealed=Workspace(),timeout=300,cpus=1,receipt=receipt)
 rows=[json.loads(l.removeprefix('NATIVE_PREVIEW_RESULT ')) for l in console.splitlines() if l.startswith('NATIVE_PREVIEW_RESULT ')];assert len(rows)==1
 assert baseline=={n:sha(ROOT/n) for n in baseline}
 assert sources=={n:sha(ROOT/n) for n in sources}
 assert hashlib.sha256(encoded(inventory(tree))).hexdigest()==stage['inventory_sha256']
 report=dict(status='LOCAL_NATIVE_MERLIN_PREVIEW_COMPATIBILITY_PASS',stage=stage,result=rows[0],vm=receipt,source_sha256=sources,baseline_preserved_sha256=baseline,log_sha256=sha(log),limits=['No automatic software-center boot integration or image/release produced','All writes use a disposable owned NVRAM/JFFS fixture; no router touched','Page rendering and configuration save do not prove VPN tunnels or target PID1 service control','UU startup uses the native ntpd callback with an owned monitor; no real account/game acceleration'])
 (ROOT/'output/merlin38812_native_preview_tests.json').write_text(json.dumps(report,indent=2)+'\n')
 print(report['status'],len(rows[0]['checks']),'checks')
if __name__=='__main__':main()
