#!/usr/bin/env python3
"""Native TLS/authenticated diagnostics, including unavailable center/recovery."""
from device_config import render_source, compiler_flags
from release_config import CONFIG
import json,os,subprocess
from prepare_hardening_overlay import prepare_resources,ROOT,sha
from run_readonly_linux import run
os.chdir(ROOT);prepare_resources();folder=ROOT/'build/hardening-overlay'
flags=['sources/zig-aarch64-macos-0.15.2/zig','cc',*compiler_flags(),'-O2']
subprocess.run(flags+['-shared','-fPIC','-o','build/httpd_bridge_next.so','sources/localmod/httpd_bridge.c','-ldl'],check=True)
p=folder/'usr/libexec/localmod/localmod-status';subprocess.run(flags+['-o',str(p),'sources/localmod/status.c'],check=True);p.chmod(0o755)
p=folder/'www/Module_Localmod.asp';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(render_source('sources/localmod/Module_Localmod.asp',dict(CONFIG,revision='r9')))
sources=['build/test_health.go','build/native_runtime_client.go','build/test_online.go','build/coexist_helpers.go']
inputs={p:sha(ROOT/p) for p in sources+['sources/localmod/health.h','sources/localmod/journal.h','sources/localmod/sha256.h','sources/localmod/status.c','sources/localmod/httpd_bridge.c','sources/localmod/Module_Localmod.asp']}
subprocess.run(['go','build','-trimpath','-o','build/test-health']+sources,check=True,env=dict(os.environ,GOOS='linux',GOARCH='arm64',CGO_ENABLED='0'))
(ROOT/'build/real-plugin-phase').write_text('hardening-health\n')
log=ROOT/'output/health_run.log';text=run(log,timeout=240)
rows=[json.loads(l.removeprefix('HEALTH_RESULT ')) for l in text.splitlines() if l.startswith('HEALTH_RESULT ')];assert len(rows)==1 and all(rows[0]['checks'].values())
(ROOT/'output/health_tests.json').write_text(json.dumps(dict(status='SOURCE_OVERLAY_NATIVE_HEALTH_PASS',result=rows[0],firmware_rebuilt=False,source_sha256=inputs,log_sha256=sha(log)),indent=2)+'\n')
print('PASS native health checks',len(rows[0]['checks']),flush=True)
