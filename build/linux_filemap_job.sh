#!/bin/sh
set -eu
mkdir -p /jffs /tmp/web-fixture
ln -s /work/build/casefs/rootfs/rom/etc/koolshare /jffs/.koolshare
printf VENDOR > /tmp/web-fixture/Module_Builtin.asp
/usr/bin/qemu-arm -L /work/build/casefs/official_rootfs -E LD_LIBRARY_PATH=/work/build -E LD_PRELOAD=/work/build/httpd_bridge.so /work/build/filemap-fixture
