#!/usr/bin/env python3
"""Run the established real TUN/mutual-TLS/PAM VPN probe on the P5 image.

The nested Cortex-A53 Linux6.12 kernel executes ARM32 natively, including
network namespaces; the physical Broadcom4.1 kernel is never claimed here.
"""
import builtins,sys,types
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
import check_native_restore as shared
def run_derived(code,namespace):
 source=(ROOT/'build/native-restore-probe/derived_check.py').read_text()
 def change(old,new):
  nonlocal source
  assert source.count(old)==1,(old,source.count(old));source=source.replace(old,new)
 change("'analysis/merlin_vpn_38812/restore_probe.go']:","'build/test_merlin.go']:")
 change('sources={n:sha(ROOT/n) for n in names}',"names+="+repr(['build/test_merlin.go','build/prepare_merlin_system.py','build/make_merlin_system_initramfs.py','build/merlin_system_sources.json','analysis/merlin_vpn_38812/check_native_tunnel.py'])+"\n sources={n:sha(ROOT/n) for n in names}")
 change("text=(ROOT/n).read_text()","text=(ROOT/n).read_text()\n  if n.endswith('test_merlin.go'):text=text.replace('onlineUUStart(ctx)','previewUUStart(ctx)').replace('openvpn_27_retained_factory_pam_plugin_authenticates_valid_account_and_rejects_wrong_password','native_openvpn_27_pam_plugin_authenticates_valid_account_and_rejects_wrong_password')")
 source=source.replace('build/native-restore-probe','build/native-real-tunnel').replace('merlin38812_restore_probe','merlin38812_real_tunnel').replace('RESTORE_PROBE_RESULT','MERLIN_RESULT').replace('LOCAL_NATIVE_RESTORE_OBSERVATIONS_RECORDED','LOCAL_NATIVE_REAL_TUNNEL_PROBE_PASS')
 marker='class Workspace(SealedWorkspace):'
 change(marker,'''from prepare_merlin_system import prepare as prepare_system
 prepare_system()
 # Only the known binfmt registration is removed in the native ARM32 kernel.
 begin=job.index('gzip -dc /lib/modules');end=job.index('mkdir /router',begin);job=job[:begin]+job[end:]
 anchor='chown -Rh 0:0 /router';assert job.count(anchor)==1
 job=job.replace(anchor,anchor+'\\nmount --bind /router /router')
 anchor='export NATIVE_CERT_CASE=1';assert job.count(anchor)==1
 job=job.replace(anchor,'modprobe tun\\nmodprobe veth\\ncp /sbin/ip /router/fixture/ip\\nexport LOCALMOD_MERLIN_PROBE=vpn\\n'+anchor)
 (work/'nested_job.sh').write_text(job)
 generator=(ROOT/'build/make_merlin_system_initramfs.py').read_text()
 token="p=base/'merlin_nested_initramfs.gz'";assert generator.count(token)==1
 generator=generator.replace(token,"p=Path('build/native-real-tunnel/nested_initramfs.gz')")
 exec(compile(generator,'owned_native_nested_initramfs','exec'),{})
 job="""#!/bin/sh
set -eu
emuroot=/work/build/merlin-system
"$emuroot/lib/ld-musl-aarch64.so.1" --library-path "$emuroot/lib:$emuroot/usr/lib" \\
 "$emuroot/usr/bin/qemu-system-aarch64" -no-user-config -nodefaults \\
 -machine virt,gic-version=2 -cpu cortex-a53 -accel tcg -smp 1 -m 512 \\
 -display none -monitor none -serial stdio -nic none -no-reboot \\
 -kernel /work/build/tools/linux-Image -initrd /work/build/merlin_nested_initramfs.gz \\
 -append 'console=ttyAMA0 loglevel=3 panic=1' \\
 -fsdev local,id=work,path=/work,security_model=none,readonly=on \\
 -device virtio-9p-device,fsdev=work,mount_tag=workspace \\
 </dev/null 2>&1 | tee /tmp/owned-native-tunnel-console.log
grep -q '^NESTED_MERLIN_JOB_STATUS=0' /tmp/owned-native-tunnel-console.log
"""
 '''+marker)
 change("super().__init__('candidate-merlin-components',guest_job=job.encode())","super().__init__('candidate-merlin-system',guest_job=job.encode())")
 marker='self.before=self.current_inventory();self.manifest_sha256='
 change(marker,"for src,dst in [('nested_job.sh','merlin_nested_job.sh'),('nested_initramfs.gz','merlin_nested_initramfs.gz')]:\n    target=self.workspace/'build'/dst;target.unlink(missing_ok=True);copy_file(work/src,target);self.inputs['build/'+dst]=sha(target)\n   "+marker)
 change('timeout=360,cpus=1,receipt=receipt','timeout=1200,cpus=1,receipt=receipt')
 change('assert len(rows)==1',"assert len(rows)==1;assert rows[0]['full_suite'] is False and len(rows[0]['checks'])==2 and all(rows[0]['checks'].values());rows[0]['online']=dict(checks=[])")
 change("'Actual candidate restore adapter; declared test-only exec boundary applies output with Alpine legacy xtables; native 4.1 kernel/backend ABI, physical router, actual UU account/game acceleration remain unverified'","'Selected OpenVPN probe only: Cortex-A53 system emulation and native ARM32 Linux6.12 compatibility, actual TUN/mutual TLS/PAM, owned keys and accounts; target Broadcom4.1 kernel, physical device and actual UU acceleration remain unverified'")
 folder=ROOT/'build/native-real-tunnel';folder.mkdir(exist_ok=True);(folder/'derived_check.py').write_text(source)
 builtins.exec(compile(source,str(folder/'derived_check.py'),'exec'),namespace)
if __name__=='__main__':
 shared.builtins=types.SimpleNamespace(exec=run_derived)
 shared.controller.exec=shared.run_derived;shared.controller.main()
