#!/usr/bin/env python3
"""Original r7 HTTPd map separation plus bounded concurrent/disconnect rounds."""
import json,os,subprocess
from pathlib import Path
from check_memory import candidate,sha
from prepare_real_plugins import prepare
from run_readonly_linux import run
ROOT=Path(__file__).resolve().parent.parent
os.chdir(ROOT);v,production=candidate();prepare()
flags=['sources/zig-aarch64-macos-0.15.2/zig','cc','-O2']
subprocess.run(flags+['-target','aarch64-linux-musl','-static','-s','-o','build/memory-exec-fixture','build/memory_exec_fixture.c'],check=True)
subprocess.run(flags+['-target','aarch64-linux-musl','-static','-s','-o','build/soak-init-fixture','build/soak_init_fixture.c'],check=True)
subprocess.run(flags+['-target','arm-linux-gnueabi.2.26','-mcpu=cortex_a53','-shared','-fPIC','-o','build/https_trace_fixture.so','build/https_trace_fixture.c','-ldl'],check=True)
sources=['build/test_soak.go','build/test_memory.go','build/memory_cycles.go','build/httpd_memory.go','build/native_runtime_client.go','build/test_online.go','build/coexist_helpers.go']
subprocess.run(['go','build','-trimpath','-o','build/test-soak']+sources,check=True,env=dict(os.environ,GOOS='linux',GOARCH='arm64',CGO_ENABLED='0'))
(ROOT/'build/real-plugin-phase').write_text('soak-httpd-memory\n')
log=ROOT/'output/httpd_memory_run.log';text=run(log,timeout=660)
results=[json.loads(l.removeprefix('HTTPD_MEMORY_RESULT ')) for l in text.splitlines() if l.startswith('HTTPD_MEMORY_RESULT ')];assert len(results)==1
r=results[0];assert r['rounds']==6 and r['healthy_queries']==243 and r['slow_disconnects']==6 and r['data_preserved'] and r['uu_launches']==1 and r['logout_and_relogin_verified']
assert r['duration_seconds']>=200
samples=r['samples'];assert len(samples)==15 and len({s['pid'] for s in samples})==1
for s in samples:
 assert s['target_mapping_rss_kib']+s['qemu_host_mapping_rss_kib']==s['smaps_rss_kib']
 assert s['thp_enabled']==0 and not any(s['mapping_groups_anon_huge_pages_kib'].values())
 assert s['perfmap']['entries']==s['perfmap']['entries_in_host_executable_maps']>0
idle=[s for s in samples if s['stage'].startswith('idle')]
keys=['target_mapping_rss_kib','qemu_host_mapping_rss_kib','fds','threads']
observation={key:dict(first=idle[0][key],last=idle[-1][key],delta=idle[-1][key]-idle[0][key],min=min(s[key] for s in idle),max=max(s[key] for s in idle)) for key in keys}
assert candidate()==(v,production)
report=dict(status='LOCAL_HTTPD_MEMORY_AND_CONCURRENCY_PASS',candidate_image=v['image'],candidate_sha256=v['sha256'],production_files=production,result=r,idle_observation=observation,log_sha256=sha(log),source_sha256={p:sha(ROOT/p) for p in sources},checks={k:True for k in ['same_native_httpd_pid_across_six_load_idle_rounds','four_clients_complete_distinct_queries_without_retry','six_partial_tls_disconnects_allow_subsequent_queries','logout_revokes_old_token_and_new_login_works','target_and_qemu_mapping_rss_sum_to_total','perfmap_addresses_only_match_host_executable_maps','process_thp_disabled_and_no_hugepages','plugin_data_db_certificate_and_owned_uu_preserved']},limits=['Original C HTTPd has no Go GC trace; RSS is not live allocation size','Finite six-round observation does not establish leak freedom','Partial TLS clients close after 100ms; arbitrary long slowloris attacks not asserted','No physical router or real UU account/traffic'])
(ROOT/'output/httpd_memory_tests.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS native HTTPd concurrency/memory',json.dumps(observation),flush=True)
