#!/usr/bin/env python3
"""Persistent redacted history: native auth, actual faults and new VM boots."""
import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
from pathlib import Path
from run_readonly_linux import run

ROOT=Path(__file__).resolve().parent.parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--candidate',action='store_true');ap.add_argument('--smoke',action='store_true');a=ap.parse_args()
    os.chdir(ROOT)
    v=json.loads((ROOT/'output/verification.json').read_text());assert all(v['checks'].values()) and not v['errors'] and sha(ROOT/v['image'])==v['sha256']
    flags=['sources/zig-aarch64-macos-0.15.2/zig','cc','-target','arm-linux-gnueabi.2.26','-mcpu=cortex_a53','-O2','-s']
    overlay={}
    if not a.candidate:
        from prepare_hardening_overlay import prepare_resources
        prepare_resources();folder=ROOT/'build/hardening-overlay'
        p=folder/'usr/libexec/localmod/localmod-status';subprocess.run(flags+['-o',str(p),'sources/localmod/status.c'],check=True);p.chmod(0o755)
        subprocess.run(flags+['-shared','-fPIC','-o','build/httpd_bridge_next.so','sources/localmod/httpd_bridge.c','-ldl'],check=True)
        p=folder/'www/Module_Localmod.asp';p.parent.mkdir(parents=True,exist_ok=True)
        from release_config import CONFIG
        p.write_text((ROOT/'sources/localmod/Module_Localmod.asp').read_text().replace('@REVISION@',CONFIG['variant']+'-'+CONFIG['revision']))
        overlay={str(p.relative_to(folder)):sha(p) for p in folder.rglob('*') if p.is_file()}
    else:
        from release_config import CONFIG
        assert v['image']==CONFIG['image']
        for p in ['usr/libexec/localmod/localmod-status','usr/libexec/localmod/bootstrap.sh','usr/libexec/localmod/installer-guard.sh','usr/lib/localmod/httpd_bridge.so']:
            assert (ROOT/'build/casefs/rootfs'/p).read_bytes()==(ROOT/'build/casefs/roundtrip'/p).read_bytes(),p
        assert (ROOT/'build/httpd_bridge.so').read_bytes()==(ROOT/'build/casefs/rootfs/usr/lib/localmod/httpd_bridge.so').read_bytes()
    sources=['build/test_history.go','build/test_online.go','build/native_runtime_client.go','build/coexist_helpers.go']
    subprocess.run(['go','build','-trimpath','-o','build/test-history']+sources,check=True,env=dict(os.environ,GOOS='linux',GOARCH='arm64',CGO_ENABLED='0'))
    subprocess.run(flags+['-shared','-fPIC','-o','build/history_fault_fixture.so','build/history_fault_fixture.c','-ldl'],check=True)
    subprocess.run(['sources/zig-aarch64-macos-0.15.2/zig','cc','-target','aarch64-linux-musl','-static','-O2','-o','build/soak-init-fixture','build/soak_init_fixture.c'],check=True)
    paths=sources+['build/check_history.py','build/history_fault_fixture.c','build/run_readonly_linux.py','build/sealed_vm.py','build/linux_real_plugins_job.sh','build/real_plugins_setup.sh','build/prepare_hardening_overlay.py','build/check_installer_boundaries.py','build/patch_online_installer.py','sources/localmod/status.c','sources/localmod/health.h','sources/localmod/journal.h','sources/localmod/sha256.h','sources/localmod/bootstrap.sh','sources/localmod/installer-guard.sh','sources/localmod/offline-installer.sh','sources/localmod/httpd_bridge.c','sources/localmod/Module_Localmod.asp']
    inputs={p:sha(ROOT/p) for p in paths}
    binaries={p:sha(ROOT/p) for p in ['build/test-history','build/history_fault_fixture.so','build/httpd_bridge.so','build/httpd_bridge_next.so','build/native_hw_fixture.so','build/soak-init-fixture'] if (ROOT/p).exists()}
    private=ROOT/'build/interrupt-private';private.mkdir(exist_ok=True,mode=0o700);private.chmod(0o700)
    run_id=secrets.token_hex(6);base=private/('history-'+run_id+'-base.img')
    with base.open('xb') as f:f.truncate(96*1024*1024)
    base.chmod(0o600);disks=[base];results={};checks={};logs={};vms={}
    def boot(phase,disk,initialize=False,cut=False):
        (ROOT/'build/interrupt-phase.json').write_text(json.dumps({'initialize':initialize})+'\n')
        (ROOT/'build/history-phase').write_text(phase+'\n')
        (ROOT/'build/real-plugin-phase').write_text(('candidate-history' if a.candidate else 'hardening-history')+'\n')
        log=ROOT/('output/history_'+phase+'.log');print('History VM:',phase,'(owned ext4 state, read-only export, no NIC)',flush=True)
        receipt={};text=run(log,timeout=360,state_disk=disk,expect_cut=cut,receipt=receipt)
        assert receipt['sealed_inputs_verified_before_and_after'] and receipt['state_lock_exclusive']
        vms[phase]=receipt
        rows=[json.loads(line[len('HISTORY_RESULT '):]) for line in text.splitlines() if line.startswith('HISTORY_RESULT ')]
        assert len(rows)==1 and rows[0]['phase']==phase and rows[0]['checks'] and all(rows[0]['checks'].values()),phase
        if not cut:assert rows[0]['uu_launches']==1
        results[phase]=rows[0];logs[str(log.relative_to(ROOT))]=sha(log)
        checks.update({phase+'_'+name:ok for name,ok in rows[0]['checks'].items()})
    boot('init',base,True)
    if not a.smoke:
        boot('verify',base)
        for boundary in ['before-rename','after-rename']:
            disk=private/('history-'+run_id+'-'+boundary+'.img');assert not disk.exists();shutil.copyfile(base,disk);disk.chmod(0o600);disks.append(disk)
            boot('cut-'+boundary,disk,cut=True);boot('verify-'+boundary,disk)
    assert sha(ROOT/v['image'])==v['sha256'] and inputs=={p:sha(ROOT/p) for p in paths}
    assert binaries=={p:sha(ROOT/p) for p in binaries}
    if overlay:assert overlay=={str(p.relative_to(ROOT/'build/hardening-overlay')):sha(p) for p in (ROOT/'build/hardening-overlay').rglob('*') if p.is_file()}
    report=dict(status='LOCAL_HISTORY_SMOKE_PASS' if a.smoke else 'LOCAL_PERSISTENT_HISTORY_PASS',base_candidate_image=v['image'],base_candidate_sha256=v['sha256'],source_overlay_used=not a.candidate,source_sha256=inputs,binary_sha256=binaries,overlay_files=overlay,checks=checks,phases=results,logs=logs,sealed_vms=vms,physical_router_accessed=False,
                scope=['Original ASUS login/TLS, center database/installer and UU download/checksum path with owned worker','Root-private bounded checksummed journal; no raw configuration/account/log payload','Three owned 96 MiB ext4 state images; actual partial writes, failed rename, disk pressure, corruption and forced VM cuts'],
                limits=['Alpine 6.12/QEMU; no physical router, original 4.1 kernel or NAND/UBIFS durability claim','Real UU account/traffic and arbitrary hostile root writers not tested','Damaged/incomplete history is retained read-only and recording becomes best effort; it never owns plugin or UU recovery','Read-only inference of an interrupted operation is not a claim that a plugin was rolled back'])
    if a.candidate:report.update(candidate_image=v['image'],candidate_sha256=v['sha256'])
    out=ROOT/('build/history_smoke.json' if a.smoke else 'output/history_tests.json');out.write_text(json.dumps(report,indent=2)+'\n')
    for disk in disks:
        assert disk.parent==private and disk.name.startswith('history-'+run_id+'-') and not disk.is_symlink();disk.unlink()
    print('PASS',len(checks),'history checks across',len(results),'boots; disposable disks removed',flush=True)


if __name__=='__main__':main()
