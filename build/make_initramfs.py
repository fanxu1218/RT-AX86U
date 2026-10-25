#!/usr/bin/env python3
import gzip
import os
import stat
import struct
from pathlib import Path

base = Path(__file__).resolve().parent
root = base/'linux-root'
kernel = (root/'boot/vmlinuz-virt').read_bytes()
if kernel[4:8] == b'zimg':
    off, length = struct.unpack_from('<II', kernel, 8)
    kernel = gzip.decompress(kernel[off:off+length])
assert kernel[56:60] == b'ARMd', 'Not an ARM64 Linux Image'
(base/'tools/linux-Image').write_bytes(kernel)

init = b'''#!/bin/busybox.static sh
export PATH=/bin:/sbin:/usr/bin:/usr/sbin
/bin/busybox.static --install -s /bin
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
ifconfig lo 127.0.0.1 up
mkdir -p /tmp /work
for module in /lib/modules/*/kernel/fs/fuse/fuse.ko.gz /lib/modules/*/kernel/fs/fuse/virtiofs.ko.gz; do
  gzip -dc "$module" > /tmp/module.ko
  insmod /tmp/module.ko || { echo "module load failed"; poweroff -f; }
done
if mount -t virtiofs workspace /work; then
  echo "LINUX_BUILDER_READY"
  if sh /work/build/linux_job.sh; then echo 0 > /work/build/linux-job.status; else echo 1 > /work/build/linux-job.status; fi
  sync
else
  echo "workspace mount failed"
fi
poweroff -f
'''

archive = bytearray()
ino = 0


def add(name, mode, data=b'', rdevmajor=0, rdevminor=0):
    global ino
    ino += 1
    n = name.encode()+b'\0'
    values = [ino, mode, 0, 0, 1, 0, len(data), 0, 0, rdevmajor, rdevminor, len(n), 0]
    header = b'070701'+b''.join(f'{x:08x}'.encode() for x in values)
    archive.extend(header+n)
    archive.extend(b'\0'*(-len(archive)%4))
    archive.extend(data)
    archive.extend(b'\0'*(-len(archive)%4))


for d in ['dev','proc','sys','tmp','work']:
    add(d, stat.S_IFDIR|0o755)
add('dev/console', stat.S_IFCHR|0o600, rdevmajor=5, rdevminor=1)
for p in sorted(root.rglob('*')):
    name = str(p.relative_to(root))
    if name.startswith('boot') or (name.startswith('lib/modules') and p.is_file()
       and not (name.endswith(('/fuse.ko.gz','/virtiofs.ko.gz'))
                or '/net/netfilter/' in name or '/net/ipv4/netfilter/' in name
                or '/net/ipv6/netfilter/' in name or '/kernel/lib/' in name
                or '/kernel/crypto/crc' in name or Path(name).name.startswith('modules.'))):
        continue
    st = p.lstat()
    if p.is_symlink():
        add(name, stat.S_IFLNK|0o777, os.readlink(p).encode())
    elif p.is_dir():
        add(name, stat.S_IFDIR|0o755)
    elif p.is_file():
        add(name, stat.S_IFREG|(st.st_mode&0o777), p.read_bytes())
add('init', stat.S_IFREG|0o755, init)
add('TRAILER!!!', 0)
(base/'tools/linux-initramfs.gz').write_bytes(gzip.compress(archive, mtime=0))
print('kernel',len(kernel),'initramfs',len(archive))
