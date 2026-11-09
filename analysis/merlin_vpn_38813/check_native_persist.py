#!/usr/bin/env python3
"""Run the established interruption scenarios against the verified P5 image.

Each boot uses a new no-NIC VM, read-only inputs and one exclusively owned
96-MiB state disk. Source/phase transformations are recorded in each sealed job.
The production startup/transaction files come from the image's verified stage.
"""
import argparse,builtins,hashlib,json,os,shutil,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
import check_candidate_runtime as controller
CURRENT={};DISK=None;CUT=False
GO=['build/test_interrupt_main.go','build/interrupt_scenarios.go','build/test_interrupt.go',
    'build/recovery_safety.go','build/test_online.go','build/native_runtime_client.go','build/coexist_helpers.go']

def run_derived(code,namespace):
 source=(ROOT/'build/merlin38813-native-candidate-runtime/derived_check.py').read_text()
 def change(old,new):
  nonlocal source
  assert source.count(old)==1,(old,source.count(old));source=source.replace(old,new)
 change("'candidate_runtime.go']]]","'candidate_runtime.go','check_native_persist.py']]]+"+repr(GO+['build/txn_fault_fixture.c','build/real_plugin_inputs.json']))
 old="['build/native_runtime_client.go','build/test_online.go','build/coexist_helpers.go','analysis/merlin_vpn_38813/native_hooks.go','analysis/merlin_vpn_38813/candidate_runtime.go']"
 change('for n in '+old+':','for n in '+repr(GO)+':')
 change('candidateDuringUU(s,u)','')
 change("assert text.count('u := onlineUUStart(ctx)')==1","pass")
 change("text=(ROOT/n).read_text()",'''text=(ROOT/n).read_text()
  text=text.replace('onlineUUStart(ctx)','previewUUStart(ctx)')
  text=text.replace('/work/build/real_plugins_setup.sh','/work/build/merlin38813-native-persist/setup.sh')
  if n.endswith('interrupt_scenarios.go'):
   mark='if irqPhase.Initialize {'
   assert text.count(mark)==1
   text=text.replace(mark,mark+'\\n nrCommand("/bin/nvram","set","vpn_client1_desc=persistent-native-profile")')
   mark='irqUUData("")\\n\\tirqOriginal("")'
   assert text.count(mark)==1
   text=text.replace(mark,mark+'\\n if strings.TrimSpace(nrCommand("/bin/nvram","get","vpn_client1_desc"))!="persistent-native-profile" {panic("persistent native VPN profile lost")}')''')
 source=source.replace('build/merlin38813-native-candidate-runtime','build/merlin38813-native-persist')
 change("setup=setup[:setup.index(cut)]+'exec /work/build/merlin38813-native-hooks/probe success\\n'", "setup=setup[:setup.index(cut)]+'/sbin/service start_softcenter || { cat /tmp/.localmod/bootstrap.log; exit 1; }\\nexec /work/build/merlin38813-native-persist/probe interrupt-run\\n'") if "setup=setup[:setup.index(cut)]+'exec /work/build/merlin38813-native-hooks/probe success\\n'" in source else change("setup=setup[:setup.index(cut)]+'exec /work/build/merlin38813-native-persist/probe success\\n'", "setup=setup[:setup.index(cut)]+'/sbin/service start_softcenter || { cat /tmp/.localmod/bootstrap.log; exit 1; }\\nexec /work/build/merlin38813-native-persist/probe interrupt-run\\n'")
 marker='class Workspace(SealedWorkspace):'
 change(marker,"""job=job.replace('/work/build/test-interrupt','/work/build/merlin38813-native-persist/probe')
 job=job.replace('export NATIVE_CERT_CASE=1 NATIVE_STATE_DIRECTORY=/tmp/native-nvram','export NATIVE_CERT_CASE=1 NATIVE_STATE_DIRECTORY=/jffs/.owned-fixture-nvram')
 token='mkdir -p /router/tmp/native-nvram /router/tmp/real-plugin-results'
 assert job.count(token)==1
 job=job.replace(token,token+'\\nmkdir -p /router/jffs/.owned-fixture-nvram\\nrm -f /router/jffs/.owned-fixture-nvram/ntp_ready /router/jffs/.owned-fixture-nvram/svc_ready /router/jffs/.owned-fixture-nvram/reload_svc_radio')
 subprocess.run([*cc,'-shared','-fPIC','-o',str(work/'txn_fault_fixture.so'),str(ROOT/'build/txn_fault_fixture.c'),'-ldl'],check=True)
 """+marker)
 change("super().__init__('candidate-merlin-components',guest_job=job.encode())", "super().__init__('candidate-merlin-components',guest_job=job.encode(),state_disk=ROOT/"+repr(str(DISK.relative_to(ROOT)))+")")
 marker='self.before=self.current_inventory();self.manifest_sha256='
 insert="""phase=json.loads(%r)
   target=self.workspace/'build/interrupt-phase.json';target.write_text(json.dumps(phase)+'\\n');self.inputs['build/interrupt-phase.json']=sha(target)
   manifest=ROOT/'build/real_plugin_inputs.json';target=self.workspace/'build/real_plugin_inputs.json';copy_file(manifest,target);self.inputs['build/real_plugin_inputs.json']=sha(manifest)
   for row in json.loads(manifest.read_text())['packages']:
    if row['module']!='ddnsgo':continue
    n=row['path'];assert n.startswith('sources/realplugins/') and '..' not in Path(n).parts
    original=ROOT/n;assert sha(original)==row['sha256'];target=self.workspace/n;target.parent.mkdir(parents=True,exist_ok=True);copy_file(original,target);self.inputs[n]=sha(original)
   target=self.workspace/'build/txn_fault_fixture.so';target.unlink(missing_ok=True);copy_file(work/'txn_fault_fixture.so',target);self.inputs['build/txn_fault_fixture.so']=sha(target)
   """ % json.dumps(CURRENT)
 change(marker,insert+marker)
 change('timeout=360,cpus=1,receipt=receipt','timeout=420,cpus=1,receipt=receipt,expect_cut='+repr(CUT))
 old="rows=[json.loads(l.removeprefix('NATIVE_HOOKS_RESULT ')) for l in console.splitlines() if l.startswith('NATIVE_HOOKS_RESULT ')];assert len(rows)==1"
 change(old,"results=[json.loads(l.removeprefix('INTERRUPT_RESULT ')) for l in console.splitlines() if l.startswith('INTERRUPT_RESULT ')];assert results;checks=[n for r in results for n in r['checks']];assert checks and len(checks)==len(set(checks));assert all('PASS '+n+'\\n' in console for n in checks);rows=[dict(checks=checks,online=dict(checks=[]),phases=results)]")
 change("'No cross-boot recovery, physical router, true UU account/game acceleration or firmware release acceptance'", "'Cross-boot behavior uses an owned ext4 state disk and persistent board fixture; physical NAND/UBIFS, actual UU account/game acceleration and firmware release acceptance remain unverified'")
 label='merlin38813_persist_'+CURRENT['case']+'_'+CURRENT['boot']
 source=source.replace('merlin38813_candidate_runtime',label).replace('LOCAL_NATIVE_MERLIN_CANDIDATE_RUNTIME_PASS','LOCAL_NATIVE_PERSISTENCE_BOOT_PASS')
 folder=ROOT/'build/merlin38813-native-persist';folder.mkdir(exist_ok=True);(folder/'derived_check.py').write_text(source)
 builtins.exec(compile(source,str(folder/'derived_check.py'),'exec'),namespace)

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def boot(case,phase,disk,initialize=False,cut=False):
 global CURRENT,DISK,CUT
 CURRENT=dict(case=case,boot=phase,initialize=initialize);DISK=disk;CUT=cut
 print('NATIVE_PERSIST_BOOT',case,phase,flush=True)
 controller.exec=run_derived;controller.main()
 path=ROOT/f'output/merlin38813_persist_{case}_{phase}_tests.json'
 r=json.loads(path.read_text());assert all(x['case']==case and x['boot']==phase for x in r['result']['phases'])
 return dict(report=str(path.relative_to(ROOT)),sha256=sha(path),checks=r['result']['checks'])

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--cases',default='kill-tree,kill-parent,real-ddnsgo,no-space');args=ap.parse_args()
 cases=args.cases.split(',');allowed={'download','checkpoint','kill-parent','kill-tree','offline','fresh','real-ddnsgo','before-commit','after-commit','committed-cleanup','no-space'}
 assert cases and len(set(cases))==len(cases) and set(cases)<=allowed
 c=json.loads((ROOT/'output/merlin38813_native_candidate_tests.json').read_text());assert 'P7_' in c['image']['image']
 assert sha(ROOT/c['image']['image'])==c['image']['sha256']
 parent=ROOT/'build/interrupt-private';parent.mkdir(mode=0o700,exist_ok=True);parent.chmod(0o700)
 key=c['image']['sha256'][:12];foundation=parent/('native-'+key+'-foundation.img');receipt=parent/('native-'+key+'-foundation.json')
 if receipt.is_file():
  base=json.loads(receipt.read_text());assert base['candidate_sha256']==c['image']['sha256'] and sha(foundation)==base['disk_sha256']
 else:
  assert not foundation.exists(),'Retained incomplete fixture needs inspection'
  with foundation.open('xb') as f:f.truncate(96*1024*1024)
  foundation.chmod(0o600);result=boot('foundation','foundation',foundation,initialize=True)
  base=dict(candidate_sha256=c['image']['sha256'],disk_sha256=sha(foundation),result=result);receipt.write_text(json.dumps(base,indent=2)+'\n')
 summary=ROOT/'output/merlin38813_persistence_tests.json'
 records={}
 if summary.is_file():
  previous=json.loads(summary.read_text())
  if previous['candidate']['sha256']==c['image']['sha256']:
   records=previous['cases']
  else:
   history=summary.with_name('merlin38813_persistence_history_'+previous['candidate']['sha256'][:12]+'.json')
   if history.exists():assert sha(history)==sha(summary)
   else:shutil.copyfile(summary,history)
 for case in cases:
  assert case not in records,'Completed case already retained: '+case
  disk=parent/('native-'+key+'-'+case+'.img');assert not disk.exists(),'Retained case fixture needs inspection: '+str(disk)
  shutil.copyfile(foundation,disk);disk.chmod(0o600)
  phases=[('exercise',False)] if case=='no-space' else [('cut',True),('verify',False)]
  if case=='kill-tree':phases.insert(1,('recover-cut',True))
  if case=='kill-parent':phases.insert(1,('recover-db-cut',True))
  records[case]={}
  for phase,cut in phases:records[case][phase]=boot(case,phase,disk,cut=cut)
  records[case]['final_disk_sha256']=sha(disk)
  # Retain completed state for inspection as well; never remove a failed disk.
  report=dict(status='LOCAL_NATIVE_PERSISTENCE_SELECTED_CASES_PASS',candidate=c['image'],foundation=base,cases=records,requested_cases=cases,complete=all(case in records for case in cases),all_standard_scenarios_complete=set(records)==allowed,physical_router_flashed=False,full_upgrade_complete=False)
  summary.write_text(json.dumps(report,indent=2)+'\n')
 assert sha(ROOT/c['image']['image'])==c['image']['sha256']
 print('LOCAL_NATIVE_PERSISTENCE_SELECTED_CASES_PASS',list(records),flush=True)
if __name__=='__main__':main()
