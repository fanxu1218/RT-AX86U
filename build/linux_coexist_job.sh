#!/bin/sh
set -eu
. /work/build/native_lifecycle_setup.sh
trap 'cat /tmp/.localmod/bootstrap.log 2>/dev/null || true' EXIT
mkdir -p /rom/etc /usr/bin /usr/sbin /usr/libexec/localmod /tmp/process-tools /tmp/upload /run
mount -t tmpfs -o size=64m tmpfs /jffs
ln -s /jffs/.koolshare /koolshare
ln -s /work/build/casefs/rootfs/rom/etc/koolshare /rom/etc/koolshare
cp /work/build/casefs/rootfs/rom/etc/localmod-core-id /rom/etc/
cp /work/sources/localmod/bootstrap.sh /work/sources/localmod/dispatch.sh /usr/libexec/localmod/
cp /work/build/native-lifecycle-private/cert.tgz /jffs/cert.tgz
modprobe iptable_filter
modprobe xt_tcpudp
modprobe ipt_REJECT
rm -f /usr/sbin/iptables
ln -s xtables-legacy-multi /usr/sbin/iptables
for tool in dbus skipd; do
 ln /usr/bin/qemu-arm "/tmp/process-tools/$tool"
 printf '#!/bin/sh\nexec /tmp/process-tools/%s -L /work/build/casefs/official_rootfs /work/build/casefs/rootfs/usr/bin/%s "$@"\n' "$tool" "$tool" > "/usr/bin/$tool"
 chmod 755 "/usr/bin/$tool"
done
cat > /usr/libexec/localmod/localmod-event <<'SCRIPT'
#!/bin/sh
exec /usr/bin/qemu-arm -L /work/build/casefs/official_rootfs /work/build/localmod-event "$@"
SCRIPT
chmod 755 /usr/libexec/localmod/localmod-event
# Prepare copies the actual core first; wrappers only bridge CPU/proc ABI in
# this ARM64 guest. The native launchers keep target process names for pidof.
sh /usr/libexec/localmod/bootstrap.sh prepare
for tool in perpboot perpd httpdb tinylog; do
 [ -f "/koolshare/bin/$tool" ] || continue
 mv "/koolshare/bin/$tool" "/koolshare/bin/$tool.arm"
 ln /usr/bin/qemu-arm "/tmp/process-tools/$tool"
 printf '#!/bin/sh\nexec /tmp/process-tools/%s -L /work/build/casefs/official_rootfs /koolshare/bin/%s.arm "$@"\n' "$tool" "$tool" > "/koolshare/bin/$tool"
 chmod 755 "/koolshare/bin/$tool"
done
cat > /koolshare/bin/start-stop-daemon <<'SCRIPT'
#!/bin/sh
exec /sbin/start-stop-daemon "$@"
SCRIPT
chmod 755 /koolshare/bin/start-stop-daemon
cat > /koolshare/scripts/coexist_probe.sh <<'SCRIPT'
#!/bin/sh
. /koolshare/scripts/base.sh
value=$(dbus get localmod_coexist_input)
dbus set localmod_coexist_result="$value-ok"
http_response "$ID"
SCRIPT
chmod 755 /koolshare/scripts/coexist_probe.sh
# The original UU URL is mapped to the owned loopback server; reject every
# other destination. This helper does not supply login or TLS implementations.
cat > /usr/bin/wget <<'SCRIPT'
#!/bin/sh
out=
url=
while [ "$#" -gt 0 ]; do
 case "$1" in -O) shift;out=$1;; http://*|https://*) url=$1;; esac
 shift
done
case "$url" in
 'https://router.uu.163.com/api/script/monitor?type=asuswrt') url=http://127.0.0.1:35000/api;;
 http://127.0.0.1:35000/monitor) ;;
 *) exit 17;;
esac
exec /usr/bin/curl --noproxy '*' --silent --fail --max-time 3 "$url" -o "$out"
SCRIPT
chmod 755 /usr/bin/wget
rm -f /bin/wget
ln -s /usr/bin/wget /bin/wget
/work/build/test-coexist
