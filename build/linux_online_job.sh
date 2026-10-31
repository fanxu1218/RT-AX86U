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
cp /work/build/casefs/rootfs/usr/libexec/localmod/installer-guard.sh /usr/libexec/localmod/
cat > /usr/libexec/localmod/plugin-txn <<'SCRIPT'
#!/bin/sh
exec /usr/bin/qemu-arm -L /work/build/casefs/official_rootfs /work/build/plugin-txn "$@"
SCRIPT
chmod 500 /usr/libexec/localmod/plugin-txn
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
mv /koolshare/bin/versioncmp /koolshare/bin/versioncmp.arm
cat > /koolshare/bin/versioncmp <<'SCRIPT'
#!/bin/sh
exec /usr/bin/qemu-arm -L /work/build/casefs/official_rootfs /koolshare/bin/versioncmp.arm "$@"
SCRIPT
chmod 755 /koolshare/bin/versioncmp
cp /work/build/casefs/rootfs/usr/sbin/wget /usr/libexec/localmod/wget
chmod 500 /usr/libexec/localmod/wget
cat > /usr/sbin/wget <<'SCRIPT'
#!/bin/sh
[ -z "${LD_PRELOAD:-}" ] || exit 97
is_uu=0
for arg do
 case "$arg" in
  'https://router.uu.163.com/api/script/monitor?type=asuswrt'|http://uu.fixture.test:35000/monitor) is_uu=1;;
 esac
done
count=$#
while [ "$count" -gt 0 ]; do
 arg=$1;shift
 case "$arg" in
  --no-check-certificate*)
   [ "$is_uu" = 1 ] || exit 97
   count=$((count-1))
   continue;;
  'https://router.uu.163.com/api/script/monitor?type=asuswrt') arg=http://uu.fixture.test:35000/api;;
  http://uu.fixture.test:35000/monitor|https://repo.fixture.test:35001/*|https://repo.fixture.test:35002/*|https://bad-name.test:35001/*) ;;
  http://*|https://*) exit 97;;
 esac
 set -- "$@" "$arg"
 count=$((count-1))
done
printf '%s\n' "$*" >> /tmp/online-wget-calls
exec /usr/bin/qemu-arm -L /work/build/casefs/official_rootfs /usr/libexec/localmod/wget --ca-certificate=/tmp/online-repo-ca.pem "$@"
SCRIPT
chmod 755 /usr/sbin/wget
rm -f /bin/wget
ln -s /usr/sbin/wget /bin/wget
printf '127.0.0.1 bad-name.test repo.fixture.test uu.fixture.test\n' >> /etc/hosts
phase=$(cat /work/build/online-phase)
case "$phase" in success|errors|concurrent) ;; *) exit 2;; esac
/work/build/test-online "$phase"
