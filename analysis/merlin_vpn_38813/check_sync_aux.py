#!/usr/bin/env python3
"""Observe blocking semantics on the immutable candidate, without changing it."""
import argparse,builtins,json,hashlib,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
import check_candidate_runtime as candidate_controller
OVERLAY=False

def run_derived(code, namespace):
 source=(ROOT/'build/merlin38813-native-candidate-runtime/derived_check.py').read_text()
 def change(old,new):
  nonlocal source
  assert source.count(old)==1,(old,source.count(old));source=source.replace(old,new)
 change("'candidate_runtime.go']]]", "'candidate_runtime.go','sync_aux.go','sync_aux_probe.c','check_sync_aux.py']]]")
 change("'analysis/merlin_vpn_38813/native_hooks.go','analysis/merlin_vpn_38813/candidate_runtime.go']:","'analysis/merlin_vpn_38813/sync_aux.go']:")
 change('candidateDuringUU(s,u)','')
 change("str(HERE/'native_hook_probe.c')","str(HERE/'sync_aux_probe.c')")
 change("'-lshared','-lnvram','-Wl,--allow-shlib-undefined'","'-lshared','-lnvram','-ldl','-Wl,--allow-shlib-undefined'")
 source=source.replace('build/merlin38813-native-candidate-runtime','build/merlin38813-native-sync-aux')
 if OVERLAY:
  change("text=(ROOT/n).read_text()", "text=(ROOT/n).read_text()\n  if n.endswith('sync_aux.go'):text=text.replace('/usr/lib/localmod/native_boot_bridge.so','/work/build/merlin38813-native-sync-aux/native_boot_bridge.so')")
  change("text=text.replace('/work/build/merlin38813-native-sync-aux/native_boot_bridge.so','/usr/lib/localmod/native_boot_bridge.so')", "# Keep the explicitly requested source overlay path for this focused run.")
 source=source.replace('merlin38813_candidate_runtime','merlin38813_sync_aux')
 source=source.replace('NATIVE_HOOKS_RESULT','SYNC_AUX_RESULT')
 source=source.replace('LOCAL_NATIVE_MERLIN_CANDIDATE_RUNTIME_PASS','SYNC_AUX_OBSERVATIONS_RECORDED')
 folder=ROOT/'build/merlin38813-native-sync-aux';folder.mkdir(exist_ok=True)
 (folder/'derived_check.py').write_text(source)
 builtins.exec(compile(source,str(folder/'derived_check.py'),'exec'),namespace)

def main():
 global OVERLAY
 ap=argparse.ArgumentParser();ap.add_argument('--overlay',action='store_true');args=ap.parse_args();OVERLAY=args.overlay
 candidate_controller.exec=run_derived
 candidate_controller.main()
 p=ROOT/'output/merlin38813_sync_aux_tests.json';r=json.loads(p.read_text())
 matches=all(c['contract_matches'] for c in r['result']['cases'])
 expected='/work/build/merlin38813-native-sync-aux/native_boot_bridge.so' if OVERLAY else '/usr/lib/localmod/native_boot_bridge.so'
 assert all(c['native_return']['loaded_bridge']==expected for c in r['result']['cases']), 'Unexpected library ownership'
 r['status']='LOCAL_SYNC_CENTER_HELPER_CONTRACT_PASS' if matches else 'LOCAL_SYNC_CENTER_HELPER_RACE_REPRODUCED'
 r['scope']='Native blocking timeout versus added software-center helper; owned delayed scripts only'
 r['fresh_source_overlay_loaded']=OVERLAY
 r['production_candidate_modified']=False
 r['source_sha256']['analysis/merlin_vpn_38813/check_sync_aux.py']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 p.write_text(json.dumps(r,indent=2)+'\n');print(r['status'])
if __name__=='__main__':main()
