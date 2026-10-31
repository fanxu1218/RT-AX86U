#!/bin/sh
set -eu
ulimit -c 0
mkdir -p /var/run /var/lock /tmp /jffs /usr/bin /usr/libexec/localmod
cp /work/build/casefs/rootfs/usr/libexec/localmod/rc.vendor /usr/libexec/localmod/rc.vendor
chmod 500 /usr/libexec/localmod/rc.vendor
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
cat > /bin/nvram <<'SCRIPT'
#!/bin/sh
case "$1:$2" in get:jffs2_scripts) echo 1;; esac
SCRIPT
chmod 755 /bin/nvram
/work/build/test-native-uu
