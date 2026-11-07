#!/usr/bin/env python3
"""Build source-overlay checks; never overwrite the published r7 candidate."""
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

from patch_online_installer import patch_online_installer
from prepare_real_plugins import prepare
from run_readonly_linux import run

ROOT=Path(__file__).resolve().parent.parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def fixtures():
    root=ROOT/'build/installer-boundary-inputs';root.mkdir(exist_ok=True)
    cases=[]
    def emit(name,items,accept=False,raw=None):
        p=root/(name+'.tar.gz')
        if raw is None:
            b=io.BytesIO()
            with tarfile.open(fileobj=b,mode='w',format=tarfile.USTAR_FORMAT) as t:
                for path,kind,value in items:
                    h=tarfile.TarInfo(path);h.mode=0o755;h.type=kind
                    if kind==tarfile.REGTYPE:
                        data=value.encode();h.size=len(data);t.addfile(h,io.BytesIO(data))
                    else:
                        if kind in (tarfile.SYMTYPE,tarfile.LNKTYPE):h.linkname=value
                        t.addfile(h)
            raw=b.getvalue()
        p.write_bytes(gzip.compress(raw,mtime=0))
        cases.append(dict(name=name,path=str(p.relative_to(ROOT)),accepted=accept,module='onlineprobe'))
    base=[('onlineprobe/.valid',tarfile.REGTYPE,'hnd'),('onlineprobe/install.sh',tarfile.REGTYPE,'#!/bin/sh\necho owned > /tmp/unsafe-installer-ran\n')]
    emit('regular',base,True)
    emit('safe_symlink',base+[('onlineprobe/link',tarfile.SYMTYPE,'install.sh')],True)
    emit('safe_hardlink',base+[('onlineprobe/link',tarfile.LNKTYPE,'onlineprobe/install.sh')],True)
    emit('safe_parent_relative',base+[('onlineprobe/sub',tarfile.DIRTYPE,''),('onlineprobe/sub/link',tarfile.SYMTYPE,'../install.sh')],True)
    for name,extra in [
        ('symlink_escape',[('onlineprobe/link',tarfile.SYMTYPE,'../../escape')]),
        ('absolute_symlink',[('onlineprobe/link',tarfile.SYMTYPE,'/jffs/uu-cache')]),
        ('hardlink_escape',[('onlineprobe/link',tarfile.LNKTYPE,'../escape')]),
        ('link_parent',[('onlineprobe/link',tarfile.SYMTYPE,'install.sh'),('onlineprobe/link/overwrite',tarfile.REGTYPE,'x')]),
        ('link_chain',[('onlineprobe/a',tarfile.SYMTYPE,'b'),('onlineprobe/b',tarfile.SYMTYPE,'install.sh')]),
        ('duplicate',[('onlineprobe/install.sh',tarfile.REGTYPE,'duplicate')]),
        ('dotdot',[('onlineprobe/../escape',tarfile.REGTYPE,'x')]),
        ('absolute_member',[('/tmp/escape',tarfile.REGTYPE,'x')]),
        ('newline_member',[('onlineprobe/line\nbreak',tarfile.REGTYPE,'x')]),
        ('fifo',[('onlineprobe/fifo',tarfile.FIFOTYPE,'')]),
        ('device',[('onlineprobe/device',tarfile.CHRTYPE,'')]),
        ('foreign_root',[('other/install.sh',tarfile.REGTYPE,'x')]),
    ]:emit(name,base+extra)
    h=tarfile.TarInfo('onlineprobe/large');h.size=64*1024*1024+1;emit('declared_large',[],raw=h.tobuf(tarfile.USTAR_FORMAT))
    h=tarfile.TarInfo('onlineprobe/setuid');h.mode=0o4755;emit('setuid',[],raw=h.tobuf(tarfile.USTAR_FORMAT)+bytes(1024))
    emit('truncated',[],raw=tarfile.TarInfo('onlineprobe/missing-data').tobuf(tarfile.USTAR_FORMAT)[:400])
    emit('trailing_payload',base,True)
    p=root/'trailing_payload.tar.gz';p.write_bytes(p.read_bytes()+gzip.compress(b'not a second tar'))
    cases[-1]['accepted']=False
    p=root/'corrupt_crc.tar.gz';blob=bytearray((root/'regular.tar.gz').read_bytes());blob[-8]^=1;p.write_bytes(blob)
    cases.append(dict(name='corrupt_crc',path=str(p.relative_to(ROOT)),accepted=False,module='onlineprobe'))
    # Valid header, excessive count: parser must stop before unbounded allocation.
    raw=b''.join(tarfile.TarInfo(f'onlineprobe/d{i}').tobuf(tarfile.USTAR_FORMAT) for i in range(8193))+bytes(1024)
    emit('excessive_entries',[],raw=raw)
    manifest=prepare()
    for p in manifest['packages']:
        cases.append(dict(name='pinned_'+p['module']+'_'+p['phase'],path=p['path'],accepted=True,module=p['module']))
    (root/'cases.json').write_text(json.dumps(cases,indent=2)+'\n')
    return cases

