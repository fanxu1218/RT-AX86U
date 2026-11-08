#!/usr/bin/env python3
"""Pinned candidate coexistence soak; original prior delivery images stay fixed."""
import argparse,hashlib,json,os,subprocess,sys,time,shutil,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'build'))
from sealed_vm import SealedWorkspace,sha,inventory,encoded,copy_file
from prepare_merlin import verify
from run_readonly_linux import run
from prepare_merlin_system import prepare as prepare_system

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--smoke',action='store_true');ap.add_argument('--probe',action='store_true');ap.add_argument('--bridge-overlay',action='store_true');a=ap.parse_args();os.chdir(ROOT)
 assert not a.bridge_overlay or a.probe
 seconds=600 if a.smoke or a.probe else 3600;label='probe' if a.probe else ('smoke' if a.smoke else '60m')
 v=json.load(open('output/verification.json'));g=json.load(open('output/release_gates.json'));assert g['status']=='LOCAL_RELEASE_GATES_PASS' and sha(ROOT/v['image'])==g['candidate_sha256']==v['sha256']
 verify(ROOT/'build/casefs/rootfs');verify(ROOT/'build/casefs/roundtrip')
 from check import owned_sources
 prefix=g['config']['revision'].replace('-','')+'_coexist'
 current=owned_sources();changed={p for p in set(current)|set(g['source_sha256']) if current.get(p)!=g['source_sha256'].get(p)}
 assert changed==({'sources/localmod/httpd_bridge.c'} if a.bridge_overlay else set()),changed
 baseline={n:sha(ROOT/n) for n in [v['image'],'output/release_gates.json','output/local_delivery.json','output/localmod2-r9-r1-local-delivery.tar.gz','output/localmod2-r9-local-delivery.tar.gz','output/RT-AX86U_388_24437_localmod2_r9_r1_EXPERIMENTAL.w']}
 from prepare_real_plugins import prepare as real_prepare
 from prepare_fancyss import prepare as fancy_prepare
 real=real_prepare();fancy=fancy_prepare()
 source=['analysis/r9r1_coexist/check.py','analysis/r9r1_coexist/workload.go','build/test_merlin.go','build/test_soak.go','build/test_memory.go','build/memory_cycles.go','build/httpd_memory.go','build/native_runtime_client.go','build/test_online.go','build/coexist_helpers.go','build/check_merlin.py','build/sealed_vm.py','build/run_readonly_linux.py','build/real_plugins_setup.sh','build/linux_real_plugins_job.sh','build/make_merlin_system_initramfs.py','build/prepare_merlin_system.py','build/merlin_system_sources.json','build/prepare_fancyss.py','build/fancyss_sources.json','build/real_plugin_sources.json','build/https_trace_fixture.c']
 source+=['analysis/r9r1_coexist/tls_trace.c','sources/localmod/httpd_bridge.c']
 before={p:sha(ROOT/p) for p in source}
 dest=ROOT/'build/coexist-compile';dest.mkdir(exist_ok=True)
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
  p=dest/Path(n).name;p.write_text(s);files.append(str(p));transforms[n]=dict(sha256=sha(p),changes=changes)
 subprocess.run(['go','build','-trimpath','-o','build/test-merlin',*files],check=True,env=dict(os.environ,GOOS='linux',GOARCH='arm64',CGO_ENABLED='0'))
 flags=['sources/zig-aarch64-macos-0.15.2/zig','cc','-target','arm-linux-gnueabi.2.26','-O2']
 subprocess.run(flags+['-shared','-fPIC','-o','build/https_trace_fixture.so','analysis/r9r1_coexist/tls_trace.c','-ldl'],check=True)
 if a.bridge_overlay:subprocess.run(flags+['-mcpu=cortex_a53','-shared','-fPIC','-o','build/httpd_bridge_next.so','sources/localmod/httpd_bridge.c','-ldl'],check=True)
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
export COEXIST_SECONDS={seconds} COEXIST_PROBE={1 if a.probe else 0} LOCALMOD_HTTPD_BRIDGE_OVERLAY={1 if a.bridge_overlay else 0} LOCALMOD_NTP_START_TIMEOUT=60s LOCALMOD_HTTPS_TRACE=1
export NATIVE_CERT_CASE=1''')
 Path('build/merlin_nested_job.sh').write_text(job);subprocess.run(['python3','build/make_merlin_system_initramfs.py'],check=True)
 outer='''#!/bin/sh
