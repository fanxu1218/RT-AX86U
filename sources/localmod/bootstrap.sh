#!/bin/sh
# Local build initialization. Runs after the unmodified vendor init mounts JFFS.
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
count=0
while ! grep -q ' /jffs ' /proc/mounts 2>/dev/null; do
 count=$((count+1)); [ "$count" -lt 180 ] || exit 1
 sleep 1
done
mkdir -p /tmp/localmod
chmod 700 /tmp/localmod
exec >>/tmp/localmod/bootstrap.log 2>&1
if [ -e /jffs/localmod-disabled ]; then
 echo "Software center disabled by recovery marker"
 exit 0
fi
if ! mkdir /tmp/localmod/bootstrap.lock 2>/dev/null; then exit 0; fi
trap 'rmdir /tmp/localmod/bootstrap.lock 2>/dev/null' EXIT
mkdir -p /jffs/.localmod /tmp/upload
if [ ! -f /jffs/.localmod/initialized ]; then
 required=$(du -sk /rom/etc/koolshare | awk '{print $1}')
 available=$(df -k /jffs | awk 'END {print $4}')
 case "$required:$available" in *[!0-9:]*) echo "Cannot determine JFFS free space"; exit 1;; esac
 [ -n "$required" ] && [ -n "$available" ] && [ "$available" -ge $((required+2048)) ] || {
  echo "Insufficient JFFS free space; keeping the previous software center intact"
  exit 1
 }
 # Preserve the old center and its database; do not auto-start old plugins.
 if [ -e /jffs/.koolshare ] && [ ! -e /jffs/.koolshare.pre-localmod ]; then
  mv /jffs/.koolshare /jffs/.koolshare.pre-localmod || exit 1
 elif [ -e /jffs/.koolshare ]; then
  echo "Both current and backup software-center directories exist; manual migration required"
  exit 1
 fi
 if [ -e /jffs/.asusrouter ] && [ ! -e /jffs/.localmod/asusrouter.previous ]; then
  mv /jffs/.asusrouter /jffs/.localmod/asusrouter.previous || exit 1
 fi
 mkdir -p /jffs/.koolshare
 cp -a /rom/etc/koolshare/. /jffs/.koolshare/ || exit 1
 touch /jffs/.localmod/initialized
fi
export KSROOT=/koolshare
export PATH=/koolshare/bin:/koolshare/scripts:$PATH
export PERP_BASE=/koolshare/perp
protect_api(){
 # Restrict the loopback API to privileged source ports, including native callbacks.
 iptables -N LOCALMOD_API 2>/dev/null || true
 iptables -F LOCALMOD_API || return 1
 iptables -A LOCALMOD_API -i lo -s 127.0.0.1/32 -p tcp --sport 1:1023 -j RETURN || return 1
 iptables -A LOCALMOD_API -j REJECT || return 1
 iptables -C INPUT -d 127.0.0.1/32 -p tcp --dport 3032 -j LOCALMOD_API 2>/dev/null ||
  iptables -I INPUT 1 -d 127.0.0.1/32 -p tcp --dport 3032 -j LOCALMOD_API
}
protect_api || { echo "Required local API isolation is unavailable; not starting software center"; exit 1; }
nvram set sc_url=https://rogsoft.ddnsto.com
nvram set sc_skin=ASUSWRT
nvram set jffs2_scripts=1
if pidof skipd httpdb perpd >/dev/null 2>&1; then
 echo "An existing software-center process is active; refusing duplicate startup"
 exit 1
fi
mkdir -p /jffs/.localmod/ksdb /koolshare/configs /var/log/perpd
/usr/bin/skipd -d /jffs/.localmod/ksdb >/tmp/localmod/skipd.log 2>&1 &
sleep 1
/usr/bin/dbus set softcenter_version="$(cat /rom/etc/koolshare/.soft_ver)"
/usr/bin/dbus set softcenter_home_url=https://rogsoft.ddnsto.com
sh /koolshare/perp/perp.sh start
for script in /koolshare/init.d/S*.sh; do
 [ -f "$script" ] && sh "$script" start
done
echo "Software center started; vendor HTTPS and UU files retained"
# Stock firewall restarts may rebuild INPUT. Repair the local rule before
# restarting the backend. This watchdog does not provide an atomic firewall hook.
while sleep 3; do
 if [ -e /jffs/localmod-disabled ]; then
  sh /koolshare/perp/perp.sh stop
  exit 0
 fi
 if ! iptables -C INPUT -d 127.0.0.1/32 -p tcp --dport 3032 -j LOCALMOD_API 2>/dev/null ||
    ! iptables -C LOCALMOD_API -j REJECT 2>/dev/null; then
  sh /koolshare/perp/perp.sh stop
  if protect_api; then sh /koolshare/perp/perp.sh start; fi
 fi
done
