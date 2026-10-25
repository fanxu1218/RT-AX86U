#!/bin/sh
# SPDX-License-Identifier: MIT
export PATH=/koolshare/bin:/koolshare/scripts:/usr/sbin:/usr/bin:/sbin:/bin
[ ! -e /jffs/localmod-disabled ] || exit 0
[ "$(nvram get jffs2_scripts)" != 0 ] || exit 0
event=$1
shift
run_user(){
 name=$1; shift
 [ ! -x "/jffs/scripts/$name" ] || "/jffs/scripts/$name" "$@"
}
run_center(){
 name=$1; shift
 [ ! -x "/koolshare/bin/$name" ] || "/koolshare/bin/$name" "$@"
}
case "$event" in
 init-start) run_user init-start;;
 services-start) run_user services-start; run_center ks-services-start.sh;;
 services-stop) run_user services-stop; run_center ks-services-stop.sh;;
 wan-event)
  run_user wan-event "$1" "$2"
  if [ "$2" = connected ]; then run_user wan-start "$1"; run_center ks-wan-start.sh start; fi;;
 wan-start) run_user wan-start "$1"; run_center ks-wan-start.sh start;;
 nat-start) run_user nat-start; run_center ks-nat-start.sh start_nat;;
 firewall-start)
  iface=$1
  if [ -z "$iface" ]; then
   unit=$(nvram get wan_primary); [ -n "$unit" ] || unit=0
   iface=$(nvram get "wan${unit}_gw_ifname"); [ -n "$iface" ] || iface=$(nvram get "wan${unit}_ifname")
  fi
  run_user firewall-start "$iface";;
 pre-mount) run_user pre-mount "$1" "$2";;
 post-mount) run_user post-mount "$1"; run_center ks-mount-start.sh start "$1";;
 unmount) run_user unmount "$1"; run_center ks-unmount.sh "$1";;
 service-event|service-event-end|dhcpc-event) run_user "$event" "$1" "$2";;
 *) exit 2;;
esac
exit 0
