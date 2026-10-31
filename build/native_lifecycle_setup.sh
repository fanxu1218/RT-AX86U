#!/bin/sh
# Test-only guest setup. All writable state is synthetic and private to this VM.
set -eu
ulimit -c 0
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export NATIVE_CERT_CASE=1 NATIVE_STATE_DIRECTORY=/tmp/native-nvram
mkdir -p "$NATIVE_STATE_DIRECTORY" /usr/libexec/localmod /var/run /var/lock /jffs /www /tmp/etc
chmod 700 "$NATIVE_STATE_DIRECTORY"
ip addr add 192.168.77.1/24 dev lo
cp -a /work/build/casefs/rootfs/www/. /www/
cp /work/build/casefs/rootfs/usr/libexec/localmod/httpd /usr/libexec/localmod/httpd
cp /work/build/casefs/rootfs/usr/libexec/localmod/rc.vendor /usr/libexec/localmod/rc.vendor
cp /work/build/casefs/rootfs/usr/sbin/openssl /usr/libexec/localmod/openssl
chmod 500 /usr/libexec/localmod/httpd /usr/libexec/localmod/rc.vendor /usr/libexec/localmod/openssl
cp /work/build/casefs/rootfs/rom/etc/openssl.cnf /etc/openssl.cnf
cp /work/build/casefs/rootfs/usr/sbin/gencert.sh /usr/sbin/gencert.sh
chmod 755 /usr/sbin/gencert.sh
cat > /bin/nvram <<'SCRIPT'
#!/bin/sh
exec /usr/bin/qemu-arm -L /work/build/casefs/official_rootfs /work/build/native-nvram "$@"
SCRIPT
cat > /usr/sbin/openssl <<'SCRIPT'
#!/bin/sh
[ -z "${LD_PRELOAD:-}" ] || exit 19
printf '%s\n' "$*" >> /tmp/native-openssl-invocations
exec /usr/bin/qemu-arm -L /work/build/casefs/official_rootfs /usr/libexec/localmod/openssl "$@"
SCRIPT
chmod 755 /bin/nvram /usr/sbin/openssl
hash=$(cat /work/build/native_shadow_hash.txt)
printf 'admin:x:0:0:fixture:/tmp:/bin/sh\n' > /etc/passwd
printf 'admin:%s:19000:0:99999:7:::\n' "$hash" > /etc/shadow
cp /etc/passwd /var/passwd
cp /etc/shadow /var/shadow
