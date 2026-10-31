#!/usr/bin/env python3
"""Verify native authenticated HTTPS query completion with and without a UU worker."""
import hashlib,json,os,re,subprocess
from pathlib import Path
from prepare_real_plugins import prepare
from run_readonly_linux import run
ROOT=Path(__file__).resolve().parent.parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
 os.chdir(ROOT)
 v=json.loads((ROOT/'output/verification.json').read_text())
 assert sha(ROOT/v['image'])==v['sha256'] and all(v['checks'].values()) and not v['errors']
 stage=ROOT/'build/casefs/rootfs';back=ROOT/'build/casefs/roundtrip'
 paths=['usr/lib/localmod/httpd_bridge.so','usr/libexec/localmod/httpd','usr/libexec/localmod/rc.vendor','usr/libexec/localmod/plugin-txn','usr/libexec/localmod/bootstrap.sh','rom/etc/koolshare/scripts/base.sh','usr/sbin/curl','usr/sbin/wget']
 assert all((stage/p).read_bytes()==(back/p).read_bytes() for p in paths)
 assert (ROOT/'build/httpd_bridge.so').read_bytes()==(stage/'usr/lib/localmod/httpd_bridge.so').read_bytes()
 baseline=json.loads((ROOT/'output/https_r6_reproduction.json').read_text());assert baseline['status']=='R6_NATURALLY_REPRODUCED' and baseline['queries']==64 and len(baseline['failures'])==1
 assert sha(ROOT/'output/https_r6_reproduction.log')==baseline['log_sha256']
 assert baseline['candidate_sha256']=='d2650339ea0868c472db0f25009642fcf23a5335a40fe2c6a6c3bae1b1cc37eb'
 manifest=prepare()
 flags=['sources/zig-aarch64-macos-0.15.2/zig','cc','-target','arm-linux-gnueabi.2.26','-mcpu=cortex_a53','-O2']
 subprocess.run(flags+['-shared','-fPIC','-o','build/https_trace_fixture.so','build/https_trace_fixture.c','-ldl'],check=True)
 subprocess.run(flags+['-s','-o','build/relay-idle-fixture','build/relay_idle_fixture.c','-ldl'],check=True)
 subprocess.run(['go','build','-trimpath','-o','build/test-https-stability','build/test_https_stability.go','build/native_runtime_client.go','build/test_online.go','build/coexist_helpers.go'],check=True,env=dict(os.environ,GOOS='linux',GOARCH='arm64',CGO_ENABLED='0'))
 checks={};details={}
 for phase,total in [('https-stability-alone',36),('https-stability',68)]:
  (ROOT/'build/real-plugin-phase').write_text(phase+'\n')
  print('Native HTTPS stability VM:',phase,flush=True)
  text=run(ROOT/f'output/https_{phase}.log')
  rows=[l for l in text.splitlines() if l.startswith('READONLY_QUERY ')]
  ids=[int(re.search(r'id=(\d+)',l)[1]) for l in rows]
  assert len(rows)==total and len(set(ids))==total and all('status=200 ' in l and 'valid=true ' in l and 'error=<nil>' in l for l in rows)
  assert all(text.count('id='+str(i)+' removed\n')==1 for i in ids)
  result=[l for l in text.splitlines() if l.startswith('HTTPS_STABILITY_RESULT ')];assert len(result)==1
  assert f'queries={total} failures=0 ' in result[0] and 'uu_api_requests=1 uu_downloads=1 uu_launches=start ' in result[0]
  assert ('uu_running=false' if phase.endswith('alone') else 'uu_running=true') in result[0]
  assert text.count('INJECT_EINTR phase=before')==text.count('INJECT_EINTR phase=after')==1
  assert len(re.findall(r'FORCED_SIGNAL_QUERY id=\d+ signals=3 kernel_eintr=[1-9]\d*',text))==2 and text.count('returned=-1 errno=4')>=2
  assert not re.search(r'SSL_write .*returned=-',text) and not re.search(r'fwrite .*error=[1-9]',text)
  names=[l[5:] for l in text.splitlines() if l.startswith('PASS ') and 'early stdio' not in l]
  assert len(names)==len(set(names))==4,names
  checks.update({phase+'_'+n:True for n in names})
  checks.update({phase+'_'+n:True for n in ['every_authenticated_readonly_query_returns_complete_expected_json','before_and_after_header_eintr_resumes_without_resubmitting_request','repeated_real_sigalrm_keeps_tls_forwarding_and_each_backend_id_completes_once','native_tls_writes_complete_without_stream_errors','uu_native_control_download_and_launch_once']})
  details[phase]={'queries':total,'status_queries':total//2,'version_queries':total//2,'controlled_eintr_before_and_after_header':2,'sigalrm_queries':2,'signals_per_query':3,'observed_kernel_eintr':text.count('returned=-1 errno=4'),'result':result[0],'log_sha256':sha(ROOT/f'output/https_{phase}.log')}
 assert sha(ROOT/v['image'])==v['sha256'] and not (ROOT/'build/readonly-guest-write-probe').exists()
 report={'status':'LOCAL_NATIVE_HTTPS_STABILITY_PASS','candidate_image':v['image'],'candidate_sha256':v['sha256'],'checks':checks,'details':details,'r6_baseline':baseline,'production_files':{p:sha(stage/p) for p in paths},'test_fixtures':{p:sha(ROOT/p) for p in ['build/https_trace_fixture.so','build/relay-idle-fixture']},'scope':['104 distinct authenticated real DDNS-Go status/version RPCs, no automatic request retry','Real original ASUS TLS/login, httpdb/skipd/perp, unchanged real DDNS-Go plugin and native curl callback','Native UU NTP/download/checksum control flow with owned monitor/worker; query phase compares worker stopped vs running','Actual signal interruption plus deterministic EINTR boundary injection; same production receive helper tested with a one-second idle argument under a repeated signal stream; production remains 120 seconds','Config file, literal native plugin records, certificate archive and synthetic persistent/temporary UU data checked unchanged','No NIC, read-only workspace and disposable RAM root/JFFS; no router accessed or flashed'],'not_tested':['Physical router, stock kernel 4.1 timing, WAN downloads or long-running field stability','Real UU monitor/account/entitlement/game acceleration','Arbitrary TLS/network failures or arbitrary plugins; no guarantee against every cause of truncated responses']}
 (ROOT/'output/https_stability_tests.json').write_text(json.dumps(report,indent=2)+'\n')
 print('PASS',len(checks),'native HTTPS stability checks;',v['sha256'])
if __name__=='__main__':main()
