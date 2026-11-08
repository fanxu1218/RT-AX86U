#!/bin/sh
set -eu
sh -n /work/sources/localmod/bootstrap.sh
# BusyBox cp does not copy macOS com.apple.* attributes into the firmware.
mkdir /tmp/clean-rootfs
cp -a /work/build/casefs/rootfs/. /tmp/clean-rootfs/
mkfs.ubifs @UBIFS_ARGS@ -r /tmp/clean-rootfs -o /work/build/localmod-rootfs.ubifs
/work/build/test-bridge
/work/build/test-real-backend
