#!/usr/bin/env python3
"""Exercise native UU control failures with the center and owned worker alive."""
import json,os,subprocess
from pathlib import Path
from prepare_hardening_overlay import prepare_resources,ROOT,sha
from run_readonly_linux import run
os.chdir(ROOT);files=prepare_resources()
sources=['build/test_uu_recovery.go','build/native_runtime_client.go','build/test_online.go','build/coexist_helpers.go']
subprocess.run(['go','build','-trimpath','-o','build/test-uu-recovery']+sources,check=True,env=dict(os.environ,GOOS='linux',GOARCH='arm64',CGO_ENABLED='0'))
inputs={p:sha(ROOT/p) for p in sources}
(ROOT/'build/real-plugin-phase').write_text('hardening-uu\n')
log=ROOT/'output/uu_recovery_run.log';text=run(log,timeout=300)
rows=[json.loads(l.removeprefix('UU_RECOVERY_RESULT ')) for l in text.splitlines() if l.startswith('UU_RECOVERY_RESULT ')];assert len(rows)==1 and all(rows[0]['checks'].values())
v=json.loads((ROOT/'output/verification.json').read_text());assert sha(ROOT/v['image'])==v['sha256']
(ROOT/'output/uu_recovery_tests.json').write_text(json.dumps(dict(status='SOURCE_OVERLAY_NATIVE_UU_RECOVERY_PASS',result=rows[0],base_candidate_sha256=v['sha256'],firmware_rebuilt=False,source_sha256=inputs,overlay_files=files,log_sha256=sha(log),limits=['DNS outage injected at owned transport boundary; no external DNS/WAN','WAN notifications and fresh native NTP cycle, not physical DHCP/PPP failover','Original native once-only policy retained; no automatic retry of UU mutation','Owned monitor and worker only; real UU account, entitlement and acceleration untested']),indent=2)+'\n')
print('PASS native UU recovery checks',len(rows[0]['checks']),flush=True)
