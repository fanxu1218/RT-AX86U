#!/usr/bin/env python3
"""Derive an owned candidate harness while preserving the earlier evidence.

Every transformation is exact and fail-closed. The complete derived controller
and Go sources are included in the sealed job manifest. Only test fixtures are
changed in RAM; production rc launcher/bridge are read from the built image's
verified stage, rather than replaced by freshly compiled probe equivalents.
"""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]

def main():
 candidate=json.loads((ROOT/'output/merlin38813_native_candidate_tests.json').read_text())
 assert candidate['status']=='NATIVE_MERLIN_CANDIDATE_BUILT_READBACK_PASS_NOT_FLASH_READY'
 image=ROOT/candidate['image']['image']
 assert hashlib.sha256(image.read_bytes()).hexdigest()==candidate['image']['sha256']
 source=(HERE/'check_native_hooks.py').read_text()
 def change(old,new):
  nonlocal source
  assert source.count(old)==1,(old,source.count(old))
  source=source.replace(old,new)
 change("stage=json.loads((ROOT/'output/merlin38813_native_preview_stage.json').read_text());tree=ROOT/stage['rootfs']", "candidate=json.loads((ROOT/'output/merlin38813_native_candidate_tests.json').read_text());stage=dict(rootfs=candidate['rootfs'],inventory_sha256=candidate['stage_inventory_sha256'],protected_sha256=candidate['protected_sha256'],image=candidate['image']);tree=ROOT/stage['rootfs']")
 change("'native_restore.c','native_center_event.sh','native_hook_probe.c','check_native_hooks.py'", "'native_restore.c','native_center_event.sh','native_hook_probe.c','check_native_hooks.py','check_candidate_runtime.py','launcher_exec_fixture.c','candidate_runtime.go'")
 change("'output/merlin38813_uu_matrix_tests.json']", "'output/merlin38813_uu_matrix_tests.json','output/merlin38813_native_candidate_tests.json',candidate['image']['image']]")
 change("'analysis/merlin_vpn_38813/native_hooks.go']:", "'analysis/merlin_vpn_38813/native_hooks.go','analysis/merlin_vpn_38813/candidate_runtime.go']:")
 change("text=(ROOT/n).read_text()", '''text=(ROOT/n).read_text()
  text=text.replace('/work/build/merlin38813-native-'+'hooks','/work/build/merlin38813-native-candidate-runtime')
  text=text.replace('/work/build/merlin38813-native-candidate-runtime/native_boot_bridge.so','/usr/lib/localmod/native_boot_bridge.so')
  if n.endswith('native_hooks.go'):
   assert text.count('onlineFixtureMain()')==1
   text=text.replace('onlineFixtureMain()','candidateReadWritePages(); onlineFixtureMain()')
   assert text.count('b, e := json.Marshal(')==1
   text=text.replace('b, e := json.Marshal(','checks = append(checks,candidateChecks...); b, e := json.Marshal(')
  if n.endswith('test_online.go'):
   marker='defer u.close()\\n\\ttest := '
   assert text.count(marker)==1
   text=text.replace(marker,'defer u.close()\\n\\tcandidateDuringUU(s,u)\\n\\ttest := ')''')
 source=source.replace('build/merlin38813-native-hooks','build/merlin38813-native-candidate-runtime')
 change("function=function.replace(old,'LD_PRELOAD=/work/build/merlin38813-native-candidate-runtime/native_boot_bridge.so:/work/build/native_hw_fixture.so:')", "function=function.replace(old,'LD_PRELOAD=/work/build/merlin38813-native-candidate-runtime/launcher_exec_fixture.so:/work/build/native_hw_fixture.so:')")
 marker="subprocess.run([*cc,'-shared','-fPIC','-o',str(work/'native_boot_bridge.so')"
 change(marker,"subprocess.run([*cc,'-shared','-fPIC','-o',str(work/'launcher_exec_fixture.so'),str(HERE/'launcher_exec_fixture.c'),'-ldl'],check=True)\n "+marker)
 change("job=job.replace(marker,'cp /work/build/merlin38813-native-candidate-runtime/native-center-event.sh /router/usr/libexec/localmod/\\nchmod 755 /router/usr/libexec/localmod/native-center-event.sh\\n'+marker)", "assert (tree/'usr/libexec/localmod/native-center-event.sh').read_bytes()==(HERE/'native_center_event.sh').read_bytes()")
 source=source.replace('merlin38813_native_hooks.log','merlin38813_candidate_runtime.log').replace('merlin38813_native_hooks_tests.json','merlin38813_candidate_runtime_tests.json')
 source=source.replace('LOCAL_NATIVE_MERLIN_HOOK_AUGMENTATION_PASS','LOCAL_NATIVE_MERLIN_CANDIDATE_RUNTIME_PASS')
 change("'New native hook bridge/event helper loaded only into the owned test; RC launcher/restore not staged or runtime-validated'", "'Actual candidate rc launcher and boot bridge executed for native UU and center aliases; target PID1 boot and restore kernel integration remain unverified'")
 folder=ROOT/'build/merlin38813-native-candidate-runtime';folder.mkdir(exist_ok=True)
 (folder/'derived_check.py').write_text(source)
 exec(compile(source,str(folder/'derived_check.py'),'exec'),dict(__name__='__main__',__file__=str(HERE/'check_candidate_runtime.py')))
if __name__=='__main__':main()
