#!/usr/bin/env python3
"""Run actual six-component services with no host writes or guest WAN NIC."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from prepare_merlin import ROOT, PIN, verify, sha
from sealed_vm import SealedWorkspace
from run_readonly_linux import run


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stage-only', action='store_true')
    ap.add_argument('--service',choices=['ssh','upnp','upnp-factory','upnp-raw','vpn','factory-config','dns','dhcp'])
    ap.add_argument('--system',action='store_true',help='Full Cortex-A53 system emulation, including native ARM32 kernel compatibility')
    a = ap.parse_args()
    assert not a.service or a.stage_only, 'Selected service probes cannot satisfy the candidate gate'
    os.chdir(ROOT)
    stage = ROOT / 'build/casefs/rootfs'
    verify(stage)
    v = json.loads((ROOT/'output/verification.json').read_text())
    if not a.stage_only:
        from release_config import CONFIG
        assert v['image'] == CONFIG['image'] and sha(ROOT/v['image']) == v['sha256']
        verify(ROOT/'build/casefs/roundtrip')
        assert (stage/'rom/etc/localmod-merlin.json').read_bytes() == (ROOT/'build/casefs/roundtrip/rom/etc/localmod-merlin.json').read_bytes()
    sources = ['build/check_merlin.py','build/audit_merlin.py','build/prepare_merlin.py','build/merlin_sources.json',
               'build/test_merlin.go','build/merlin_vpn_config_probe.c','build/merlin_vpn_config_fixture.c',
               'sources/localmod/merlin_launcher.c','build/sealed_vm.py','build/real_plugins_setup.sh',
               'build/linux_real_plugins_job.sh','build/native_runtime_client.go','build/test_online.go',
               'build/coexist_helpers.go','build/make_initramfs.py',
               'sources/localmod/miniupnp_compat.c','sources/localmod/openvpn_compat.c','sources/localmod/restore.c',
               'build/prepare_merlin_system.py','build/merlin_system_sources.json',
               'build/make_merlin_system_initramfs.py']
    assert (stage/'usr/libexec/localmod/miniupnp-compat').read_bytes()==(ROOT/'build/miniupnp-compat').read_bytes()
    before = {p:sha(ROOT/p) for p in sources}
    cc = [str(ROOT/'sources/zig-aarch64-macos-0.15.2/zig'),'cc','-target','arm-linux-gnueabi.2.26','-O2']
    subprocess.run(cc+['-o','build/merlin-vpn-config-probe','build/merlin_vpn_config_probe.c','-ldl'],check=True)
    subprocess.run(cc+['-shared','-fPIC','-o','build/merlin-vpn-config-fixture.so','build/merlin_vpn_config_fixture.c'],check=True)
    subprocess.run(['go','build','-trimpath','-o','build/test-merlin','build/test_merlin.go',
                    'build/test_online.go','build/native_runtime_client.go','build/coexist_helpers.go'],
                   check=True,env=dict(os.environ,GOOS='linux',GOARCH='arm64',CGO_ENABLED='0'))
    audit = json.loads(subprocess.check_output([str(ROOT/'analysis/.venv/bin/python'),'build/audit_merlin.py'],text=True))
    job = (ROOT/'build/linux_real_plugins_job.sh').read_text()
    # Dropbear re-execs an open CLOEXEC binary descriptor. O lets QEMU receive
    # the kernel's executable fd, instead of reopening an already closed
    # /proc/self/fd path. P retains the Dropbear multicall argv[0]. These
    # flags affect this emulation fixture only, not the target kernel.
    assert job.count('/usr/bin/qemu-arm:F\'') == 1
    job = job.replace('/usr/bin/qemu-arm:F\'', '/usr/bin/qemu-arm:POF\'')
    job = job.replace("flags: F", "flags: POF")
    assert job.count('chown -Rh 0:0 /router') == 1
    # ip netns exec needs a mount at the chroot root for its private mount
    # namespace. Do this before installing the /proc,/dev,/work submounts.
    job = job.replace('chown -Rh 0:0 /router','chown -Rh 0:0 /router\nmount --bind /router /router')
    anchor = 'export NATIVE_CERT_CASE=1'
    assert job.count(anchor) == 1
    job = job.replace(anchor,'''modprobe tun
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
''' + anchor)
    if a.service:
        job=job.replace(anchor,'export LOCALMOD_MERLIN_PROBE='+a.service+'\n'+anchor)
    use_system=a.system or not a.service
    if use_system:
        from prepare_merlin_system import prepare as prepare_system
        prepare_system()
        begin=job.index('gzip -dc /lib/modules')
        end=job.index('mkdir /router',begin)
        job=job[:begin]+job[end:]
        job=job.replace(anchor,'export LOCALMOD_NTP_START_TIMEOUT=60s\n'+anchor)
        (ROOT/'build/merlin_nested_job.sh').write_text(job)
        subprocess.run(['python3','build/make_merlin_system_initramfs.py'],check=True)
        job='''#!/bin/sh
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
 </dev/null 2>&1 | tee /tmp/merlin-system-console.log
grep -q '^NESTED_MERLIN_JOB_STATUS=0' /tmp/merlin-system-console.log
'''
    receipt = {}
    log = ROOT / ('build/merlin_'+a.service+'_probe.log' if a.service else 'build/merlin_staged_tests.log' if a.stage_only else 'output/merlin_component_tests.log')
    text = run(log,timeout=1200 if use_system else 360,cpus=1,sealed=SealedWorkspace('candidate-merlin-system' if use_system else 'candidate-merlin-components',guest_job=job.encode()),receipt=receipt)
    results = [json.loads(s[len('MERLIN_RESULT '):]) for s in text.splitlines() if s.startswith('MERLIN_RESULT ')]
    assert len(results) == 1 and results[0]['checks'] and all(results[0]['checks'].values())
    assert results[0]['full_suite'] == (not a.service)
    if not a.service: assert len(results[0]['checks']) >= 12
    assert before == {p:sha(ROOT/p) for p in sources}
    report = dict(status='BASELINE_REPRODUCED' if a.service=='upnp-raw' else 'LOCAL_STAGED_MERLIN_SERVICE_PROBE_PASS' if a.service else 'LOCAL_STAGED_MERLIN_COMPONENTS_PASS' if a.stage_only else 'LOCAL_MERLIN_COMPONENTS_PASS',
                  candidate_image=v['image'],candidate_sha256=v['sha256'],staged_overlay=a.stage_only,
                  selected_service_probe=a.service,
                  full_system_emulation=use_system,
                  checks=results[0]['checks'],result=results[0],elf_audit=audit,source_sha256=before,
                  source=PIN,vm=receipt,log_sha256=sha(log),
                  limits=['Networkless full Cortex-A53 Linux6.12 system emulation with native kernel ARM32 compatibility' if use_system else 'Networkless ARM64 Linux6.12 with QEMU user emulation for ARM32 applications',
                          'No physical router, target kernel4.1, NAND flash, wireless drivers or real WAN packet forwarding',
                          'Factory libvpn configuration text is real; synthetic NVRAM/PID1 and captured launches are fixtures',
                          'Local TLS/SSH/VPN/DNS/UPnP services use owned keys, dummy interfaces and data; no WAN accounts or UU acceleration'])
    target = ROOT / ('build/merlin_'+a.service+'_probe.json' if a.service else 'build/merlin_staged_tests.json' if a.stage_only else 'output/merlin_component_tests.json')
    target.write_text(json.dumps(report,indent=2)+'\n')
    print(('REPRODUCED isolated ' if a.service=='upnp-raw' else 'PASS isolated ')+(a.service+' service probe' if a.service else 'six-component service suite'),len(results[0]['checks']),flush=True)


if __name__ == '__main__':
    main()
