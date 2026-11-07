#!/usr/bin/env python3
"""Input-phase signal/timeout control on overlay or exact readback candidate."""
import argparse,json,shutil,subprocess,os,hashlib,time
from pathlib import Path
from check_interrupt import compile_fixtures
from run_readonly_linux import run
from release_config import ROOT,CONFIG
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--candidate',action='store_true');a=ap.parse_args();os.chdir(ROOT)
 v=json.loads(Path('output/verification.json').read_text());assert sha(ROOT/v['image'])==v['sha256']
 if a.candidate:
  assert v['image']==CONFIG['image']
  assert Path('build/httpd_bridge.so').read_bytes()==Path('build/casefs/roundtrip/usr/lib/localmod/httpd_bridge.so').read_bytes()
 flags=['sources/zig-aarch64-macos-0.15.2/zig','cc','-target','arm-linux-gnueabi.2.26','-mcpu=cortex_a53','-O2','-s','-shared','-fPIC']
 inputs={p:sha(Path(p)) for p in ['build/native_tls_probe_fixture.c','build/interrupt_scenarios.go','build/check_tls_input.py','sources/localmod/httpd_bridge.c','build/native_runtime_client.go']}
 subprocess.run(flags+['-o','build/httpd_tls_cache_fixture.so','build/native_tls_probe_fixture.c','-ldl'],check=True);compile_fixtures()
 if not a.candidate:subprocess.run(flags+['-o','build/httpd_bridge_patched.so','sources/localmod/httpd_bridge.c','-ldl'],check=True)
 code=subprocess.check_output(['git','show','a2ff36d:sources/localmod/httpd_bridge.c']);Path('build/r7-input-baseline.c').write_bytes(code)
 subprocess.run(flags+['-o','build/httpd_bridge_r7_input.so','build/r7-input-baseline.c','-ldl'],check=True)
 Path('build/irq-tls-probe').write_text('metadata only\n');results={}
 try:
  for old in [False,True]:
   label='r7' if old else 'fixed';flag=Path('build/irq-old-httpd-bridge')
   if old or not a.candidate:
    shutil.copyfile('build/httpd_bridge_r7_input.so' if old else 'build/httpd_bridge_patched.so','build/httpd_bridge_next.so');flag.write_text('owned adapter comparison\n')
   else:flag.unlink(missing_ok=True)
   disk=Path(f'build/interrupt-private/tls-input-{label}-{time.time_ns()}.img');shutil.copyfile('build/interrupt-private/foundation.img',disk);disk.chmod(0o600)
   Path('build/interrupt-phase.json').write_text(json.dumps(dict(case='tls-input-probe',boot='tls-input-probe',initialize=False))+'\n');Path('build/real-plugin-phase').write_text('interrupt-run\n')
   log=Path('output/candidate_tls_input_'+label+'.log');text=run(log,state_disk=disk,timeout=180)
   rows=[json.loads(l.removeprefix('TLS_INPUT_RESULT ')) for l in text.splitlines() if l.startswith('TLS_INPUT_RESULT ')];assert len(rows)==1
   cases=rows[0];assert len(cases)==12
   if not old:assert all(x['code']==200 and x['valid'] for x in cases[:10]) and cases[10]['code']==200 and cases[10]['valid'] and cases[10]['script_invocations']==1 and cases[-1]['disconnected'] and 4.8<=cases[-1]['elapsed_seconds']<6.5,cases
   else:assert all(x['code']==200 and x['valid'] for x in cases[:4]) and all(not x['valid'] for x in cases[4:10]),cases
   results[label]=dict(cases=cases,log_sha256=sha(log));print('TLS input comparison',label,cases,flush=True)
   disk.unlink()
 finally:
  Path('build/irq-old-httpd-bridge').unlink(missing_ok=True);Path('build/irq-tls-probe').unlink(missing_ok=True)
 assert inputs=={p:sha(Path(p)) for p in inputs}
 Path('output/tls_input_tests.json').write_text(json.dumps(dict(status='FINAL_CANDIDATE_NATIVE_INPUT_SIGNAL_PASS' if a.candidate else 'SOURCE_OVERLAY_NATIVE_INPUT_SIGNAL_PASS',candidate_sha256=v['sha256'],results=results,firmware_rebuilt=a.candidate,source_sha256=inputs,r7_baseline_source_commit='a2ff36df57a555ce6319dc82e2e230c3ec5db15d',limits=['Owned partial-header/before-request-line signal controls; does not retroactively identify every earlier EOF','Same TLS read resumed within original receive budget; no HTTP request resubmitted','Native certificate, crypto and authentication retained; no router flashed']),indent=2)+'\n')
if __name__=='__main__':main()
