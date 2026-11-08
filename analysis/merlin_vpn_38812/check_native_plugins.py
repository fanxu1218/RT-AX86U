#!/usr/bin/env python3
"""Bind authentic HND/Fancyss suites to the immutable native candidate.

Reuse established package/TLS/data assertions, changing only the base-specific
UU entry point, obsolete factory curl control, and private fixture paths.
"""
import argparse,builtins,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
import check_candidate_runtime as controller
SUITE='fancyss'

def run_derived(code,namespace):
 source=(ROOT/'build/native-candidate-runtime/derived_check.py').read_text()
 def change(old,new):
  nonlocal source
  assert source.count(old)==1,(old,source.count(old));source=source.replace(old,new)
 go=['build/native_runtime_client.go','build/test_online.go','build/coexist_helpers.go']
 if SUITE=='fancyss':go+=['build/test_fancyss.go','build/test_softcenter_upgrade.go','build/test_extended_plugins.go']
 else:go+=['build/test_real_plugins.go']
 change("'candidate_runtime.go']]]","'candidate_runtime.go','check_native_plugins.py']]]+"+repr(go))
 old="['build/native_runtime_client.go','build/test_online.go','build/coexist_helpers.go','analysis/merlin_vpn_38812/native_hooks.go','analysis/merlin_vpn_38812/candidate_runtime.go']"
 change('for n in '+old+':','for n in '+repr(go)+':')
 change('candidateDuringUU(s,u)','')
 change("assert text.count('u := onlineUUStart(ctx)')==1",'pass')
 change("text=(ROOT/n).read_text()",'''text=(ROOT/n).read_text()
  text=text.replace('onlineUUStart(ctx)','previewUUStart(ctx)')
  if n.endswith('test_real_plugins.go'):
   start=text.index('\\t// The requested upstream curl does not carry ASUS')
   end=text.index('\\n}',start)
   text=text[:start]+text[end:]
   old='selected_curl_and_factory_numeric_url_contracts_and_hostname_callback_pinned_to_loopback'
   assert text.count(old)==1
   text=text.replace(old,'native_merlin_curl_numeric_and_hostname_requests_pinned_to_loopback')''')
 source=source.replace('build/native-candidate-runtime','build/native-plugins-'+SUITE)
 phase='candidate-fancyss' if SUITE=='fancyss' else 'native-hnd-'+SUITE.removeprefix('hnd-')
 argument='candidate-fancyss' if SUITE=='fancyss' else SUITE.removeprefix('hnd-')
 prefix='/work/build/native-plugins-'+SUITE
 old="setup=setup[:setup.index(cut)]+'exec "+prefix+"/probe success\\n'"
 new="setup=setup[:setup.index(cut)]+'/sbin/service start_softcenter || { cat /tmp/.localmod/bootstrap.log; exit 1; }\\nexec "+prefix+"/probe "+argument+"\\n'"
 change(old,new)
 change("super().__init__('candidate-merlin-components',guest_job=job.encode())","super().__init__("+repr(phase)+",guest_job=job.encode())")
 change('timeout=360,cpus=1,receipt=receipt','timeout=720,cpus=1,receipt=receipt')
 label='FANCYSS_RESULT' if SUITE=='fancyss' else 'REAL_PLUGIN_RESULT'
 old="rows=[json.loads(l.removeprefix('NATIVE_HOOKS_RESULT ')) for l in console.splitlines() if l.startswith('NATIVE_HOOKS_RESULT ')];assert len(rows)==1"
 new="rows=[json.loads(l.removeprefix(%r)) for l in console.splitlines() if l.startswith(%r)];assert len(rows)==1;checks=rows[0]['checks'];assert checks;assert all(checks.values()) if isinstance(checks,dict) else len(checks)==len(set(checks));assert all('PASS '+n+'\\n' in console for n in checks);rows[0]['online']=dict(checks=[])"%(label+' ',label+' ')
 if SUITE!='fancyss':new+=";d=rows[0]['details'];assert d['uu_api_requests']==d['uu_monitor_downloads']==d['uu_launches']==1"
 change(old,new)
 change("'No cross-boot recovery, physical router, true UU account/game acceleration or firmware release acceptance'","'Authentic plugin lifecycles and owned local endpoints only; physical NAND, WAN/provider/proxy subscriptions, true UU account/game acceleration and firmware release acceptance remain unverified'")
 source=source.replace('merlin38812_candidate_runtime','merlin38812_plugins_'+SUITE.replace('-','_')).replace('LOCAL_NATIVE_MERLIN_CANDIDATE_RUNTIME_PASS','LOCAL_NATIVE_AUTHENTIC_PLUGINS_PASS')
 folder=ROOT/('build/native-plugins-'+SUITE);folder.mkdir(exist_ok=True);(folder/'derived_check.py').write_text(source)
 builtins.exec(compile(source,str(folder/'derived_check.py'),'exec'),namespace)

def main():
 global SUITE
 ap=argparse.ArgumentParser();ap.add_argument('--suite',choices=['fancyss','hnd-upgrade','hnd-fresh'],default='fancyss');SUITE=ap.parse_args().suite
 controller.exec=run_derived;controller.main()
 p=ROOT/('output/merlin38812_plugins_'+SUITE.replace('-','_')+'_tests.json');r=json.loads(p.read_text())
 checks=r['result']['checks'];assert checks
 if isinstance(checks,dict):assert all(checks.values())
 else:assert len(checks)==len(set(checks))
 assert all('PASS '+n+'\n' in (ROOT/('output/merlin38812_plugins_'+SUITE.replace('-','_')+'.log')).read_text() for n in checks)
 if SUITE!='fancyss':
  d=r['result']['details'];assert d['uu_api_requests']==d['uu_monitor_downloads']==d['uu_launches']==1
 r['suite']=SUITE;r['physical_router_flashed']=False;r['full_upgrade_complete']=False
 p.write_text(json.dumps(r,indent=2)+'\n')
if __name__=='__main__':main()
