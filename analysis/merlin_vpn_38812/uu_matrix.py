#!/usr/bin/env python3
"""Observe native UU startup in retained factory and complete Merlin userspaces."""
import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'build'))
from sealed_vm import SealedWorkspace,inventory,encoded,copy_file,sha
from run_readonly_linux import run
JOB=r'''#!/bin/sh
set -eux
ulimit -c 0
[ "$(ls /sys/class/net)" = lo ]
if (echo forbidden >/work/build/uu-matrix/write-probe) 2>/dev/null;then exit 98;fi
gzip -dc /lib/modules/*/kernel/fs/binfmt_misc.ko.gz >/tmp/binfmt.ko
insmod /tmp/binfmt.ko
mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc
printf '%s\n' ':arm:M::\x7fELF\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x28\x00:\xff\xff\xff\xff\xff\xff\xff\x00\xff\xff\xff\xff\xff\xff\xff\xff\xfe\xff\xff\xff:/usr/bin/qemu-arm:F' > /proc/sys/fs/binfmt_misc/register || [ -r /proc/sys/fs/binfmt_misc/arm ]
grep -qx 'flags: F' /proc/sys/fs/binfmt_misc/arm
grep -qx 'interpreter /usr/bin/qemu-arm' /proc/sys/fs/binfmt_misc/arm
mkdir /router
cp -a @TREE@/. /router/
chown -Rh 0:0 /router
mkdir -p /router/work /router/fixture/lib /router/tmp/var/run /router/var/run /router/tmp/native-nvram /router/tmp/uu-matrix /router/jffs
cp /usr/bin/qemu-arm /router/usr/bin/qemu-arm
cp /lib/ld-musl-aarch64.so.1 /router/lib/
cp -a /lib/*.so* /usr/lib/*.so* /router/fixture/lib/
mount --bind /work /router/work
mount --bind /dev /router/dev
mount -t proc proc /router/proc
mount -t tmpfs -o size=32m tmpfs /router/jffs
printf '127.0.0.1 localhost\n' >/router/etc/hosts
mv /router/usr/sbin/wget /router/fixture/native-wget
cat >/router/usr/sbin/wget <<'SCRIPT'
#!/bin/sh
count=$#
while [ "$count" -gt 0 ];do
 arg=$1;shift
 case "$arg" in
 'https://router.uu.163.com/api/script/monitor?type=asuswrt') arg=http://127.0.0.1:35000/api;;
 http://127.0.0.1:35000/monitor) ;;
 http://*|https://*) exit 97;;
 esac
 set -- "$@" "$arg"
 count=$((count-1))
done
exec /fixture/native-wget "$@"
SCRIPT
chmod 755 /router/usr/sbin/wget
export NATIVE_STATE_DIRECTORY=/tmp/native-nvram MATRIX_BASE=@LABEL@ MATRIX_RC_PATH=@RC@ MATRIX_EVENT=@EVENT@
/work/build/soak-init-fixture /bin/chroot /router /work/build/uu-matrix/probe
'''
def main():
 os.chdir(ROOT);work=ROOT/'build/uu-matrix';work.mkdir(exist_ok=True)
 gate=json.loads((ROOT/'output/release_gates.json').read_text());pin=json.loads((ROOT/'build/merlin_sources.json').read_text())
 assert sha(ROOT/pin['archive']['image'])==pin['archive']['image_sha256']
 baseline={n:sha(ROOT/n) for n in [gate['config']['image'],'output/release_gates.json','output/local_delivery.json','output/merlin38812_vpn_phase1_tests.json']}
 subprocess.run(['go','build','-trimpath','-o',str(work/'probe'),str(HERE/'uu_matrix.go')],check=True,env=dict(os.environ,GOOS='linux',GOARCH='arm64',CGO_ENABLED='0'))
 fixture=work/'clear_preload.c';fixture.write_text('#include <stdlib.h>\n__attribute__((constructor)) static void clear(void){unsetenv("LD_PRELOAD");}\n')
 subprocess.run([str(ROOT/'sources/zig-aarch64-macos-0.15.2/zig'),'cc','-target','arm-linux-gnueabi.2.26','-O2','-shared','-fPIC','-o',str(work/'clear_preload.so'),str(fixture)],check=True)
 # Compile fixture inputs in this job's private directory. Do not claim a
 # current source hash describes a stale shared build/*.so from another run.
 for n,extra in [('native_hw_fixture',['-DLOCALMOD_DEVICE_MODEL="RT-AX86U"']),('native_uu_transport',['-ldl'])]:
  subprocess.run([str(ROOT/'sources/zig-aarch64-macos-0.15.2/zig'),'cc','-target','arm-linux-gnueabi.2.26','-mcpu=cortex_a53','-O2','-shared','-fPIC','-o',str(work/(n+'.so')),str(ROOT/'build'/(n+'.c')),*extra],check=True)
 sources={str(p.relative_to(ROOT)):sha(p) for p in [HERE/'uu_matrix.py',HERE/'uu_matrix.go',HERE/'vendor/merlin_ntpd.c',ROOT/'build/native_hw_fixture.c',ROOT/'build/native_uu_transport.c',ROOT/'build/sealed_vm.py',ROOT/'build/run_readonly_linux.py',ROOT/'upstream/merlin/metadata.json']}
 fixture_binaries={str(p.relative_to(ROOT)):sha(p) for p in [work/'probe',work/'native_hw_fixture.so',work/'native_uu_transport.so',work/'clear_preload.so']}
 observations=[]
 for label,tree,rc in [('factory','build/casefs/rootfs','/usr/libexec/localmod/rc.vendor'),('merlin','build/uu-matrix-merlin-root','/sbin/rc')]:
  class Workspace(SealedWorkspace):
   def __init__(self):
    job=JOB.replace('@TREE@','/work/'+tree).replace('@LABEL@',label).replace('@RC@',rc).replace('@EVENT@','ntpd_step' if label=='merlin' else 'legacy_signal')
    super().__init__('candidate-merlin-components',guest_job=job.encode())
    for p in work.iterdir():
     if not p.is_file():continue
     n=p.relative_to(ROOT);dest=self.workspace/n;dest.parent.mkdir(parents=True,exist_ok=True);copy_file(p,dest);self.inputs[str(n)]=sha(p)
    if label=='merlin':
     src=ROOT/'build/casefs/merlin38812_rootfs';dest=self.workspace/tree
     before=inventory(src);shutil.copytree(src,dest,symlinks=True,copy_function=copy_file)
     assert before==inventory(src)==inventory(dest)
     # The original UBIFS inode modes are authoritative. The cached extraction
     # kept file bytes but not execute bits; normalize only this owned copy.
     metadata=json.loads((ROOT/'upstream/merlin/metadata.json').read_text())
     for n,row in metadata.items():
      p=dest/n.lstrip('/')
      if p.exists() and not p.is_symlink():p.chmod(row['mode']&0o7777)
     normalized=inventory(dest)
     assert {n:{k:v for k,v in r.items() if k!='mode'} for n,r in normalized.items()}=={n:{k:v for k,v in r.items() if k!='mode'} for n,r in before.items()}
     self.inputs[tree]=hashlib.sha256(encoded(normalized)).hexdigest()
    self.before=self.current_inventory();self.manifest_sha256=hashlib.sha256(encoded(self.before)).hexdigest();(self.job/'manifest.json').write_bytes(encoded(self.before));self.verify()
  receipt={};log=ROOT/f'output/merlin38812_uu_matrix_{label}.log'
  console=run(log,sealed=Workspace(),timeout=200,cpus=1,receipt=receipt)
  rows=[json.loads(l.removeprefix('UU_MATRIX_RESULT ')) for l in console.splitlines() if l.startswith('UU_MATRIX_RESULT ')];assert len(rows)==1
  observations.append(dict(result=rows[0],vm=receipt,log_sha256=sha(log)))
 assert baseline=={n:sha(ROOT/n) for n in baseline}
 assert sources=={n:sha(ROOT/n) for n in sources}
 passed=all(len(o['result']['cases'])==6 and all(c['matches_factory_contract'] for c in o['result']['cases']) for o in observations)
 report=dict(status='LOCAL_NATIVE_UU_STARTUP_MATRIX_PASS' if passed else 'NATIVE_UU_USERSPACE_COMPARISON_OBSERVED',upstream_image_sha256=pin['archive']['image_sha256'],factory_candidate_sha256=gate['candidate_sha256'],observations=observations,source_sha256=sources,fixture_binaries=fixture_binaries,baseline_preserved_sha256=baseline,limits=['Synthetic board/NVRAM includes uu_accel flag in both baselines; does not prove real boot advertises UU','Native NTP, download/checksum/launch logic with owned monitor only; no real UU account or acceleration','Userspace under QEMU-user/Linux6.12; no target kernel, WAN or router flash','No production baseline or release configuration changed'])
 (ROOT/'output/merlin38812_uu_matrix_tests.json').write_text(json.dumps(report,indent=2)+'\n')
 print(report['status'],[(o['result']['base'],sum(c['matches_factory_contract'] for c in o['result']['cases'])) for o in observations])
if __name__=='__main__':main()
