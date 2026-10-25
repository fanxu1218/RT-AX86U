#!/bin/sh
set -eu
sh -n /work/sources/localmod/bootstrap.sh
# BusyBox cp does not copy macOS com.apple.* attributes into the firmware.
mkdir /tmp/clean-rootfs
cp -a /work/build/casefs/rootfs/. /tmp/clean-rootfs/
mkfs.ubifs -U -m 2048 -e 126976 -c 2048 -x zlib -f 8 -l 5 -p 1 -F -j 8388608 -r /tmp/clean-rootfs -o /work/build/localmod-rootfs.ubifs
/work/build/test-bridge
/work/build/test-real-backend
