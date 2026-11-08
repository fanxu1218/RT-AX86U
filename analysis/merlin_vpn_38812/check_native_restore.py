#!/usr/bin/env python3
"""Observe the actual restore adapter with an explicit legacy kernel boundary."""
import builtins,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
import check_candidate_runtime as controller
def run_derived(code,namespace):
 source=(ROOT/'build/native-candidate-runtime/derived_check.py').read_text()
 def change(old,new):
  nonlocal source
  assert source.count(old)==1,(old,source.count(old));source=source.replace(old,new)
 change("'candidate_runtime.go']]]","'candidate_runtime.go','restore_probe.go','restore_kernel_fixture.c','check_native_restore.py']]]")
 change("'analysis/merlin_vpn_38812/native_hooks.go','analysis/merlin_vpn_38812/candidate_runtime.go']:","'analysis/merlin_vpn_38812/restore_probe.go']:")
 change('candidateDuringUU(s,u)','')
 source=source.replace('build/native-candidate-runtime','build/native-restore-probe')
 change("setup=setup[:setup.index(cut)]+'exec /work/build/native-restore-probe/probe success\\n'","setup=setup[:setup.index(cut)]+'/sbin/service start_softcenter || exit 1\\nexec /work/build/native-restore-probe/probe\\n'")
 marker='class Workspace(SealedWorkspace):'
 change(marker,"subprocess.run([*cc,'-shared','-fPIC','-o',str(work/'restore_kernel_fixture.so'),str(HERE/'restore_kernel_fixture.c'),'-ldl'],check=True)\n "+marker)
 source=source.replace('merlin38812_candidate_runtime','merlin38812_restore_probe').replace('NATIVE_HOOKS_RESULT','RESTORE_PROBE_RESULT').replace('LOCAL_NATIVE_MERLIN_CANDIDATE_RUNTIME_PASS','LOCAL_NATIVE_RESTORE_OBSERVATIONS_RECORDED')
 change("'No cross-boot recovery, physical router, true UU account/game acceleration or firmware release acceptance'","'Actual candidate restore adapter; declared test-only exec boundary applies output with Alpine legacy xtables; native 4.1 kernel/backend ABI, physical router, actual UU account/game acceleration remain unverified'")
 folder=ROOT/'build/native-restore-probe';folder.mkdir(exist_ok=True);(folder/'derived_check.py').write_text(source)
 builtins.exec(compile(source,str(folder/'derived_check.py'),'exec'),namespace)
if __name__=='__main__':
 controller.exec=run_derived;controller.main()
 p=ROOT/'output/merlin38812_restore_probe_tests.json';r=json.loads(p.read_text());r['status']='LOCAL_NATIVE_RESTORE_NOFLUSH_CONTRACT_PASS' if r['result']['contract_matches'] else 'LOCAL_NATIVE_RESTORE_NOFLUSH_DUPLICATE_JUMPS_REPRODUCED';p.write_text(json.dumps(r,indent=2)+'\n');print(r['status'])
