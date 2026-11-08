#!/usr/bin/env python3
"""Isolated r9-r2 latency attribution and native same-PID memory cycles."""
import argparse,hashlib,json,os,subprocess,sys,time,shutil,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'build'))
from sealed_vm import SealedWorkspace,sha,inventory,encoded,copy_file
from prepare_merlin import verify
from run_readonly_linux import run
from prepare_merlin_system import prepare as prepare_system

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--mode',choices=['preflight','cycles'],default='preflight');a=ap.parse_args();os.chdir(ROOT)
 seconds=600 if a.mode=='preflight' else 3600;label=a.mode
 v=json.load(open('output/verification.json'));g=json.load(open('output/release_gates.json'));assert g['status']=='LOCAL_RELEASE_GATES_PASS' and sha(ROOT/v['image'])==g['candidate_sha256']==v['sha256']
 verify(ROOT/'build/casefs/rootfs');verify(ROOT/'build/casefs/roundtrip')
 from check import owned_sources
 assert g['config']['revision']=='r9-r2'
 prefix='r9r2_diagnostic'
 current=owned_sources();changed={p for p in set(current)|set(g['source_sha256']) if current.get(p)!=g['source_sha256'].get(p)}
 assert not changed,changed
 baseline={n:sha(ROOT/n) for n in [v['image'],'output/release_gates.json','output/local_delivery.json','output/localmod2-r9-r1-local-delivery.tar.gz','output/localmod2-r9-local-delivery.tar.gz','output/RT-AX86U_388_24437_localmod2_r9_r1_EXPERIMENTAL.w','output/localmod2-r9-r2-local-delivery.tar.gz','output/localmod2-r9-r2-local-delivery.tar.gz.sha256','output/r9r2_coexist_60m_tests.json','output/r9r2_coexist_native_probe_tests.json']}
 from prepare_real_plugins import prepare as real_prepare
 from prepare_fancyss import prepare as fancy_prepare
 real=real_prepare();fancy=fancy_prepare()
 source=['analysis/r9r1_coexist/check.py','analysis/r9r1_coexist/workload.go','build/test_merlin.go','build/test_soak.go','build/test_memory.go','build/memory_cycles.go','build/httpd_memory.go','build/native_runtime_client.go','build/test_online.go','build/coexist_helpers.go','build/check_merlin.py','build/sealed_vm.py','build/run_readonly_linux.py','build/real_plugins_setup.sh','build/linux_real_plugins_job.sh','build/make_merlin_system_initramfs.py','build/prepare_merlin_system.py','build/merlin_system_sources.json','build/prepare_fancyss.py','build/fancyss_sources.json','build/real_plugin_sources.json','build/https_trace_fixture.c']
 source+=['analysis/r9r1_coexist/tls_trace.c','sources/localmod/httpd_bridge.c','analysis/r9r2_diagnostics/check.py','analysis/r9r2_diagnostics/diagnostics.go','build/memory_exec_fixture.c']
 before={p:sha(ROOT/p) for p in source}
 dest=ROOT/'build/r9r2-diagnostic-compile';dest.mkdir(exist_ok=True)
 files=[];transforms={}
 for n in source:
  if not n.endswith('.go'):continue
  s=(ROOT/n).read_text();changes=[]
  if n.endswith(('test_merlin.go','test_soak.go')):
   assert s.count('func main() {')==1;s=s.replace('func main() {','func historical'+Path(n).stem.replace('_','')+'Main() {');changes.append('Rename historical standalone main; helpers unchanged')
  if n.endswith('test_merlin.go'):
   assert s.count('.Add(time.Hour)')==2;s=s.replace('.Add(time.Hour)','.Add(3*time.Hour)');changes.append('Owned test VPN certificate expiry3h for1h run, not router credentials')
  if n.endswith('test_online.go'):
   assert s.count('.Add(time.Hour)')==1;s=s.replace('.Add(time.Hour)','.Add(3*time.Hour)');changes.append('Owned HTTPS repository fixture certificate expiry3h; normal certificate verification remains enabled')
  if n=='analysis/r9r1_coexist/workload.go':
   assert s.count('c.handshakeProbe()')==1;s=s.replace('c.handshakeProbe()','c.diagnostics()');changes.append('Route owned diagnostic mode to paired latency and same-PID load/idle probes')
  if n=='build/native_runtime_client.go':
   old='program := "/usr/bin/qemu-arm"\n\targv := []string{"-L", nrQEMURoot(), "-E", "LD_PRELOAD=" + preload, "/usr/libexec/localmod/httpd", "-s", "-p", "34443"}'
   new='program := "/usr/libexec/localmod/httpd"\n\targv := []string{"-s", "-p", "34443"}\n\tif os.Getenv("DIAG_HTTPD_QEMU")=="1" { program="/usr/bin/qemu-arm";argv=[]string{"-L",nrQEMURoot(),"-E","LD_PRELOAD="+preload,"/usr/libexec/localmod/httpd","-s","-p","34443"} }'
   assert old in s;s=s.replace(old,new)
   assert 'cmd.Dir = "/www"' in s;s=s.replace('cmd.Dir = "/www"','if os.Getenv("DIAG_HTTPD_QEMU")!="1" {cmd.Env=append(os.Environ(),"LD_PRELOAD="+preload)}\n\tcmd.Dir = "/www"')
   changes.append('Primary full-system native ARM32 HTTPd; explicit diagnostic-only QEMU-user A/B switch, same executable and preloads')
  p=dest/Path(n).name;p.write_text(s);files.append(str(p));transforms[n]=dict(sha256=sha(p),changes=changes)
 subprocess.run(['go','build','-trimpath','-o','build/test-merlin',*files],check=True,env=dict(os.environ,GOOS='linux',GOARCH='arm64',CGO_ENABLED='0'))
 flags=['sources/zig-aarch64-macos-0.15.2/zig','cc','-target','arm-linux-gnueabi.2.26','-O2']
 subprocess.run(flags+['-mcpu=cortex_a53','-o','build/diag-thp-exec','build/memory_exec_fixture.c'],check=True)
 subprocess.run(flags+['-shared','-fPIC','-o','build/https_trace_fixture.so','analysis/r9r1_coexist/tls_trace.c','-ldl'],check=True)
 prepare_system()
 job=Path('build/linux_real_plugins_job.sh').read_text();begin=job.index('gzip -dc /lib/modules');end=job.index('mkdir /router',begin);job=job[:begin]+job[end:]
 job=job.replace('chown -Rh 0:0 /router','chown -Rh 0:0 /router\nmount --bind /router /router').replace('jffs_size=64m','jffs_size=128m')
 job=job.replace('export NATIVE_CERT_CASE=1',f'''modprobe tun
modprobe veth
modprobe crc32c_generic
modprobe iptable_nat
modprobe xt_nat
modprobe xt_MASQUERADE
modprobe xt_REDIRECT
cp /sbin/ip /router/fixture/ip
ip link add wan0 type dummy
ip addr add 203.0.113.1/24 dev wan0
ip link set wan0 up
export COEXIST_SECONDS={seconds} COEXIST_PROBE=1 DIAG_MODE={a.mode} LOCALMOD_NTP_START_TIMEOUT=60s LOCALMOD_HTTPS_TRACE=1
export NATIVE_CERT_CASE=1''')
 Path('build/merlin_nested_job.sh').write_text(job);subprocess.run(['python3','build/make_merlin_system_initramfs.py'],check=True)
 outer='''#!/bin/sh
set -eu
r=/work/build/merlin-system
"$r/lib/ld-musl-aarch64.so.1" --library-path "$r/lib:$r/usr/lib" "$r/usr/bin/qemu-system-aarch64" -no-user-config -nodefaults -machine virt,gic-version=2 -cpu cortex-a53 -accel tcg -smp 1 -m 640 -display none -monitor none -serial stdio -nic none -no-reboot -kernel /work/build/tools/linux-Image -initrd /work/build/merlin_nested_initramfs.gz -append 'console=ttyAMA0 loglevel=3 panic=1' -fsdev local,id=work,path=/work,security_model=none,readonly=on -device virtio-9p-device,fsdev=work,mount_tag=workspace </dev/null 2>&1 | tee /tmp/coexist-system.log
grep -q '^NESTED_MERLIN_JOB_STATUS=0' /tmp/coexist-system.log
'''
 current=next(p for p in fancy['packages'] if p['phase']=='current');ddns=next(p for p in real['packages'] if p['module']=='ddnsgo' and p['phase']=='current')
 extras=['build/fancyss_inputs.json','build/real_plugin_inputs.json',current['adapted_path'],ddns['path'],'build/https_trace_fixture.so','build/diag-thp-exec']
 class CoexistWorkspace(SealedWorkspace):
  def __init__(self):
   super().__init__('candidate-merlin-system',guest_job=outer.encode())
   for name in extras:
    p=ROOT/name;h=sha(p);t=self.workspace/name;t.parent.mkdir(parents=True,exist_ok=True);copy_file(p,t);assert sha(t)==h==sha(p);self.inputs[name]=h
   self.before=self.current_inventory();assert len(self.before)<20000 and sum(e.get('bytes',0) for e in self.before.values())<768*1024*1024
   self.manifest_sha256=hashlib.sha256(encoded(self.before)).hexdigest();(self.job/'manifest.json').write_bytes(encoded(self.before));self.verify()
 receipt={};log=ROOT/f'output/{prefix}_{label}.log';began=time.monotonic()
 text=run(log,timeout=seconds+1200,sealed=CoexistWorkspace(),cpus=1,receipt=receipt)
 elapsed=time.monotonic()-began
 rows=[json.loads(l.removeprefix('DIAGNOSTIC_RESULT ')) for l in text.splitlines() if l.startswith('DIAGNOSTIC_RESULT ')];assert len(rows)==1;r=rows[0]
 assert r['no_thp_control_same_pid'] and r['no_thp_control_binary_matches']
 assert r['data_preserved'] and r['runtime_script_restored'] and r['same_memory_pid'] and r['background_load_errors']==[]
 assert before=={p:sha(ROOT/p) for p in source} and baseline=={p:sha(ROOT/p) for p in baseline}
 assert r['duration_seconds']>=r['requested_memory_seconds']
 assert receipt['sealed_inputs_verified_before_and_after']
 report=dict(status='LOCAL_ATTRIBUTION_DIAGNOSTIC_COMPLETE',mode=a.mode,candidate_image=v['image'],candidate_sha256=v['sha256'],host_elapsed_seconds=elapsed,result=r,source_sha256=before,generated_test_source=transforms,vm=receipt,baseline_preserved_sha256=baseline,log_sha256=sha(log),limits=['Full-system Cortex-A53/Linux6.12,640MiB inner/1024MiB outer,no NIC or physical router','Native DDNS-Go RSS excludes QEMU-user; QEMU-system host RSS is outside guest process samples','GODEBUG traces enabled only in disposable DDNS supervisor, default GC policy unchanged; trace MiB figures are coarse, not exact retained-byte counts','Fancyss HTTP status diagnostic remains global-proxy-disabled, real Xray traffic uses owned loopback endpoints; original UU flow uses owned worker','Latency failures are observations, never hidden retries or a stability PASS; controlled pauses are labelled separately','Finite same-PID load/idle and GC observations cannot prove leak freedom or multi-day/device stability'])
 Path(f'output/{prefix}_{label}_tests.json').write_text(json.dumps(report,indent=2)+'\n');print('COMPLETE',a.mode,r['duration_seconds'],'seconds',len(r['samples']),'memory samples',len(r['latency_cases']),'latency cases',flush=True)
if __name__=='__main__':main()
