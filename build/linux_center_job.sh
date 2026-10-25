#!/bin/sh
set -eu
trap 'cp /tmp/upload/soft_log.txt /work/build/center_install_trace.log 2>/dev/null || true; cp /tmp/.localmod/bootstrap.log /work/build/center_bootstrap_trace.log 2>/dev/null || true' EXIT
mkdir -p /jffs /rom/etc /usr/bin /usr/sbin /usr/libexec/localmod /tmp/upload /www/css
mount -t tmpfs -o size=64m tmpfs /jffs
ln -s /jffs/.koolshare /koolshare
ln -s /work/build/casefs/rootfs/rom/etc/koolshare /rom/etc/koolshare
cp /work/build/casefs/rootfs/rom/etc/localmod-core-id /rom/etc/
cp /work/sources/localmod/bootstrap.sh /usr/libexec/localmod/
cat > /bin/nvram <<'EOF'
#!/bin/sh
case "$1:$2" in get:jffs2_scripts) echo 1;; get:sc_skin) echo ASUSWRT;; get:odmpid|get:productid) echo RT-AX86U;; esac
EOF
chmod 755 /bin/nvram
mkdir -p /tmp/process-tools
# QEMU otherwise names every emulated process qemu-arm, hiding the target's
# normal skipd/httpdb names from the production pidof/killall lifecycle.
ln /usr/bin/qemu-arm /tmp/process-tools/skipd
ln /usr/bin/qemu-arm /tmp/process-tools/httpdb
for tool in dbus skipd; do
 if [ "$tool" = skipd ]; then emulator=/tmp/process-tools/skipd; else emulator=/usr/bin/qemu-arm; fi
 printf '#!/bin/sh\nexec %s /work/build/casefs/rootfs/usr/bin/%s "$@"\n' "$emulator" "$tool" > "/usr/bin/$tool"
 chmod 755 "/usr/bin/$tool"
done
cat > /usr/libexec/localmod/localmod-event <<'EOF'
#!/bin/sh
exec /usr/bin/qemu-arm -L /work/build/casefs/official_rootfs /work/build/localmod-event "$@"
EOF
chmod 755 /usr/libexec/localmod/localmod-event
mkdir -p /jffs/.koolshare
printf old-plugin > /jffs/.koolshare/old-plugin
sh /usr/libexec/localmod/bootstrap.sh prepare
[ "$(cat /jffs/.koolshare.pre-localmod/old-plugin)" = old-plugin ]
[ ! -e /koolshare/old-plugin ]
/usr/bin/dbus set localmod_migration_probe=retained
sh /usr/libexec/localmod/bootstrap.sh stop
printf retained-plugin > /koolshare/retained-plugin
printf '#!/bin/sh\necho user-owned\n' > /jffs/scripts/wan-start
before_hook=$(sha256sum /jffs/scripts/wan-start | awk '{print $1}')
printf old-localmod1 > /jffs/.localmod/core-version
sh /usr/libexec/localmod/bootstrap.sh prepare
[ "$(cat /koolshare/retained-plugin)" = retained-plugin ]
[ "$(sha256sum /jffs/scripts/wan-start | awk '{print $1}')" = "$before_hook" ]
[ "$(/usr/bin/dbus get localmod_migration_probe)" = retained ]
for round in 1 2; do
 /usr/bin/dbus set localmod_restart_probe=round_$round
 sh /usr/libexec/localmod/bootstrap.sh skipd-restart
 [ "$(/usr/bin/dbus get localmod_restart_probe)" = round_$round ]
done
echo 'PASS immediate writes survive skipd service restarts'
echo 'PASS database value and exact user hook bytes survive managed-core upgrade'
echo 'PASS initial center migration archives old plugins; managed-core upgrade preserves current plugins and user hooks'
for tool in versioncmp; do
 mv "/koolshare/bin/$tool" "/koolshare/bin/$tool.arm"
 printf '#!/bin/sh\nexec /usr/bin/qemu-arm -L /work/build/casefs/official_rootfs /koolshare/bin/%s.arm "$@"\n' "$tool" > "/koolshare/bin/$tool"
 chmod 755 "/koolshare/bin/$tool"
done
cat > /koolshare/bin/start-stop-daemon <<'EOF'
#!/bin/sh
# Use the native OpenRC helper for /proc enumeration in this ARM64 guest.
exec /sbin/start-stop-daemon "$@"
EOF
chmod 755 /koolshare/bin/start-stop-daemon
printf 'background: #4F5B5F\n' > /www/form_style.css
for name in localmod_probe wrong_platform softcenter; do
 mkdir -p "/tmp/package-fixtures/$name/webs" "/tmp/package-fixtures/$name/scripts"
 printf '<html><body>localmod-probe</body></html>\n' > "/tmp/package-fixtures/$name/webs/Module_$name.asp"
 printf hnd > "/tmp/package-fixtures/$name/.valid"
 printf '#!/bin/sh\ntouch /tmp/%s-installed\n' "$name" > "/tmp/package-fixtures/$name/install.sh"
done
printf mtk > /tmp/package-fixtures/wrong_platform/.valid
cat > /tmp/package-fixtures/localmod_probe/install.sh <<'EOF'
#!/bin/sh
mkdir -p /koolshare/webs /koolshare/scripts
cp /tmp/localmod_probe/webs/Module_localmod_probe.asp /koolshare/webs/
cp /tmp/localmod_probe/scripts/localmod_probe.sh /koolshare/scripts/
chmod 755 /koolshare/scripts/localmod_probe.sh
dbus set softcenter_module_localmod_probe_install=1
dbus set softcenter_module_localmod_probe_version=1.0
EOF
cat > /tmp/package-fixtures/localmod_probe/scripts/localmod_probe.sh <<'EOF'
#!/bin/sh
. /koolshare/scripts/base.sh
input=$(dbus get localmod_probe_input)
dbus set localmod_probe_runtime="$input-ok"
http_response "$ID"
EOF
for name in localmod_probe wrong_platform softcenter; do
 tar -czf "/tmp/package-fixtures/$name.tar.gz" -C /tmp/package-fixtures "$name"
done
cp /tmp/package-fixtures/localmod_probe.tar.gz /tmp/upload/
/work/build/test-center
