#!/usr/bin/env python3
"""Apply exact, reviewable patches to the pinned KoolCenter online script."""

def patch_online_installer(text):
    def replace(old, new, count=1):
        nonlocal text
        assert text.count(old) == count, old[:100]
        text = text.replace(old, new)

    text = text.replace('--no-check-certificate ', '')
    replace('source /koolshare/scripts/base.sh\neval $(dbus export softcenter_installing_)',
            'source /koolshare/scripts/base.sh\n'
            'LOG_FILE=/tmp/upload/soft_install_log.txt\n'
            '. /usr/libexec/localmod/installer-guard.sh\n'
            'ks_operation_begin "$1" "${2:-install}" || exit 1\n'
            'eval $(dbus export softcenter_installing_)\n'
            'ks_operation_validate "$1" || exit 1')
    start = text.index('quit_ks_install(){')
    end = text.index('jffs_space(){', start)
    text = text[:start] + 'quit_ks_install(){ ks_finish "${1:-1}"; }\n\n' + \
           'quit_ks_uninstall(){ ks_finish "${1:-1}"; }\n\n' + text[end:]
    replace('\ninstall_ks_module() {', '\ninstall_ks_module() {\n'
            ' if [ "$softcenter_installing_todo" = softcenter ] || [ "$softcenter_installing_todo" = koolcenter ]; then\n'
            '  echo_date "此试验官改的软件中心核心由固件构建维护；请通过固件升级更新核心。普通插件可单独安装。"\n'
            '  quit_ks_install\n fi')
    start = text.index('\t# 2. detect ks_app_install.sh process')
    end = text.index('\t# 3. 检查上次插件安装', start)
    text = text[:start] + '\t# The operation lock was acquired before reading the shared request fields.\n\n' + text[end:]
    start = text.index('\t# 6. 下载准备')
    end = text.index('\techo_date "插件【${softcenter_installing_title}】将会被安装', start)
    text = text[:start] + '\tks_scope_prepare || quit_ks_install\n' + text[end:]
    replace('wget -t 2 -T 20 --dns-timeout=15 ${TAR_URL}',
            'wget -t 2 -T 20 --dns-timeout=15 -O "$KS_DOWNLOAD" "$TAR_URL"')
    replace('md5sum /tmp/${FNAME}', 'md5sum "$KS_DOWNLOAD"')
    replace('tar -zxf ${FNAME}',
            'ks_archive_valid || { echo_date "插件压缩包目录不匹配或解压失败！"; quit_ks_install; }\n'
            '\ttar -zxf "$KS_DOWNLOAD" -C /tmp')
    replace('\t# 检查前尝试删掉 uu.tar.gz uu.tar.gz.md5，这并无其它影响，因为uu还会下载下来的，但是对小jffs分区如RT-AX56U_V2、RT-AX57比较友好\n'
            '\tfind /jffs/ -name "uu.tar.gz*" -type f | xargs rm -rf',
            '\t# UU archives belong to UU; ordinary plugin operations must preserve them.')
    replace('\t\t\texit_tar_install 1', '\t\t\tquit_ks_install')
    replace('\t# 14. 复制uninstall.sh', '\tks_checkpoint || quit_ks_install\n'
            '\tks_uninstaller_backup || quit_ks_install\n\n\t# 14. 复制uninstall.sh')
    replace('\t\trm -rf /koolshare/scripts/uninstall_${softcenter_installing_todo}.sh',
            '\t\tks_uninstaller_restore || echo_date "恢复旧卸载脚本失败，请保留日志。"')
    replace('\t\techo_date "退出本次插件安装！"\n\t\tquit_ks_install\n\tfi\n\n\tks_scope_prepare',
            '\t\techo_date "退出本次插件安装！"\n\t\tquit_ks_install 0\n\tfi\n\n\tks_scope_prepare')
    replace('\techo_date "安装完毕！"\n\tquit_ks_install', '\techo_date "安装完毕！"\n\tquit_ks_install 0')
    replace(' -o "${softcenter_installing_todo}" == "softcenter" ]; then',
            ' -o "${softcenter_installing_todo}" == "softcenter" -o "${softcenter_installing_todo}" == "koolcenter" ]; then')
    replace('if [ -f /koolshare/scripts/${softcenter_installing_todo}_uninstall.sh]; then',
            'if [ -f "/koolshare/scripts/${softcenter_installing_todo}_uninstall.sh" ]; then')
    replace('start-stop-daemon -S -q -x /koolshare/scripts/${softcenter_installing_todo}_uninstall.sh 2>&1',
            'start-stop-daemon -S -q -x "/koolshare/scripts/${softcenter_installing_todo}_uninstall.sh" 2>&1 || {\n'
            '\t\techo_date "插件卸载脚本失败，保留登记和配置。"; quit_ks_uninstall; }')
    start = text.index(' \t\tstart-stop-daemon -S -q -x /koolshare/scripts/uninstall_${softcenter_installing_todo}.sh 2>&1')
    end = text.index('\telse\n\t\techo_date "没有找到插件', start)
    text = text[:start] + '\t\tstart-stop-daemon -S -q -x "/koolshare/scripts/uninstall_${softcenter_installing_todo}.sh" 2>&1 || {\n' + \
           '\t\t echo_date "插件卸载脚本失败，保留登记和配置。"; quit_ks_uninstall; }\n' + text[end:]
    replace('rm -rf /koolshare/init.d/*${softcenter_installing_todo}*',
            'rm -f /koolshare/init.d/[SVTNMU][0-9][0-9]"${softcenter_installing_todo}".sh')
    replace('rm -rf /koolshare/scripts/${softcenter_installing_todo}*.sh',
            'rm -f /koolshare/scripts/"${softcenter_installing_todo}".sh /koolshare/scripts/"${softcenter_installing_todo}"_*.sh /koolshare/scripts/"uninstall_${softcenter_installing_todo}.sh"')
    replace('local txt=$(dbus list ${softcenter_installing_todo})', 'local txt=$(dbus list "${softcenter_installing_todo}_")')
    replace('\techo_date "卸载成功！"\n\tquit_ks_uninstall', '\techo_date "卸载成功！"\n\tquit_ks_uninstall 0')
    assert text.rstrip().endswith('esac')
    return text.rstrip() + '\nks_operation_result\n'
