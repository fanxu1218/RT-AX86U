#!/bin/sh
# SPDX-License-Identifier: MIT
# prepare runs at JFFS mount completion; start runs at the init idle boundary.
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
BASE=/tmp/.localmod
KSROOT=/koolshare
export KSROOT PERP_BASE=/koolshare/perp
VERSION=$(cat /rom/etc/localmod-core-id 2>/dev/null)
[ -n "$VERSION" ] || VERSION=localmod2
command=${1:-start}
mkdir -p "$BASE"
chmod 700 "$BASE"
exec >>"$BASE/bootstrap.log" 2>&1

prepare(){
 grep -q ' /jffs ' /proc/mounts || { echo 'JFFS is not mounted'; return 1; }
 mkdir -p /jffs/.localmod /tmp/upload /jffs/scripts /jffs/configs/dnsmasq.d
 if [ ! -f /jffs/.localmod/initialized ]; then
  required=$(du -sk /rom/etc/koolshare | awk '{print $1}')
  available=$(df -k /jffs | awk 'END {print $4}')
  case "$required:$available" in *[!0-9:]*) return 1;; esac
  [ -n "$required" ] && [ -n "$available" ] && [ "$available" -ge $((required+2048)) ] || return 1
  if [ -e /jffs/.koolshare ]; then
   [ ! -e /jffs/.koolshare.pre-localmod ] || { echo 'Old-center backup conflict'; return 1; }
   mv /jffs/.koolshare /jffs/.koolshare.pre-localmod || return 1
  fi
  if [ -e /jffs/.asusrouter ]; then
   [ ! -e /jffs/.localmod/asusrouter.previous ] || return 1
   mv /jffs/.asusrouter /jffs/.localmod/asusrouter.previous || return 1
  fi
 fi
 if [ "$(cat /jffs/.localmod/core-version 2>/dev/null)" != "$VERSION" ]; then
  if pidof httpdb perpd >/dev/null 2>&1; then echo 'Stop the existing center before replacing its managed core'; return 1; fi
  mkdir -p /jffs/.koolshare
  cp -a /rom/etc/koolshare/. /jffs/.koolshare/ || return 1
  # Remove only incompatible files previously owned by the center itself.
  rm -f /jffs/.koolshare/init.d/V02debug.sh /jffs/.koolshare/scripts/ks_debug.sh /jffs/.koolshare/perp/.control/perpd.pid
  printf '%s\n' "$VERSION" > /jffs/.localmod/core-version
  touch /jffs/.localmod/initialized
 fi
 mkdir -p /koolshare/configs /jffs/.localmod/ksdb
 [ -n "$(nvram get jffs2_scripts)" ] || nvram set jffs2_scripts=1
 nvram set sc_url=https://rogsoft.ddnsto.com
 nvram set sc_skin=ASUSWRT
 skipd_start && eventd_start
}

protect_api(){
 iptables -N LOCALMOD_API 2>/dev/null || true
 # This helper runs only with httpdb stopped. Normal table replacement is
 # protected atomically by the iptables-restore adapter.
 iptables -F LOCALMOD_API || return 1
 iptables -A LOCALMOD_API -i lo -s 127.0.0.1/32 -p tcp --sport 1:1023 -j RETURN || return 1
 iptables -A LOCALMOD_API -j REJECT || return 1
 iptables -C INPUT -d 127.0.0.1/32 -p tcp --dport 3032 -j LOCALMOD_API 2>/dev/null ||
  iptables -I INPUT 1 -d 127.0.0.1/32 -p tcp --dport 3032 -j LOCALMOD_API
}

skipd_start(){
 pidof skipd >/dev/null 2>&1 && return 0
 /usr/bin/skipd -d /jffs/.localmod/ksdb >"$BASE/skipd.log" 2>&1 &
 retries=30
 while ! /usr/bin/dbus list softcenter_ >/dev/null 2>&1; do
  retries=$((retries-1)); [ "$retries" -gt 0 ] || return 1
  sleep 1
 done
 /usr/bin/dbus set softcenter_version="$(cat /rom/etc/koolshare/.soft_ver)"
 /usr/bin/dbus set softcenter_home_url=https://rogsoft.ddnsto.com
}


