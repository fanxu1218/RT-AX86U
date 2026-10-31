#!/bin/sh
# SPDX-License-Identifier: MIT
# Standard single-root HND packages; share the online checkpoint and lock.
. /koolshare/scripts/base.sh
LOG_FILE=/tmp/upload/soft_log.txt
. /usr/libexec/localmod/installer-guard.sh
ks_operation_begin "$1" offline || exit 1
upload=$(dbus get soft_name)
http_response "$1"
offline_install(){
 : > "$LOG_FILE"
 case "$upload" in ''|*/*|*'..'*|*[!a-zA-Z0-9_.-]*) echo_date "无效的上传文件名。"; ks_finish 1;; esac
 [ -f "/tmp/upload/$upload" ] && [ ! -L "/tmp/upload/$upload" ] || { echo_date "未找到上传的安装包。"; ks_finish 1; }
 cp "/tmp/upload/$upload" "$KS_DOWNLOAD" || ks_finish 1
 tar -tzf "$KS_DOWNLOAD" > "$KS_LOCK/members" 2>/dev/null || ks_finish 1
 softcenter_installing_todo=$(sed 's|^\./||' "$KS_LOCK/members" | head -n1 | cut -d/ -f1)
 ks_valid_module "$softcenter_installing_todo" || ks_finish 1
 case "$softcenter_installing_todo" in softcenter|koolcenter) echo_date "此官改的软件中心核心随固件更新，不接受离线覆盖核心。"; ks_finish 1;; esac
 ks_archive_valid || { echo_date "插件压缩包目录不匹配或解压失败！"; ks_finish 1; }
 ks_scope_prepare || ks_finish 1
 tar -zxf "$KS_DOWNLOAD" -C /tmp || ks_finish 1
 [ -f "$KS_STAGE/install.sh" ] && [ -f "$KS_STAGE/.valid" ] &&
  grep -qw hnd "$KS_STAGE/.valid" || { echo_date "安装包不是ASUS hnd平台或缺少安装脚本。"; ks_finish 1; }
 ks_checkpoint || ks_finish 1
 ks_uninstaller_backup || ks_finish 1
 if [ -f "$KS_STAGE/uninstall.sh" ]; then
  cp "$KS_STAGE/uninstall.sh" "/koolshare/scripts/uninstall_$softcenter_installing_todo.sh" || ks_finish 1
  chmod 755 "/koolshare/scripts/uninstall_$softcenter_installing_todo.sh"
 fi
 # Match the upstream registration contract: an installer declares its new
 # version, otherwise the fallback is 0.1 rather than a stale old version.
 dbus remove "softcenter_module_${softcenter_installing_todo}_version"
 chmod 755 "$KS_STAGE/install.sh"
 if ! start-stop-daemon -S -q -x "$KS_STAGE/install.sh"; then
  ks_uninstaller_restore
  ks_finish 1
 fi
 [ -n "$(dbus get softcenter_module_${softcenter_installing_todo}_name)" ] || dbus set "softcenter_module_${softcenter_installing_todo}_name=$softcenter_installing_todo"
 [ -n "$(dbus get softcenter_module_${softcenter_installing_todo}_title)" ] || dbus set "softcenter_module_${softcenter_installing_todo}_title=$softcenter_installing_todo"
 dbus set "softcenter_module_${softcenter_installing_todo}_install=1"
 [ -n "$(dbus get softcenter_module_${softcenter_installing_todo}_version)" ] || dbus set "softcenter_module_${softcenter_installing_todo}_version=0.1"
 # Only the submitted upload and this operation's stage/download are owned.
 rm -f "/tmp/upload/$upload"
 dbus remove soft_name
 dbus remove soft_install_version
 ks_finish 0
}
offline_install 2>&1 | tee -a "$LOG_FILE" /tmp/upload/soft_log_backup.txt
ks_operation_result
