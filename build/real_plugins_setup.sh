#!/bin/sh
set -eu
export PATH=/bin:/usr/bin:/sbin:/usr/sbin
cp /work/build/native-nvram /bin/nvram
chmod 755 /bin/nvram
hash=$(cat /work/build/native_shadow_hash.txt)
printf 'admin:x:0:0:fixture:/tmp:/bin/sh\n' > /var/passwd
printf 'admin:%s:19000:0:99999:7:::\n' "$hash" > /var/shadow
cp /var/shadow /etc/shadow
printf '127.0.0.1 localhost repo.fixture.test uu.fixture.test bad-name.test\n' > /etc/hosts
mkdir -p /var/spool/cron/crontabs /var/run /var/lock
touch /var/spool/cron/crontabs/admin
mkdir -p /var/log/perpd /tmp/upload /run
mv /usr/sbin/wget /usr/libexec/localmod/wget
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
   count=$((count-1));continue;;
  'https://router.uu.163.com/api/script/monitor?type=asuswrt') arg=http://uu.fixture.test:35000/api;;
  http://uu.fixture.test:35000/monitor|https://repo.fixture.test:35001/*) ;;
  http://*|https://*) exit 97;;
 esac
 set -- "$@" "$arg"
 count=$((count-1))
done
printf '%s\n' "$*" >> /tmp/online-wget-calls
exec /usr/libexec/localmod/wget --ca-certificate=/tmp/online-repo-ca.pem "$@"
SCRIPT
chmod 755 /usr/sbin/wget
for tool in iptables ip6tables; do
 rm -f /usr/sbin/$tool
 cat > /usr/sbin/$tool <<SCRIPT
#!/bin/sh
export XTABLES_LIBDIR=/fixture/xtables
exec /lib/ld-musl-aarch64.so.1 --library-path /fixture/lib /fixture/xtables-legacy-multi $tool "\$@"
SCRIPT
 chmod 755 /usr/sbin/$tool
done
/bin/sh /usr/libexec/localmod/bootstrap.sh prepare || { cat /tmp/.localmod/bootstrap.log; exit 1; }
echo "FIXTURE_ARM_ARCH=$(uname -m)"
/koolshare/bin/start-stop-daemon --help 2>&1 | head -3
iptables -L >/tmp/iptables-probe 2>&1 || { cat /tmp/iptables-probe; exit 1; }
/bin/sh /usr/libexec/localmod/bootstrap.sh start || { cat /tmp/.localmod/bootstrap.log; exit 1; }
cat /tmp/.localmod/bootstrap.log
echo REAL_PLUGIN_SETUP_READY

phase=$(cat /work/build/real-plugin-phase)
case "$phase" in soak-*) export LOCALMOD_HTTPS_TRACE=1; exec /work/build/test-soak "$phase";; esac
case "$phase" in https-stability*) export LOCALMOD_HTTPS_TRACE=1; exec /work/build/test-https-stability "$phase";; esac
case "$phase" in
 interrupt-*) exec /work/build/test-interrupt "$phase";;
 upgrade|fresh) ;;
 *) exit 2;;
esac
exec /work/build/test-real-plugins "$phase"
