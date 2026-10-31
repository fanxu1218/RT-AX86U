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
if grep -qw localmod_state_disk=1 /proc/cmdline; then
 modprobe virtio_blk
 modprobe crc32c_generic
 modprobe ext4
 for attempt in 1 2 3 4 5; do
  [ ! -b /dev/vda ] || break
  sleep 1
 done
 [ -b /dev/vda ] || { cat /proc/cmdline; ls /sys/class/block /dev; exit 1; }
 if grep -q '"initialize": true' /work/build/interrupt-phase.json; then
  mkfs.ext4 -q -F -O ^metadata_csum,^metadata_csum_seed,^orphan_file -E nodiscard,lazy_itable_init=0,lazy_journal_init=0 -L LOCALMOD_TEST /dev/vda
 fi
 mount -t ext4 /dev/vda /router/jffs || { cat /proc/partitions; cat /proc/filesystems; dmesg | tail -12; exit 1; }
else
 mount -t tmpfs -o size=64m tmpfs /router/jffs
fi
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
export LOCALMOD_NTP_WAIT_TIMEOUT=45s
export LOCALMOD_PLUGIN_OPERATION_TIMEOUT=45s
mkdir -p /router/tmp/native-nvram /router/tmp/real-plugin-results
if grep -qw localmod_state_disk=1 /proc/cmdline; then
 export LOCALMOD_PLUGIN_OPERATION_TIMEOUT=90s
 mv /router/usr/libexec/localmod/plugin-txn /router/usr/libexec/localmod/plugin-txn.real
 cp /work/build/txn_fault_fixture.so /router/fixture/
 cat > /router/usr/libexec/localmod/plugin-txn <<'SCRIPT'
#!/bin/sh
exec /usr/bin/qemu-arm -L / -E LD_PRELOAD=/fixture/txn_fault_fixture.so /usr/libexec/localmod/plugin-txn.real "$@"
SCRIPT
 chmod 755 /router/usr/libexec/localmod/plugin-txn
 /work/build/test-interrupt controller
else
 if grep -q '^soak-' /work/build/real-plugin-phase; then
  /work/build/soak-init-fixture /bin/chroot /router /bin/sh /work/build/real_plugins_setup.sh
 else
  chroot /router /bin/sh /work/build/real_plugins_setup.sh
 fi
fi
