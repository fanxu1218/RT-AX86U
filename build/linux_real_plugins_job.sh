#!/bin/sh
# Disposable RAM-only router chroot. The only host export is read-only.
set -eu
ulimit -c 0
if (echo forbidden > /work/build/readonly-guest-write-probe) 2>/dev/null; then
 echo 'Read-only export check failed'; exit 1
fi
[ "$(ls /sys/class/net)" = lo ]
gzip -dc /lib/modules/*/kernel/fs/binfmt_misc.ko.gz > /tmp/binfmt.ko
insmod /tmp/binfmt.ko
mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc
printf '%s\n' ':arm:M::\x7fELF\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x28\x00:\xff\xff\xff\xff\xff\xff\xff\x00\xff\xff\xff\xff\xff\xff\xff\xff\xfe\xff\xff\xff:/usr/bin/qemu-arm:F' > /proc/sys/fs/binfmt_misc/register || [ -r /proc/sys/fs/binfmt_misc/arm ]
grep -qx 'flags: F' /proc/sys/fs/binfmt_misc/arm
mkdir /router
cp -a /work/build/casefs/rootfs/. /router/
chown -Rh 0:0 /router
mkdir -p /router/work /router/tmp/var/run /router/tmp/var/lock /router/tmp/var/spool/cron/crontabs
mount --bind /work /router/work
mount -t proc proc /router/proc
mount --bind /sys /router/sys
mount --bind /dev /router/dev
mount -t tmpfs -o size=64m tmpfs /router/jffs
cp /usr/bin/qemu-arm /router/usr/bin/qemu-arm
mkdir -p /router/fixture/lib /router/fixture/xtables
cp -a /lib/*.so* /usr/lib/*.so* /router/fixture/lib/
cp /lib/ld-musl-aarch64.so.1 /router/lib/ld-musl-aarch64.so.1
cp /usr/sbin/xtables-legacy-multi /router/fixture/xtables-legacy-multi
cp /usr/lib/xtables/*.so /router/fixture/xtables/
modprobe iptable_filter
modprobe xt_tcpudp
modprobe ipt_REJECT
modprobe dummy
ip link add br0 type dummy
ip addr add 192.168.77.1/24 dev br0
ip link set br0 up
export NATIVE_CERT_CASE=1 NATIVE_STATE_DIRECTORY=/tmp/native-nvram
export LOCALMOD_QEMU_ROOT=/ LOCALMOD_TEST_OUTPUT=/tmp/real-plugin-results
export LOCALMOD_TLS_START_TIMEOUT=60s
export LOCALMOD_HTTP_REQUEST_TIMEOUT=10s
mkdir -p /router/tmp/native-nvram /router/tmp/real-plugin-results
chroot /router /bin/sh /work/build/real_plugins_setup.sh
