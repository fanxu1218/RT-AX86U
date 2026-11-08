#!/usr/bin/env python3
"""Read-only TLS cache/mallinfo observation on the original HTTPd."""
from device_config import compiler_flags
import json,os,re,subprocess,sys
from pathlib import Path
from check_memory import candidate,sha
from run_readonly_linux import run
ROOT=Path(__file__).resolve().parent.parent
os.chdir(ROOT);v,production=candidate()
overlay='--overlay' in sys.argv
if overlay:subprocess.run(['sources/zig-aarch64-macos-0.15.2/zig','cc',*compiler_flags(),'-O2','-shared','-fPIC','-o','build/httpd_bridge_next.so','sources/localmod/httpd_bridge.c','-ldl'],check=True)
subprocess.run(['sources/zig-aarch64-macos-0.15.2/zig','cc',*compiler_flags(),'-O2','-shared','-fPIC','-o','build/httpd_tls_cache_fixture.so','build/httpd_tls_cache_fixture.c','-ldl'],check=True)
sources=['build/test_soak.go','build/test_memory.go','build/memory_cycles.go','build/httpd_memory.go','build/native_runtime_client.go','build/test_online.go','build/coexist_helpers.go']
subprocess.run(['go','build','-trimpath','-o','build/test-soak']+sources,check=True,env=dict(os.environ,GOOS='linux',GOARCH='arm64',CGO_ENABLED='0'))
source_sha={p:sha(ROOT/p) for p in sources+['build/httpd_tls_cache_fixture.c']+(['sources/localmod/httpd_bridge.c'] if overlay else [])}
(ROOT/'build/real-plugin-phase').write_text('soak-httpd-cache'+('-overlay' if overlay else '')+'\n')
prefix='httpd_cache_bounded' if overlay else 'httpd_cache'
log=ROOT/f'output/{prefix}_run.log';text=run(log,timeout=360)
rows=[json.loads(l.removeprefix('HTTPD_CACHE_RESULT ')) for l in text.splitlines() if l.startswith('HTTPD_CACHE_RESULT ')];assert len(rows)==1
r=rows[0];assert r['protected_page_queries']==300 and r['data_preserved'] and r['uu_launches']==1
stats=[]
for line in text.splitlines():
 if line.startswith('TLS_CACHE '):stats.append({k:(val if k=='phase' else int(val)) for k,val in re.findall(r'(\w+)=([\w]+)',line)})
assert all(any(s['phase']==p for s in stats) for p in ['fresh1','resumed','fresh2'])
phases={p:[s for s in stats if s['phase']==p] for p in ['fresh1','resumed','fresh2']}
summary={p:dict(handshakes=len(s),resumed=sum(x['reused'] for x in s),first=s[0],last=s[-1]) for p,s in phases.items()}
assert all(len(s)>=100 for s in phases.values())
if overlay:assert all(s['capacity']<=256 and s['sessions']<=256 and s['timeout_seconds']<=300 for s in stats)
assert candidate()==(v,production)
(ROOT/f'output/{prefix}_tests.json').write_text(json.dumps(dict(status='SOURCE_OVERLAY_CACHE_BOUNDS_PASS' if overlay else 'TLS_CACHE_OBSERVATION_COMPLETE',candidate_sha256=v['sha256'],firmware_rebuilt=False,overlay_bridge_sha256=sha(ROOT/'build/httpd_bridge_next.so') if overlay else None,result=r,phase_stats=summary,cache_samples=stats,source_sha256=source_sha,log_sha256=sha(log),limits=['Observer does not change allocator/cache settings; overlay changes cache capacity/timeout only' if overlay else 'No TLS/cache or allocator settings changed','Public allocator totals include all allocations, not object ownership','No account/session IDs/cert keys logged']),indent=2)+'\n')
print(json.dumps(summary),flush=True)
