from pathlib import Path
import gzip,stat,struct,json
base=Path('build');raw=gzip.decompress((base/'tools/linux-initramfs.gz').read_bytes());entries={};pos=0
while True:
 assert raw[pos:pos+6]==b'070701'
 h=[int(raw[pos+6+i*8:pos+14+i*8],16) for i in range(13)];pos+=110
 name=raw[pos:pos+h[11]-1].decode();pos=(pos+h[11]+3)&~3
 data=raw[pos:pos+h[6]];pos=(pos+h[6]+3)&~3
 if name=='TRAILER!!!':break
 entries[name]=(h[1],data,h[9],h[10])
root=base/'linux-root';moddir=next((root/'lib/modules').iterdir());deps={}
for line in (moddir/'modules.dep').read_text().splitlines():
 left,right=line.split(':',1);deps[left]=right.split()
need={n for n in deps if n.endswith(('/9p.ko.gz','/9pnet_virtio.ko.gz','/virtio_mmio.ko.gz'))};todo=list(need)
while todo:
 n=todo.pop()
 for d in deps[n]:
  if d not in need:need.add(d);todo.append(d)
for n in need:
 p=moddir/n;name=str(p.relative_to(root))
 entries[name]=(stat.S_IFREG|0o644,p.read_bytes(),0,0)
 for parent in Path(name).parents:
  if str(parent)!='.':entries.setdefault(str(parent),(stat.S_IFDIR|0o755,b'',0,0))
init=r'''#!/bin/busybox.static sh
export PATH=/bin:/sbin:/usr/bin:/usr/sbin
/bin/busybox.static --install -s /bin
ln -sf /bin/busybox.static /sbin/modprobe
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
ifconfig lo 127.0.0.1 up
mkdir -p /work /tmp
modprobe virtio_mmio || { echo NESTED_MODULE_FAILURE;poweroff -f; }
modprobe 9pnet_virtio || { echo NESTED_MODULE_FAILURE;poweroff -f; }
modprobe 9p || { echo NESTED_MODULE_FAILURE;poweroff -f; }
if mount -t 9p -o trans=virtio,version=9p2000.L,ro workspace /work; then
 echo MERLIN_SYSTEM_PROBE_READY
 if (echo forbidden >/work/build/nested-write-probe) 2>/dev/null;then echo NESTED_WRITE_FAILURE;poweroff -f;fi
 if sh /work/build/merlin_nested_job.sh;then echo NESTED_MERLIN_JOB_STATUS=0;else echo NESTED_MERLIN_JOB_STATUS=1;fi
else
 echo NESTED_MOUNT_FAILURE
fi
sync
poweroff -f
'''
entries['init']=(stat.S_IFREG|0o755,init.encode(),0,0)
archive=bytearray();ino=0
for name,(mode,data,major,minor) in list(sorted(entries.items()))+[('TRAILER!!!',(0,b'',0,0))]:
 ino+=1;n=name.encode()+b'\0';v=[ino,mode,0,0,1,0,len(data),0,0,major,minor,len(n),0]
 archive.extend(b'070701'+b''.join(f'{x:08x}'.encode() for x in v)+n);archive.extend(b'\0'*(-len(archive)%4));archive.extend(data);archive.extend(b'\0'*(-len(archive)%4))
p=base/'merlin_nested_initramfs.gz';p.write_bytes(gzip.compress(archive,mtime=0));print(p,len(archive),p.stat().st_size)
