#!/usr/bin/env python3
"""Bounded live-time coexistence run; never changes the candidate firmware."""
import os,sys,subprocess,json,hashlib,re
from pathlib import Path
from prepare_real_plugins import prepare
from run_readonly_linux import run
ROOT=Path(__file__).resolve().parent.parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 os.chdir(ROOT)
 v=json.loads((ROOT/'output/verification.json').read_text());assert sha(ROOT/v['image'])==v['sha256'] and all(v['checks'].values()) and not v['errors']
 stage=ROOT/'build/casefs/rootfs';back=ROOT/'build/casefs/roundtrip'
 paths=['usr/lib/localmod/httpd_bridge.so','usr/libexec/localmod/httpd','usr/libexec/localmod/rc.vendor','usr/libexec/localmod/plugin-txn','usr/libexec/localmod/bootstrap.sh','rom/etc/koolshare/scripts/base.sh','usr/sbin/curl','usr/sbin/wget']
 assert all((stage/p).read_bytes()==(back/p).read_bytes() for p in paths)
 assert (ROOT/'build/httpd_bridge.so').read_bytes()==(stage/paths[0]).read_bytes()
 prepare()
 flags=['sources/zig-aarch64-macos-0.15.2/zig','cc','-O2']
 subprocess.run(flags+['-target','aarch64-linux-musl','-static','-s','-o','build/soak-init-fixture','build/soak_init_fixture.c'],check=True)
 subprocess.run(flags+['-target','arm-linux-gnueabi.2.26','-mcpu=cortex_a53','-shared','-fPIC','-o','build/https_trace_fixture.so','build/https_trace_fixture.c','-ldl'],check=True)
 subprocess.run(['go','build','-trimpath','-o','build/test-soak','build/test_soak.go','build/native_runtime_client.go','build/test_online.go','build/coexist_helpers.go'],check=True,env=dict(os.environ,GOOS='linux',GOARCH='arm64',CGO_ENABLED='0'))
 smoke='--smoke' in sys.argv;phase='soak-smoke' if smoke else 'soak-30m'
 (ROOT/'build/real-plugin-phase').write_text(phase+'\n')
 print('Running',phase,flush=True)
 log=ROOT/f'output/{phase}.log'
 text=run(log,timeout=400 if smoke else 2160)
 rows=[json.loads(l.removeprefix('SOAK_RESULT ')) for l in text.splitlines() if l.startswith('SOAK_RESULT ')];assert len(rows)==1
 result=rows[0];assert result['duration_seconds']>=result['requested_duration_seconds']==(100 if smoke else 1800)
 assert result['healthy_queries']>=(60 if smoke else 1000) and result['unplanned_query_failures']==0
 assert result['data_preserved'] and result['tls_archive_preserved'] and result['private_api_denied']
 kinds=['abort','partial','backend','center','ddns','uu','tls','signals'];assert all(result['counts'].get(k,0)>=(1 if smoke else 2) for k in kinds)
 assert result['uu_launches']==1+result['counts']['uu']
 assert len(result['samples'])>=(4 if smoke else 85)
 windows=re.findall(r'(center_restart|ddns_restart|uu_restart)_reads=(\d+) unavailable=(\d+)',text)
 assert {w[0] for w in windows}=={'center_restart','ddns_restart','uu_restart'} and all(int(n)>0 for _,n,_ in windows)
 assert all(int(n)==0 for k,_,n in windows if k=='uu_restart')
 assert 'SOAK_REAPER orphans_reaped=' in text and 'SOAK_FAILURE' not in text and not (ROOT/'build/readonly-guest-write-probe').exists()
 assert sha(ROOT/v['image'])==v['sha256']
 grouped={}
 for sample in result['samples']:
  for name in ['httpd','httpdb','skipd','ddnsgo','uu']:
   row=sample[name];assert row['fds']>=0 and row['rss_kib']>0
   grouped.setdefault((name,row['pid']),[]).append(row)
 resources=[]
 for (name,pid),rows in sorted(grouped.items()):
  resources.append({'name':name,'pid':pid,'samples':len(rows),'fd_min':min(r['fds'] for r in rows),'fd_max':max(r['fds'] for r in rows),'rss_min_kib':min(r['rss_kib'] for r in rows),'rss_max_kib':max(r['rss_kib'] for r in rows)})
 report={'status':'LOCAL_SOAK_SMOKE_PASS' if smoke else 'LOCAL_30_MINUTE_SOAK_PASS','candidate_image':v['image'],'candidate_sha256':v['sha256'],'result':result,'maintenance_windows':[{'name':k,'queries':int(n),'expected_unavailable':int(bad)} for k,n,bad in windows],'resource_ranges':resources,'orphan_children_reaped':int(re.search(r'SOAK_REAPER orphans_reaped=(\d+)',text)[1]),'resource_observation':'DDNS-Go QEMU process RSS increased in steps; cache/runtime/emulation overhead versus slow leak remains unclassified. FD counts are sampled, not a proof of leak freedom.','log_sha256':sha(log),'production_files':{p:sha(stage/p) for p in paths},'checks':{k:True for k in ['actual_elapsed_time_meets_requested_duration','healthy_queries_complete_without_automatic_retry','client_rst_and_partial_body_disconnect_allow_later_independent_queries','backend_kill_respawns_and_later_queries_recover','center_restart_under_continuous_polling_recovers','ddns_restart_under_continuous_polling_recovers','uu_restart_does_not_interrupt_center_queries','https_restart_preserves_certificate_and_reauthenticates','repeated_sigalrm_keeps_complete_response','plugin_files_and_native_database_records_preserved','uu_synthetic_persistent_and_temporary_data_preserved','only_planned_uu_restarts_observed','private_api_stays_denied_to_unprivileged_ports','resource_samples_have_live_processes_and_valid_fd_rss_counts','workspace_readonly_no_nic_no_physical_router']},'scope':['Single disposable ARM64 VM; original ASUS ARM32 HTTPS/login/rc and unmodified real DDNS-Go plugin; no physical router/NIC',str(result['requested_duration_seconds'])+' seconds measured with a monotonic clock after installation/setup; not accelerated time','New IDs for every request; queries during explicitly planned center/DDNS maintenance can be unavailable; UU restart must not interrupt queries','Owned synthetic UU monitor/heartbeat worker and test data; original native NTP/download/checksum startup flow','Test-only subreaper supplies orphan reaping for the minimal guest shell PID 1; it never kills live services','FD/RSS samples are observations per PID, not proof that no slow leak exists'],'not_tested':['Stock 4.1 kernel and physical router/NAND/UBIFS','Real UU monitor/account/entitlement/game traffic or WAN provider APIs','Day/week-long operation, high client concurrency and all network failures']}
 (ROOT/f'output/{phase}_tests.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'status':report['status'],'seconds':result['duration_seconds'],'queries':result['healthy_queries'],'events':result['events'],'sha256':v['sha256']}),flush=True)
if __name__=='__main__':main()
