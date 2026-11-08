#!/bin/sh
# SPDX-License-Identifier: MIT
# The native Merlin framework already invokes the user hook. Run only the
# corresponding software-center helper, in the shared deduplication context.
export PATH=/bin:/usr/bin:/sbin:/usr/sbin:/koolshare/bin:/koolshare/scripts
[ ! -e /jffs/localmod-disabled ] || exit 0
[ "$(nvram get jffs2_scripts)" != 0 ] || exit 0
case "$1" in
 services-start) exec /koolshare/bin/ks-services-start.sh;;
 services-stop) exec /koolshare/bin/ks-services-stop.sh;;
 wan-start) exec /koolshare/bin/ks-wan-start.sh start;;
 nat-start) exec /koolshare/bin/ks-nat-start.sh start_nat;;
 post-mount) exec /koolshare/bin/ks-mount-start.sh start "$2";;
 unmount) exec /koolshare/bin/ks-unmount.sh "$2";;
 *) exit 2;;
esac