# A read commits pending skipd writes. A successful set response alone does not
# establish persistence in the packaged skipd 3.0.0. Bound the barrier, then wait
# for the old process to exit before a restart can reuse its database/socket.
skipd_stop(){
 pidof skipd >/dev/null 2>&1 || return 0
 /usr/bin/dbus list __localmod_shutdown_barrier__ >/dev/null 2>&1 &
 reader=$!
 ( sleep 5; kill "$reader" 2>/dev/null ) &
 timer=$!
 wait "$reader"; barrier_status=$?
 kill "$timer" 2>/dev/null; wait "$timer" 2>/dev/null
 if [ "$barrier_status" -ne 0 ]; then echo 'Database commit barrier failed; preserving the running database'; return 1; fi
 killall skipd 2>/dev/null || true
 attempts=5
 while pidof skipd >/dev/null 2>&1; do
  attempts=$((attempts-1)); [ "$attempts" -gt 0 ] || { echo 'Database process did not stop'; return 1; }
  sleep 1
 done
 sync
}

eventd_start(){
 if [ -s "$BASE/eventd.pid" ]; then
  pid=$(cat "$BASE/eventd.pid")
  if [ -r "/proc/$pid/cmdline" ] && grep -q 'localmod-event' "/proc/$pid/cmdline"; then return 0; fi
 fi
 /usr/libexec/localmod/localmod-event --daemon >"$BASE/events.log" 2>&1 &
 child=$!
 attempts=10
 while [ "$attempts" -gt 0 ]; do
  if [ "$(cat "$BASE/eventd.pid" 2>/dev/null)" = "$child" ] && kill -0 "$child" 2>/dev/null; then return 0; fi
  kill -0 "$child" 2>/dev/null || { wait "$child" 2>/dev/null; return 1; }
  attempts=$((attempts-1)); sleep 1
 done
 kill "$child" 2>/dev/null; return 1
}
backend_stop(){
 export PATH=/koolshare/bin:/koolshare/scripts:$PATH
 [ ! -f /koolshare/perp/perp.sh ] || sh /koolshare/perp/perp.sh stop
 skipd_stop
}
stop(){
 backend_stop || return 1
 if [ -s "$BASE/eventd.pid" ]; then
  pid=$(cat "$BASE/eventd.pid")
  if [ -r "/proc/$pid/cmdline" ] && grep -q 'localmod-event' "/proc/$pid/cmdline"; then
   kill "$pid" 2>/dev/null
   attempts=5
   while [ "$attempts" -gt 0 ] && [ -r "/proc/$pid/cmdline" ] && grep -q 'localmod-event' "/proc/$pid/cmdline"; do
    attempts=$((attempts-1));sleep 1
   done
  fi
  rm -f "$BASE/eventd.pid"
 fi
 rm -f "$BASE/queue/"*.evt
}
start(){
 prepare || return 1
 export PATH=/koolshare/bin:/koolshare/scripts:$PATH
 mkdir -p /var/log/perpd
 skipd_start || return 1
 if ! pidof httpdb >/dev/null 2>&1; then
  protect_api || { echo 'Private API isolation unavailable'; return 1; }
  sh /koolshare/perp/perp.sh start || return 1
 fi
 eventd_start
}
if [ -e /jffs/localmod-disabled ]; then
 case "$command" in stop|stop-backend|skipd-stop) ;; *) stop; exit $?;; esac
fi
case "$command" in
 prepare) prepare;;
 start) start;;
 stop) stop;;
 stop-backend) backend_stop;;
 restart) stop && start;;
 skipd-start) prepare && skipd_start;;
 skipd-stop) skipd_stop;;
 skipd-restart) skipd_stop && prepare && skipd_start;;
 *) echo "Unsupported localmod service: $command"; exit 2;;
esac
