#!/usr/bin/env python3
"""Build and verify the experimental image with the prepared pinned local tools."""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
root=Path(__file__).resolve().parent.parent
ap=argparse.ArgumentParser();ap.add_argument('--compile-only',action='store_true');args=ap.parse_args()
def run(*command,log=None):
    print('Running',command[0],flush=True)
    if log:
        with (root/log).open('w') as output:subprocess.run(command,cwd=root,check=True,stdout=output,stderr=subprocess.STDOUT)
    else:subprocess.run(command,cwd=root,check=True)
assert (root/'build/casefs').is_mount(),'Mount the case-sensitive build volume first'
zig=str(root/'sources/zig-aarch64-macos-0.15.2/zig')
flags=[zig,'cc','-target','arm-linux-gnueabi.2.26','-mcpu=cortex_a53']
common=['sources/localmod/runtime.c']
run(*flags,'-O2','-s','-shared','-fPIC','-o','build/httpd_bridge.so','sources/localmod/httpd_bridge.c','-ldl')
for define,name in [('', 'httpd'),('INIT_LAUNCHER','init'),('RC_LAUNCHER','rc')]:
    run(*flags,'-O2','-s',*(['-D'+define] if define else []),'-o',f'build/{name}-launcher','sources/localmod/launcher.c')
run(*flags,'-O2','-s','-shared','-fPIC','-o','build/rc_bridge.so','sources/localmod/rc_bridge.c',*common,'-ldl','-lpthread')
run(*flags,'-O2','-s','-o','build/localmod-event','sources/localmod/event.c',*common)
run(*flags,'-O2','-s','-o','build/iptables-restore-launcher','sources/localmod/restore.c',*common)
run(*flags,'-O0','-rdynamic','-o','build/bridge-fixture','build/bridge_fixture.c')
run(*flags,'-O0','-shared','-fPIC','-Wl,-soname,libfilemap_vendor.so','-o','build/libfilemap_vendor.so','build/filemap_vendor.c')
run(*flags,'-O0','-rdynamic','-o','build/filemap-fixture','build/filemap_fixture.c','-Lbuild','-lfilemap_vendor')
run(*flags,'-O2','-shared','-fPIC','-DLOCALMOD_RC_FIXTURE','-o','build/rc_bridge_fixture.so','sources/localmod/rc_bridge.c',*common,'-ldl','-lpthread')
run(*flags,'-O0','-shared','-fPIC','-Wl,-soname,librc_vendor_fixture.so','-o','build/librc_vendor_fixture.so','build/rc_vendor_fixture.c')
run(*flags,'-O0','-o','build/rc-fixture','build/rc_fixture.c','-Lbuild','-lrc_vendor_fixture')
run(*flags,'-O2','-Isources/localmod','-o','build/runtime-fixture','build/runtime_fixture.c',*common)
run(*flags,'-O2','-DVENDOR_RESTORE="/usr/sbin/iptables-legacy-restore"','-o','build/restore-fixture','sources/localmod/restore.c',*common)
run(str(root/'analysis/.venv/bin/python'),'build/prepare_native_fixtures.py')
run(*flags,'-O2','-shared','-fPIC','-o','build/native_hw_fixture.so','build/native_hw_fixture.c')
run(*flags,'-O2','-shared','-fPIC','-o','build/native_uu_transport.so','build/native_uu_transport.c','-ldl')
for name in ['bridge','real-backend','restore','center','launcher-vendor','native-httpd','native-uu']:
    env=dict(os.environ,GOOS='linux',GOARCH='arm64',CGO_ENABLED='0')
    subprocess.run(['go','build','-o',f'build/test-{name}',f'build/test_{name.replace("-","_")}.go'],cwd=root,env=env,check=True)
if args.compile_only:raise SystemExit(0)
run('python3','build/stage_image.py','--refresh-generated-stage')
run(str(root/'analysis/.venv/bin/python'),'build/audit_vendor_contracts.py')
for name,destination in [('build','build/runtime_tests.log'),('filemap','output/filemap_tests.log'),('hooks','build/hooks_test_run.log'),('restore','build/restore_tests_run.log'),('center','build/center_tests_run.log'),('native_httpd','build/native_httpd_tests_run.log'),('native_uu','build/native_uu_tests_run.log')]:
    shutil.copyfile(root/f'build/linux_{name}_job.sh',root/'build/linux_job.sh')
    run('python3','build/run_linux.py',log=destination)
run('python3','build/verify_hooks.py')
run('python3','build/verify_compatibility.py')
run('python3','build/verify_native_runtime.py')
run('python3','build/verify_uu_compatibility.py')
image='output/RT-AX86U_388_24437_localmod2_r4_EXPERIMENTAL.w'
run('python3','build/repack_image.py','upstream/RT-AX86U_3.0.0.4_388_24437-g81951d7_pureubi.w','build/localmod-rootfs.ubifs',image)
run('python3','build/inspect_upstream.py',image,'output/recheck',log='output/structure.json')
run(str(root/'analysis/.venv/bin/python'),'build/export_metadata.py','output/recheck/rootfs_ubifs','output/recheck/metadata.json')
roundtrip=root/'build/casefs/roundtrip'
if roundtrip.exists():
    assert json.loads((root/'output/verification.json').read_text())['status']=='EXPERIMENTAL_NOT_DEVICE_TESTED'
    shutil.rmtree(roundtrip)
run(str(root/'analysis/.venv/bin/python'),'build/verify_candidate.py',image,'output/verification.json')
for name in ['changes.json','runtime_tests.log','hooks_trace.log','hooks_test_run.log','restore_tests_run.log','restore_hook_trace.log','center_tests_run.log','native_httpd_tests_run.log','native_uu_tests_run.log']:
    shutil.copyfile(root/'build'/name,root/'output'/name)
(root/'output/SHA256SUMS').write_text(hashlib.sha256((root/image).read_bytes()).hexdigest()+'  '+Path(image).name+'\n')
run('python3','build/check_lifecycle.py','--skip-native-regression')
run('python3','build/check_online.py')
run('python3','build/check_real_plugins.py')
print('Built localmod2-r4 and verified the experimental candidate; no router was accessed or flashed.')
