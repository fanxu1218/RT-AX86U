#!/bin/sh
# SPDX-License-Identifier: MIT
# Online plugin operations own only their download and freshly created stage.
ks_valid_module(){
 case "$1" in ''|*[!a-zA-Z0-9_-]*) return 1;; esac
 [ "${#1}" -le 64 ]
}
ks_operation_begin(){
 KS_HAVE_LOCK=0
 case "$2" in download_log|clean_log) return 0;; esac
 KS_OWNER_PID=$$
 KS_LOCK=/tmp/.localmod/plugin-operation.lock
 mkdir -p /tmp/.localmod || return 1
 chmod 700 /tmp/.localmod || return 1
 if ! (umask 077; mkdir "$KS_LOCK") 2>/dev/null; then
  echo_date "软件中心：已有插件操作正在运行，本次请求未执行。" >> "$LOG_FILE"
  http_response "$1"
  return 1
 fi
 KS_HAVE_LOCK=1
 KS_STATUS_FILE=$KS_LOCK/status
 KS_DOWNLOAD=$KS_LOCK/package.tar.gz
 printf '%s\n' "$KS_OWNER_PID" > "$KS_LOCK/pid"
 trap 'ks_operation_end' EXIT
 trap 'exit 1' HUP INT TERM
 if ! /usr/libexec/localmod/plugin-txn begin "$KS_OWNER_PID" "${LOG_FILE##*/}"; then
  echo_date "插件操作正在运行或中断恢复尚未完成；请查看日志并重启路由器恢复。" >> "$LOG_FILE"
  http_response "$1"
  rm -rf "$KS_LOCK"
  KS_HAVE_LOCK=0
  return 1
 fi
 /usr/libexec/localmod/plugin-txn watch "$KS_OWNER_PID" || return 1
}
ks_operation_end(){
 [ "$KS_HAVE_LOCK" = 1 ] || return 0
 # ash subshells retain $$; read proc directly to distinguish the lock owner.
 read KS_SELF_PID KS_PROC_REST < /proc/self/stat
 [ "$KS_SELF_PID" = "$KS_OWNER_PID" ] || return 0
 if [ ! -f "$KS_STATUS_FILE" ]; then
  /usr/libexec/localmod/plugin-txn abandon "$KS_OWNER_PID"
 fi
 ks_scope_clean
 rm -rf "$KS_LOCK"
}
ks_operation_validate(){
 [ "$KS_HAVE_LOCK" = 1 ] || return 0
 if ! ks_valid_module "$softcenter_installing_todo"; then
  dbus set softcenter_installing_result=1
  echo_date "软件中心：插件标识无效，本次请求未执行。" >> "$LOG_FILE"
  echo XU6J03M6 >> "$LOG_FILE"
  http_response "$1"
  /usr/libexec/localmod/plugin-txn finish "$KS_OWNER_PID" 1
  printf '1\n' > "$KS_STATUS_FILE"
  return 1
 fi
 dbus set softcenter_installing_result=running
}
ks_checkpoint(){
 /usr/libexec/localmod/plugin-txn checkpoint "$KS_OWNER_PID" "$softcenter_installing_todo"
}
ks_scope_prepare(){
 KS_STAGE=/tmp/$softcenter_installing_todo
 # DDNS-Go creates an empty runtime directory with its package name. Never
 # adopt nonempty state or follow links; rmdir also fails closed on a race.
 if [ -d "$KS_STAGE" ] && [ ! -L "$KS_STAGE" ] &&
    [ "$(dbus get softcenter_module_${softcenter_installing_todo}_install)" = 1 ]; then
  rmdir "$KS_STAGE" 2>/dev/null || true
 fi
 if ! (umask 077; mkdir "$KS_STAGE") 2>/dev/null; then
  echo_date "插件临时目录已存在，保留原内容并停止本次安装：$KS_STAGE"
  return 1
 fi
 printf '%s\n' "$softcenter_installing_todo" > "$KS_LOCK/stage-name"
}
ks_scope_clean(){
 if [ -f "$KS_LOCK/stage-name" ]; then
  KS_OWNED_NAME=$(cat "$KS_LOCK/stage-name")
  if ks_valid_module "$KS_OWNED_NAME"; then rm -rf "/tmp/$KS_OWNED_NAME"; fi
  rm -f "$KS_LOCK/stage-name"
 fi
 rm -f "$KS_DOWNLOAD"
}
ks_archive_valid(){
 tar -tzf "$KS_DOWNLOAD" > "$KS_LOCK/members" 2>/dev/null || return 1
 awk -v module="$softcenter_installing_todo" '
  { sub(/^\.\//, ""); if ($0 != module && index($0,module "/") != 1) bad=1;
    n=split($0,a,"/"); for(i=1;i<=n;i++) if(a[i]=="..") bad=1; count++ }
  END { exit (bad || !count) ? 1 : 0 }' "$KS_LOCK/members"
}
ks_uninstaller_backup(){
 KS_UNINSTALL=/koolshare/scripts/uninstall_$softcenter_installing_todo.sh
 if [ -e "$KS_UNINSTALL" ] || [ -L "$KS_UNINSTALL" ]; then
  cp -a "$KS_UNINSTALL" "$KS_LOCK/uninstaller.previous" || return 1
  touch "$KS_LOCK/uninstaller.existed"
 fi
}
ks_uninstaller_restore(){
 KS_UNINSTALL=/koolshare/scripts/uninstall_$softcenter_installing_todo.sh
 rm -f "$KS_UNINSTALL"
 if [ -f "$KS_LOCK/uninstaller.existed" ]; then
  cp -a "$KS_LOCK/uninstaller.previous" "$KS_UNINSTALL" || return 1
 fi
}
ks_finish(){
 KS_CODE=${1:-1}
 ks_scope_clean
 for KS_FIELD in todo title name tar_url version md5; do dbus set "softcenter_installing_$KS_FIELD="; done
 dbus set "softcenter_installing_result=$KS_CODE"
 # A read commits the packaged skipd's pending writes. Seal the checkpoint
 # only after the installer and its version/configuration writes succeeded.
 if ! dbus list __localmod_plugin_commit_barrier__ >/dev/null 2>&1 ||
    ! /usr/libexec/localmod/plugin-txn finish "$KS_OWNER_PID" "$KS_CODE"; then
  KS_CODE=1
  dbus set softcenter_installing_result=1
 fi
 if [ -d /jffs/.localmod/plugin-txn/active ]; then
  dbus set softcenter_recovery_required=1
  echo_date "未提交的插件变更已保留检查点。请重启检查并尝试恢复；校验或空间异常时会保留副本并停止软件中心。"
 fi
 printf '%s\n' "$KS_CODE" > "$KS_STATUS_FILE"
 echo_date "============================= end ================================="
 echo XU6J03M6
 exit "$KS_CODE"
}
ks_operation_result(){
 [ "$KS_HAVE_LOCK" = 1 ] || return 0
 KS_CODE=$(cat "$KS_STATUS_FILE" 2>/dev/null)
 case "$KS_CODE" in ''|*[!0-9]*) KS_CODE=1;; esac
 exit "$KS_CODE"
}
