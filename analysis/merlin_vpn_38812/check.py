#!/usr/bin/env python3
"""Run the private Merlin VPN model beside retained factory services in a sealed VM."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(ROOT/'build')]
from prepare import prepare,PAYLOAD
from sealed_vm import SealedWorkspace,copy_file,sha,encoded
from run_readonly_linux import run
def main():
 os.chdir(ROOT)
 sys.path.insert(0,str(ROOT/'build'))
 from check import owned_sources
 gate=json.loads((ROOT/'output/release_gates.json').read_text());assert owned_sources()==gate['source_sha256']
 baseline={n:sha(ROOT/n) for n in ['output/release_gates.json','output/local_delivery.json','output/r9r2_diagnostic_delivery.json','output/localmod2-r9-r2-local-delivery.tar.gz','output/localmod2-r9-r2-diagnostics.tar.gz',gate['config']['image']]}
 manifest=prepare();work=PAYLOAD.parent
 sources=['build/native_runtime_client.go','build/test_online.go','build/coexist_helpers.go','analysis/merlin_vpn_38812/probe.go','analysis/merlin_vpn_38812/check.py','build/sealed_vm.py','build/run_readonly_linux.py','build/linux_real_plugins_job.sh','build/real_plugins_setup.sh']
 source_hashes={p:sha(ROOT/p) for p in sources}
 compile_dir=work/'compile';compile_dir.mkdir(exist_ok=True)
 go_files=[]
 for n in sources:
  if n.endswith('.go'):
   p=compile_dir/Path(n).name;p.write_bytes((ROOT/n).read_bytes());go_files.append(str(p))
 subprocess.run(['go','build','-trimpath','-o',str(work/'probe'),*go_files],check=True,env=dict(os.environ,GOOS='linux',GOARCH='arm64',CGO_ENABLED='0'))
 job=(ROOT/'build/linux_real_plugins_job.sh').read_text()
 assert job.count('chown -Rh 0:0 /router')==1
 job=job.replace('chown -Rh 0:0 /router','cp -a /work/build/merlin-vpn-phase1/payload/. /router/\nchown -Rh 0:0 /router')
 setup=(ROOT/'build/real_plugins_setup.sh').read_text()
 old='exec /work/build/test-merlin "$phase"';assert old in setup
 setup=setup.replace(old,'exec /work/build/merlin-vpn-phase1/probe "$phase"')
 (work/'setup.sh').write_text(setup)
 job=job.replace('/work/build/real_plugins_setup.sh','/work/build/merlin-vpn-phase1/setup.sh')
 class Workspace(SealedWorkspace):
  def __init__(self):
   super().__init__('candidate-merlin-components',guest_job=job.encode())
   for p in work.rglob('*'):
    if not p.is_file():continue
    n=p.relative_to(ROOT);dest=self.workspace/n;dest.parent.mkdir(parents=True,exist_ok=True);copy_file(p,dest);assert sha(p)==sha(dest);self.inputs[str(n)]=sha(p)
   self.before=self.current_inventory();self.manifest_sha256=hashlib.sha256(encoded(self.before)).hexdigest();(self.job/'manifest.json').write_bytes(encoded(self.before));self.verify()
 receipt={};log=ROOT/'output/merlin38812_vpn_phase1.log'
 console=run(log,sealed=Workspace(),timeout=300,cpus=1,receipt=receipt)
 rows=[json.loads(l.removeprefix('VPN38812_PHASE1_RESULT ')) for l in console.splitlines() if l.startswith('VPN38812_PHASE1_RESULT ')];assert len(rows)==1
 assert baseline=={n:sha(ROOT/n) for n in baseline} and source_hashes=={n:sha(ROOT/n) for n in source_hashes}
 assert rows[0]['service_control_enabled'] is False and rows[0]['full_firmware_upgrade_complete'] is False
 result=dict(status='LOCAL_PRIVATE_MERLIN_VPN_MODEL_PASS',scope='Phase1 read-only native configuration model; not full VPN UI/control integration or a firmware upgrade',source_tag='3004.388.12_2',candidate_unchanged_sha256=gate['candidate_sha256'],manifest=manifest,result=rows[0],vm=receipt,baseline_preserved_sha256=baseline,source_sha256=source_hashes,log_sha256=sha(log),limits=['No router access or flash; GitHub push remains user-owned','QEMU-user inside Linux6.12 isolated VM, no external NIC; original4.1 kernel not executed','UU original startup/download/checksum path with owned worker only; no real account/game acceleration','No VPN write/start/stop route or native UI menu is installed; whole firmware remains r9-r2'])
 (ROOT/'output/merlin38812_vpn_phase1_tests.json').write_text(json.dumps(result,indent=2)+'\n')
 print(result['status'],len(rows[0]['checks']),'checks; protected firmware unchanged')
if __name__=='__main__':main()
