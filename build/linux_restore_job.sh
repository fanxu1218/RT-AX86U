#!/bin/sh
set -eu
mkdir -p /run /jffs/scripts /tmp/.localmod /usr/libexec/localmod /koolshare/bin /koolshare/init.d /koolshare/scripts /usr/sbin
chmod 700 /tmp/.localmod
modprobe iptable_filter
modprobe crc32c_generic
modprobe iptable_nat
modprobe xt_tcpudp
modprobe ipt_REJECT
uname -r > /work/build/restore_kernel_version.txt
iptables-legacy --version > /work/build/restore_helper_version.txt
cat > /bin/nvram <<'EOF'
#!/bin/sh
case "$1:$2" in get:jffs2_scripts) echo 1;; get:wan_primary) echo 0;; get:wan0_gw_ifname) echo ppp0;; esac
EOF
chmod 755 /bin/nvram
cp /work/sources/localmod/dispatch.sh /usr/libexec/localmod/dispatch.sh
chmod 755 /usr/libexec/localmod/dispatch.sh
for name in nat-start firewall-start; do
 printf '#!/bin/sh\nprintf "%s %%s\\n" "$*" >> /tmp/restore_hook_trace\n' "$name" > "/jffs/scripts/$name"
 chmod 755 "/jffs/scripts/$name"
done
cp /work/build/casefs/rootfs/rom/etc/koolshare/bin/ks-nat-start.sh /koolshare/bin/
chmod 755 /koolshare/bin/ks-nat-start.sh
printf '#!/bin/sh\n_LOG(){ :; }\n' > /koolshare/scripts/base.sh
printf '#!/bin/sh\necho CENTER-N-$1 >> /tmp/restore_hook_trace\n' > /koolshare/init.d/N10probe.sh
chmod 755 /koolshare/init.d/N10probe.sh
/work/build/test-restore
/usr/bin/qemu-arm -L /work/build/casefs/official_rootfs /work/build/localmod-event --drain
cp /tmp/restore_hook_trace /work/build/restore_hook_trace.log
