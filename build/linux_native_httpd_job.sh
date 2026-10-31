#!/bin/sh
set -eu
export PATH=/koolshare/bin:/koolshare/scripts:/usr/sbin:/usr/bin:/sbin:/bin
ulimit -c 0
ip addr add 192.168.77.1/24 dev lo
trap 'cat /tmp/skipd.log /tmp/httpdb.log 2>/dev/null || true' EXIT
mkdir -p /usr/sbin /tmp/.localmod /www /var/run /var/lock /tmp/etc /jffs /usr/libexec/localmod /koolshare/webs /koolshare/scripts /tmp/ksdb
cp -a /work/build/casefs/rootfs/www/. /www/
printf NATIVE_VENDOR_PROTECTED > /www/Module_NativeProbe.asp
cp /work/build/casefs/rootfs/usr/libexec/localmod/httpd /usr/libexec/localmod/httpd
chmod 500 /usr/libexec/localmod/httpd
hash=$(cat /work/build/native_shadow_hash.txt)
printf 'admin:x:0:0:fixture:/tmp:/bin/sh\n' > /etc/passwd
printf 'admin:%s:19000:0:99999:7:::\n' "$hash" > /etc/shadow
cp /etc/passwd /var/passwd
cp /etc/shadow /var/shadow
/usr/bin/qemu-arm /work/build/casefs/rootfs/usr/bin/skipd -d /tmp/ksdb > /tmp/skipd.log 2>&1 &
attempts=30
while [ ! -S /tmp/.skipd_server_sock ]; do
 attempts=$((attempts-1)); [ "$attempts" -gt 0 ] || exit 1; sleep 0.1
done
/usr/bin/qemu-arm /work/build/casefs/rootfs/usr/bin/dbus set localmod_native_probe=real-native-session
/usr/bin/qemu-arm /work/build/casefs/rootfs/rom/etc/koolshare/bin/httpdb -p 127.0.0.1:3032 -r 127.0.0.1:34080 > /tmp/httpdb.log 2>&1 &
cat > /usr/bin/dbus <<'SCRIPT'
#!/bin/sh
exec /usr/bin/qemu-arm /work/build/casefs/rootfs/usr/bin/dbus "$@"
SCRIPT
chmod 755 /usr/bin/dbus
cp /work/build/casefs/rootfs/rom/etc/koolshare/scripts/base.sh /koolshare/scripts/base.sh
cat > /koolshare/scripts/native_probe.sh <<'SCRIPT'
#!/bin/sh
. /koolshare/scripts/base.sh
input=$(dbus get localmod_native_input)
dbus set localmod_native_output="$input-pass"
http_response "$ID"
SCRIPT
chmod 755 /koolshare/scripts/native_probe.sh
cd /www
/work/build/test-native-httpd
