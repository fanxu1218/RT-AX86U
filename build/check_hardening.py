#!/usr/bin/env python3
"""All new behaviors on exact staged/readback candidate bytes, without overlay."""
import hashlib,json,os,subprocess
from pathlib import Path
from check_installer_boundaries import fixtures
from check_memory import candidate,sha
from run_readonly_linux import run
from release_config import CONFIG,ROOT
os.chdir(ROOT);v,production=candidate();assert v['image']==CONFIG['image']
stage=ROOT/'build/casefs/rootfs';back=ROOT/'build/casefs/roundtrip'
paths=['usr/libexec/localmod/'+x for x in ['archive-guard','plugin-run','log-limit','localmod-status','localmod-event','bootstrap.sh','installer-guard.sh']]+['www/Module_Localmod.asp','usr/lib/localmod/httpd_bridge.so']
for p in paths:assert (stage/p).read_bytes()==(back/p).read_bytes()
artifacts={p:sha(stage/p) for p in paths};fixtures()
arm=['sources/zig-aarch64-macos-0.15.2/zig','cc','-target','arm-linux-gnueabi.2.26','-mcpu=cortex_a53','-O2','-s']
fixture=['-DLM_BASE="/tmp/localmod-bounds"','-DLM_DISPATCH="/tmp/bounds-dispatch.sh"','-DLM_LOGGER="/work/build/log-limit-bounds-fixture"']
for name,sources in [('log-limit',['sources/localmod/log_limit.c']),('event',['sources/localmod/event.c','sources/localmod/runtime.c']),('barrier',['build/barrier_bounds_fixture.c','sources/localmod/runtime.c'])]:
 subprocess.run(arm+fixture+['-o','build/'+name+'-bounds-fixture']+sources,check=True)
for name,source in [('soak-init','soak_init_fixture.c'),('memory-exec','memory_exec_fixture.c')]:
 subprocess.run(['sources/zig-aarch64-macos-0.15.2/zig','cc','-target','aarch64-linux-musl','-static','-O2','-o','build/'+name+'-fixture','build/'+source],check=True)
subprocess.run(arm+['-shared','-fPIC','-o','build/httpd_tls_cache_fixture.so','build/httpd_tls_cache_fixture.c','-ldl'],check=True)
common=['build/native_runtime_client.go','build/test_online.go','build/coexist_helpers.go']
programs={
 'installer-boundaries':['build/test_installer_boundaries.go']+common,
 'resource-bounds':['build/test_resource_bounds.go']+common,
 'uu-recovery':['build/test_uu_recovery.go']+common,
 'health':['build/test_health.go']+common,
 'soak':['build/test_soak.go','build/test_memory.go','build/memory_cycles.go','build/httpd_memory.go']+common}
inputs={p:sha(ROOT/p) for p in sorted(set(sum(programs.values(),[])))}
for name,sources in programs.items():subprocess.run(['go','build','-trimpath','-o','build/test-'+name]+sources,check=True,env=dict(os.environ,GOOS='linux',GOARCH='arm64',CGO_ENABLED='0'))
details={}
for phase,marker in [('candidate-installer','INSTALLER_BOUNDARY_RESULT'),('candidate-resources','RESOURCE_BOUNDS_RESULT'),('candidate-uu','UU_RECOVERY_RESULT'),('candidate-health','HEALTH_RESULT'),('soak-httpd-cache','HTTPD_CACHE_RESULT'),('soak-httpd-memory','HTTPD_MEMORY_RESULT')]:
 (ROOT/'build/real-plugin-phase').write_text(phase+'\n');print('Final candidate VM:',phase,flush=True)
 log=ROOT/('output/candidate_'+phase+'.log');text=run(log,timeout=660 if phase.endswith('memory') else 360)
 rows=[json.loads(l.removeprefix(marker+' ')) for l in text.splitlines() if l.startswith(marker+' ')];assert len(rows)==1
 r=rows[0]
 if 'checks' in r:assert r['checks'] and all(r['checks'].values())
 if phase=='candidate-installer':assert len(r['archive_cases'])==28
 if phase=='soak-httpd-cache':
  import re
  stats=[dict(re.findall(r'(\w+)=([\w]+)',l)) for l in text.splitlines() if l.startswith('TLS_CACHE ')]
  assert len(stats)>=300 and all(int(s['capacity'])<=256 and int(s['sessions'])<=256 and int(s['timeout_seconds'])<=300 for s in stats)
 if phase=='soak-httpd-memory':assert r['healthy_queries']==243 and r['slow_disconnects']==6 and r['data_preserved'] and r['logout_and_relogin_verified']
 details[phase]=dict(result=r,log_sha256=sha(log))
assert candidate()==(v,production)
assert all(sha(stage/p)==sha(back/p)==digest for p,digest in artifacts.items())
assert all(sha(ROOT/p)==digest for p,digest in inputs.items())
(ROOT/'output/hardening_tests.json').write_text(json.dumps(dict(status='FINAL_CANDIDATE_HARDENING_PASS',candidate_image=v['image'],candidate_sha256=v['sha256'],production_files=artifacts,source_sha256=inputs,phases=details,source_overlay_used=False,physical_router_accessed=False),indent=2)+'\n')
print('PASS final candidate hardening, TLS cache and six-round coexistence',flush=True)
