#!/usr/bin/env python3
"""Check event/log limits on a source overlay in the disposable native root."""
import hashlib,json,os,subprocess
from pathlib import Path
from check_installer_boundaries import overlay
from run_readonly_linux import run
ROOT=Path(__file__).resolve().parent.parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
os.chdir(ROOT)
files=overlay();folder=ROOT/'build/hardening-overlay'
flags=['sources/zig-aarch64-macos-0.15.2/zig','cc','-target','arm-linux-gnueabi.2.26','-mcpu=cortex_a53','-O2','-s']
for name,src,extra in [('log-limit','log_limit.c',[]),('localmod-event','event.c',['sources/localmod/runtime.c'])]:
 p=folder/'usr/libexec/localmod'/name
 subprocess.run(flags+['-o',str(p),'sources/localmod/'+src]+extra,check=True);p.chmod(0o755)
p=folder/'usr/libexec/localmod/bootstrap.sh';p.write_bytes((ROOT/'sources/localmod/bootstrap.sh').read_bytes());p.chmod(0o755)
fixture=['-DLM_BASE="/tmp/localmod-bounds"','-DLM_DISPATCH="/tmp/bounds-dispatch.sh"','-DLM_LOGGER="/work/build/log-limit-bounds-fixture"']
subprocess.run(flags+fixture+['-o','build/log-limit-bounds-fixture','sources/localmod/log_limit.c'],check=True)
subprocess.run(flags+fixture+['-o','build/event-bounds-fixture','sources/localmod/event.c','sources/localmod/runtime.c'],check=True)
subprocess.run(flags+fixture+['-o','build/barrier-bounds-fixture','build/barrier_bounds_fixture.c','sources/localmod/runtime.c'],check=True)
subprocess.run(['go','build','-trimpath','-o','build/test-resource-bounds','build/test_resource_bounds.go','build/native_runtime_client.go','build/test_online.go','build/coexist_helpers.go'],check=True,env=dict(os.environ,GOOS='linux',GOARCH='arm64',CGO_ENABLED='0'))
files={str(p.relative_to(folder)):sha(p) for p in folder.rglob('*') if p.is_file()}
(ROOT/'build/real-plugin-phase').write_text('hardening-resources\n')
log=ROOT/'output/resource_bounds_run.log';text=run(log,timeout=300)
rows=[json.loads(l.removeprefix('RESOURCE_BOUNDS_RESULT ')) for l in text.splitlines() if l.startswith('RESOURCE_BOUNDS_RESULT ')];assert len(rows)==1 and all(rows[0]['checks'].values())
v=json.loads((ROOT/'output/verification.json').read_text());assert sha(ROOT/v['image'])==v['sha256']
(ROOT/'output/resource_bounds_tests.json').write_text(json.dumps(dict(status='SOURCE_OVERLAY_CHECKS_PASS',result=rows[0],base_candidate_sha256=v['sha256'],firmware_rebuilt=False,overlay_files=files,log_sha256=sha(log)),indent=2)+'\n')
print('PASS resource checks',len(rows[0]['checks']))
