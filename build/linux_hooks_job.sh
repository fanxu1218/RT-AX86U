#!/bin/sh
set -eux
trap 'cp /tmp/hook_trace /work/build/hooks_trace.log 2>/dev/null || true; cp /etc/dnsmasq.conf /work/build/hooks_dnsmasq.conf 2>/dev/null || true' EXIT
mkdir -p /usr/libexec/localmod /usr/sbin /jffs/scripts /jffs/configs/dnsmasq.d /koolshare/bin /koolshare/scripts /koolshare/init.d /tmp/.localmod /etc /www/css
chmod 700 /tmp/.localmod
cp /work/sources/localmod/dispatch.sh /usr/libexec/localmod/dispatch.sh
chmod 755 /usr/libexec/localmod/dispatch.sh
cat > /usr/libexec/localmod/bootstrap.sh <<'EOF'
#!/bin/sh
printf 'BOOTSTRAP %s\n' "$1" >> /tmp/hook_trace
EOF
chmod 755 /usr/libexec/localmod/bootstrap.sh
cat > /usr/libexec/localmod/localmod-event <<'EOF'
#!/bin/sh
exec /usr/bin/qemu-arm -L /work/build/casefs/official_rootfs /work/build/localmod-event "$@"
EOF
chmod 755 /usr/libexec/localmod/localmod-event
cat > /bin/nvram <<'EOF'
#!/bin/sh
case "$1:$2" in get:jffs2_scripts) cat /tmp/hook_script_flag;; get:sc_skin) echo ASUSWRT;; esac
EOF
chmod 755 /bin/nvram
printf 'base-line\n' > /etc/dnsmasq.conf
printf 'custom-option=1\n' > /jffs/configs/dnsmasq.conf.add
cat > /jffs/scripts/dnsmasq.postconf <<'EOF'
#!/bin/sh
printf 'postconf-line\n' >> "$1"
printf 'POSTCONF %s\n' "$1" >> /tmp/hook_trace
EOF
chmod 755 /jffs/scripts/dnsmasq.postconf
for hook in init-start services-start services-stop service-event service-event-end wan-event wan-start pre-mount post-mount unmount; do
 printf '#!/bin/sh\nprintf "USER %s %%s\\n" "$*" >> /tmp/hook_trace\n' "$hook" > "/jffs/scripts/$hook"
 chmod 755 "/jffs/scripts/$hook"
done
printf '/koolshare/bin/ks-wan-start.sh start\n' >> /jffs/scripts/wan-start
for helper in ks-services-start.sh ks-services-stop.sh ks-wan-start.sh ks-nat-start.sh ks-mount-start.sh ks-unmount.sh; do
 cp "/work/build/casefs/rootfs/rom/etc/koolshare/bin/$helper" "/koolshare/bin/$helper"
 chmod 755 "/koolshare/bin/$helper"
done
cat > /koolshare/scripts/base.sh <<'EOF'
#!/bin/sh
export KSROOT=/koolshare
export PATH=/koolshare/bin:/usr/sbin:/usr/bin:/sbin:/bin
_LOG(){ :; }
EOF
printf 'background: #4F5B5F\n' > /www/form_style.css
for prefix in S V T N M U; do
 printf '#!/bin/sh\nprintf "CENTER %s %%s\\n" "$*" >> /tmp/hook_trace\n' "$prefix" > "/koolshare/init.d/${prefix}10probe.sh"
 chmod 755 "/koolshare/init.d/${prefix}10probe.sh"
 if [ "$prefix" = M ] || [ "$prefix" = U ]; then
  printf 'printf "ARGC %s %%s <%%s>\\n" "$#" "$1" >> /tmp/hook_trace\n' "$prefix" >> "/koolshare/init.d/${prefix}10probe.sh"
 fi
done
set +e
/usr/bin/qemu-arm -L /work/build/casefs/official_rootfs -E LD_LIBRARY_PATH=/work/build -E LD_PRELOAD=/work/build/rc_bridge_fixture.so /work/build/rc-fixture
result=$?
echo fixture-return-$result
set -e
[ "$result" = 0 ]
/usr/bin/qemu-arm -L /work/build/casefs/official_rootfs /work/build/localmod-event --drain
/usr/bin/qemu-arm -L /work/build/casefs/official_rootfs /work/build/runtime-fixture
cp /work/build/test-launcher-vendor /usr/libexec/localmod/rc.vendor
chmod 755 /usr/libexec/localmod/rc.vendor
set +e
/usr/bin/qemu-arm -0 hotplug -L /work/build/casefs/official_rootfs /work/build/rc-launcher usb "value with space;literal" > /work/build/launcher_forward.json
forward=$?
touch /jffs/localmod-disabled
/usr/bin/qemu-arm -0 hotplug -L /work/build/casefs/official_rootfs /work/build/rc-launcher usb "value with space;literal" > /work/build/launcher_disabled.json
disabled=$?
rm -f /jffs/localmod-disabled
set -e
[ "$forward" = 19 ] && [ "$disabled" = 19 ]
/usr/bin/qemu-arm -0 service -L /work/build/casefs/official_rootfs /work/build/rc-launcher restart_skipd
cp /tmp/hook_trace /work/build/hooks_trace.log
cp /etc/dnsmasq.conf /work/build/hooks_dnsmasq.conf
