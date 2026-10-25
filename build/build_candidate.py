#!/usr/bin/env python3
"""Rebuild with the already downloaded, pinned local tools. Never flashes a router."""
import hashlib,json,shutil,subprocess
from pathlib import Path
root=Path(__file__).resolve().parent.parent

def run(*args,log=None):
    print('Running',args[0],flush=True)
    if log:
        with (root/log).open('w') as output:subprocess.run(args,cwd=root,check=True,stdout=output,stderr=subprocess.STDOUT)
    else:subprocess.run(args,cwd=root,check=True)

assert (root/'build/casefs').is_mount(),'Mount build/RTAX86UBuild.sparseimage at build/casefs first'
zig=str(root/'sources/zig-aarch64-macos-0.15.2/zig')
flags=[zig,'cc','-target','arm-linux-gnueabi.2.26','-mcpu=cortex_a53']
run(*flags,'-O2','-s','-shared','-fPIC','-o','build/httpd_bridge.so','sources/localmod/httpd_bridge.c','-ldl')
run(*flags,'-O2','-s','-o','build/httpd-launcher','sources/localmod/launcher.c')
run(*flags,'-O2','-s','-DINIT_LAUNCHER','-o','build/init-launcher','sources/localmod/launcher.c')
run(*flags,'-O0','-rdynamic','-o','build/bridge-fixture','build/bridge_fixture.c')
run(*flags,'-O0','-shared','-fPIC','-Wl,-soname,libfilemap_vendor.so','-o','build/libfilemap_vendor.so','build/filemap_vendor.c')
run(*flags,'-O0','-rdynamic','-o','build/filemap-fixture','build/filemap_fixture.c','-Lbuild','-lfilemap_vendor')
for name in ['bridge','real-backend']:
    import os
    env=dict(os.environ,GOOS='linux',GOARCH='arm64',CGO_ENABLED='0')
    subprocess.run(['go','build','-o',f'build/test-{name}',f'build/test_{name.replace("-","_")}.go'],cwd=root,env=env,check=True)
run('python3','build/stage_image.py','--refresh-generated-stage')
shutil.copyfile(root/'build/linux_build_job.sh',root/'build/linux_job.sh')
run('python3','build/run_linux.py',log='build/runtime_tests.log')
shutil.copyfile(root/'build/linux_filemap_job.sh',root/'build/linux_job.sh')
run('python3','build/run_linux.py',log='output/filemap_tests.log')
image='output/RT-AX86U_388_24437_localmod1_EXPERIMENTAL.w'
run('python3','build/repack_image.py','upstream/RT-AX86U_3.0.0.4_388_24437-g81951d7_pureubi.w','build/localmod-rootfs.ubifs',image)
run('python3','build/inspect_upstream.py',image,'output/recheck',log='output/structure.json')
run(str(root/'analysis/.venv/bin/python'),'build/export_metadata.py','output/recheck/rootfs_ubifs','output/recheck/metadata.json')
roundtrip=root/'build/casefs/roundtrip'
if roundtrip.exists():
    assert json.loads((root/'output/verification.json').read_text())['status']=='EXPERIMENTAL_NOT_DEVICE_TESTED'
    shutil.rmtree(roundtrip)
run(str(root/'analysis/.venv/bin/python'),'build/verify_candidate.py',image,'output/verification.json')
for name in ['changes.json','runtime_tests.log']:
    shutil.copyfile(root/'build'/name,root/'output'/name)
(root/'output/SHA256SUMS').write_text(hashlib.sha256((root/image).read_bytes()).hexdigest()+'  '+Path(image).name+'\n')
print('Built and verified experimental candidate. No router was accessed or flashed.')