def overlay():
    folder=ROOT/'build/hardening-overlay'
    if folder.exists():shutil.rmtree(folder)
    flags=['sources/zig-aarch64-macos-0.15.2/zig','cc','-target','arm-linux-gnueabi.2.26','-mcpu=cortex_a53','-O2','-s']
    for name,src in [('archive-guard','archive_guard.c'),('plugin-run','plugin_run.c'),('log-limit','log_limit.c')]:
        subprocess.run(flags+['-o','build/'+name,'sources/localmod/'+src],check=True)
    files={
      'usr/libexec/localmod/archive-guard':ROOT/'build/archive-guard',
      'usr/libexec/localmod/plugin-run':ROOT/'build/plugin-run',
      'usr/libexec/localmod/log-limit':ROOT/'build/log-limit',
      'usr/libexec/localmod/installer-guard.sh':ROOT/'sources/localmod/installer-guard.sh',
      'usr/libexec/localmod/plugin-compat.sh':ROOT/'sources/localmod/plugin-compat.sh',
      'usr/libexec/localmod/fancyss-packages.sha256':ROOT/'sources/localmod/fancyss-packages.sha256',
      'rom/etc/koolshare/scripts/ks_tar_install.sh':ROOT/'sources/localmod/offline-installer.sh',
    }
    for dst,src in files.items():
        target=folder/dst;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,target);target.chmod(0o755)
    target=folder/'rom/etc/koolshare/scripts/ks_app_install.sh'
    donor=ROOT/'build/casefs/koolcenter_rootfs/rom/etc/koolshare/scripts/ks_app_install.sh'
    target.write_text(patch_online_installer(donor.read_text()));target.chmod(0o755)
    return {str(p.relative_to(folder)):sha(p) for p in folder.rglob('*') if p.is_file()}

def main():
    os.chdir(ROOT);assert (ROOT/'build/casefs').is_mount()
    v=json.loads((ROOT/'output/verification.json').read_text());assert sha(ROOT/v['image'])==v['sha256']
    cases=fixtures();files=overlay()
    subprocess.run(['go','build','-trimpath','-o','build/test-installer-boundaries','build/test_installer_boundaries.go','build/native_runtime_client.go','build/test_online.go','build/coexist_helpers.go'],check=True,env=dict(os.environ,GOOS='linux',GOARCH='arm64',CGO_ENABLED='0'))
    subprocess.run(['sources/zig-aarch64-macos-0.15.2/zig','cc','-target','aarch64-linux-musl','-static','-O2','-o','build/soak-init-fixture','build/soak_init_fixture.c'],check=True)
    (ROOT/'build/real-plugin-phase').write_text('hardening-installer\n')
    log=ROOT/'output/installer_boundaries_run.log';text=run(log,timeout=360)
    rows=[json.loads(l.removeprefix('INSTALLER_BOUNDARY_RESULT ')) for l in text.splitlines() if l.startswith('INSTALLER_BOUNDARY_RESULT ')];assert len(rows)==1
    result=rows[0];assert len(result['archive_cases'])==len(cases) and result['checks'] and all(result['checks'].values())
    assert files=={str(p.relative_to(ROOT/'build/hardening-overlay')):sha(p) for p in (ROOT/'build/hardening-overlay').rglob('*') if p.is_file()}
    assert sha(ROOT/v['image'])==v['sha256']
    report=dict(status='SOURCE_OVERLAY_CHECKS_PASS',base_candidate_image=v['image'],base_candidate_sha256=v['sha256'],firmware_rebuilt=False,overlay_files=files,result=result,log_sha256=sha(log),limits=['No physical router or real UU monitor/account','Source overlay in disposable RAM; not a readback claim for the published r7 firmware','Unsupported tar extensions/sparse records are rejected before extraction; safe internal links are supported'])
    (ROOT/'output/installer_boundaries_tests.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS archive cases',len(cases),'workflow checks',len(result['checks']),flush=True)

if __name__=='__main__':main()