set -eu
r=/work/build/merlin-system
"$r/lib/ld-musl-aarch64.so.1" --library-path "$r/lib:$r/usr/lib" "$r/usr/bin/qemu-system-aarch64" -no-user-config -nodefaults -machine virt,gic-version=2 -cpu cortex-a53 -accel tcg -smp 1 -m 640 -display none -monitor none -serial stdio -nic none -no-reboot -kernel /work/build/tools/linux-Image -initrd /work/build/merlin_nested_initramfs.gz -append 'console=ttyAMA0 loglevel=3 panic=1' -fsdev local,id=work,path=/work,security_model=none,readonly=on -device virtio-9p-device,fsdev=work,mount_tag=workspace </dev/null 2>&1 | tee /tmp/coexist-system.log
grep -q '^NESTED_MERLIN_JOB_STATUS=0' /tmp/coexist-system.log
'''
 current=next(p for p in fancy['packages'] if p['phase']=='current');ddns=next(p for p in real['packages'] if p['module']=='ddnsgo' and p['phase']=='current')
 extras=['build/fancyss_inputs.json','build/real_plugin_inputs.json',current['adapted_path'],ddns['path'],'build/https_trace_fixture.so']
 if a.bridge_overlay:extras.append('build/httpd_bridge_next.so')
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
 if a.probe:
  rows=[json.loads(l.removeprefix('COEXIST_PROBE_RESULT ')) for l in text.splitlines() if l.startswith('COEXIST_PROBE_RESULT ')];assert len(rows)==1
  assert before=={p:sha(ROOT/p) for p in source} and baseline=={p:sha(ROOT/p) for p in baseline}
  r=rows[0];cases=r['handshake_cases'];assert len(cases)==14 and all(row['valid'] and row['code']==200 for row in cases[:12]) and all(not row['valid'] for row in cases[12:]),cases
  Path(f'output/{prefix}_probe_tests.json').write_text(json.dumps(dict(status='SOURCE_OVERLAY_HANDSHAKE_RECOVERY_PASS' if a.bridge_overlay else 'FINAL_CANDIDATE_HANDSHAKE_RECOVERY_PASS',candidate_sha256=v['sha256'],source_overlay_used=a.bridge_overlay,result=r,source_sha256=before,generated_test_source=transforms,baseline_preserved_sha256=baseline,log_sha256=sha(log),vm=receipt),indent=2)+'\n');return
 rows=[json.loads(l[len('COEXIST_RESULT '):]) for l in text.splitlines() if l.startswith('COEXIST_RESULT ')];assert len(rows)==1;r=rows[0]
 assert r['duration_seconds']>=seconds and elapsed>=seconds and r['unplanned_failures']==0 and r['data_preserved']
 assert r['events']>=16*(1 if a.smoke else 2) and all(r['counts'].get(k,0)>=(1 if a.smoke else 2) for k in r['event_kinds'])
 assert r['queries']>=(35 if a.smoke else 360) and len(r['samples'])>=(5 if a.smoke else 100)
 assert before=={p:sha(ROOT/p) for p in source} and baseline=={p:sha(ROOT/p) for p in baseline}
 windows=[dict(name=n,queries=int(q),unavailable=int(b)) for n,q,b in re.findall(r'([a-z_-]+)_reads=(\d+) unavailable=(\d+)',text)]
 assert windows and all(w['queries']>0 and (w['unavailable']==0 or w['name'] in ['center_restart','ddns_restart']) for w in windows)
 grouped={}
 for sample in r['samples']:
  for name,row in sample.items():
   if isinstance(row,dict) and 'pid' in row:grouped.setdefault((name,row['pid']),[]).append(row)
 resources=[dict(name=n,pid=p,samples=len(rows),executable=rows[0]['executable'],rss_min_kib=min(r['rss_kib'] for r in rows),rss_max_kib=max(r['rss_kib'] for r in rows),fd_min=min(r['fds'] for r in rows),fd_max=max(r['fds'] for r in rows)) for (n,p),rows in sorted(grouped.items())]
 report=dict(maintenance_windows=windows,resource_ranges=resources,status='LOCAL_COEXIST_SMOKE_PASS' if a.smoke else 'LOCAL_60_MINUTE_COEXIST_PASS',candidate_image=v['image'],candidate_sha256=v['sha256'],requested_seconds=seconds,host_elapsed_seconds=elapsed,result=r,source_sha256=before,generated_test_source=transforms,vm=receipt,baseline_preserved_sha256=baseline,log_sha256=sha(log),limits=['Networkless full Cortex-A53 Linux6.12 system emulation,640MiB inner/1024MiB outer; no target4.1 kernel or physical router','Actual pinned Fancyss installed via production installer; real Xray SOCKS/VLESS traffic uses owned loopback endpoints, transparent/global proxy mode remains disabled','UU uses original NTP/download/checksum flow and owned worker; no real UU monitor/account/game acceleration','Program restarts and upstream failures are owned/manual maintenance; only existing perp/OpenVPN recovery is automatic','RSS includes guest program/runtime and QEMU-user overhead where observed executable is qemu-arm; QEMU-system host RAM is outside guest samples','One-hour bounded observation cannot establish day/week stability or leak freedom'])
 Path(f'output/{prefix}_{label}_tests.json').write_text(json.dumps(report,indent=2)+'\n');print('PASS',report['status'],seconds,'seconds',r['queries'],'queries',r['events'],'events',flush=True)
if __name__=='__main__':main()
