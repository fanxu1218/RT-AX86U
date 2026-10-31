#!/usr/bin/env python3
import json
from pathlib import Path
root=Path(__file__).resolve().parent.parent
lines=(root/'build/hooks_trace.log').read_text().splitlines()
conf=(root/'build/hooks_dnsmasq.conf').read_text()
def index(prefix):return next(i for i,s in enumerate(lines) if s.startswith(prefix))
def count(prefix):return sum(s.startswith(prefix) for s in lines)
checks={
 'httpd_launcher_keeps_readonly_vendor_path_arguments_exit_and_recovery':json.loads((root/'build/httpd_launcher_forward.json').read_text())=={'args':['httpd','-s','-p','34443'],'preload':'/usr/lib/localmod/httpd_bridge.so'} and json.loads((root/'build/httpd_launcher_disabled.json').read_text())=={'args':['httpd','-s','-p','34443'],'preload':''},
 'rc_launcher_preserves_arguments_and_vendor_exit':json.loads((root/'build/launcher_forward.json').read_text())=={'args':['hotplug','usb','value with space;literal'],'preload':'/usr/lib/localmod/rc_bridge.so'},
 'rc_launcher_recovery_and_skipd_compatibility':json.loads((root/'build/launcher_disabled.json').read_text())=={'args':['hotplug','usb','value with space;literal'],'preload':''} and count('BOOTSTRAP skipd-restart')==1,
 'vendor_nvram_shared_buffer_is_not_clobbered':count('WORK nvram-buffer-preserved')==1,
 'uu_style_vendor_eval_arguments_environment_and_return_preserved':count('VENDOR uu-download-contract preserved')==count('VENDOR uu-monitor-contract preserved')==count('WORK uu-vendor-commands-preserved')==1,
 'init_hook_after_mount_and_prepare':index('VENDOR mount /jffs')<index('BOOTSTRAP prepare')<index('USER init-start'),
 'service_before_after_and_multi_command':all(index('USER service-event '+verb+' '+name)<index('WORK '+verb+'_'+name)<index('USER service-event-end '+verb+' '+name) for verb,name in [('restart','httpd'),('start','dnsmasq')]),
 'wan_connected_once_per_unit':count('USER wan-event 0 connected')==count('USER wan-event 1 connected')==1,
 'fork_does_not_replay_parent_wan':count('USER wan-event 0 connecting')==1,
 'legacy_user_hook_and_center_deduplicated':count('CENTER S start')==3,
 'all_vendor_wan_states_mapped':all(count('USER wan-event 3 '+state)==1 for state in ['init','connecting','connected','disconnected','stopped','disabled','stopping']),
 'mount_arguments_and_order':index('USER pre-mount /dev/sda1 ext4')<index('VENDOR mount /tmp/mnt/USB with space')<index('USER post-mount /tmp/mnt/USB with space'),
 'post_mount_finishes_before_unmount':index('CENTER M /tmp/mnt/USB with space')<index('USER unmount /tmp/mnt/USB with space')<index('VENDOR umount /tmp/mnt/USB with space'),
 'center_mount_paths_remain_one_argument':count('ARGC M 1 </tmp/mnt/USB with space>')==count('ARGC U 1 </tmp/mnt/USB with space>')==1,
 'unmount_retry_runs_hook_once':count('USER unmount ')==count('CENTER U ')==1 and count('VENDOR umount ')==2,
 'bind_and_remount_do_not_emit_storage_hooks':not any(s.startswith('USER ') and ('/tmp/mnt/remount' in s or '/tmp/mnt/bind' in s) for s in lines),
 'disabled_hooks_and_exact_nvram_keys':not any('USER' in s and '/tmp/mnt/disabled' in s for s in lines) and count('USER wan-event 2 ')==0 and count('USER wan-event 0 connected')==1,
 'services_stop_before_shutdown_and_restart_start':index('USER services-stop')<index('CENTER T')<index('BOOTSTRAP stop') and count('USER services-start')==count('CENTER V')==2,
 'halt_also_stops_services':count('USER services-stop')==count('CENTER T')==count('BOOTSTRAP stop')==2,
 'dns_config_and_postconf_before_daemon':conf.count('custom-option=1')==1 and conf.count('conf-dir=/jffs/configs/dnsmasq.d')==1 and count('POSTCONF /etc/dnsmasq.conf')==count('VENDOR eval dnsmasq')==2 and index('POSTCONF')<index('VENDOR eval dnsmasq'),
 'timeouts_and_nested_event_guard':'PASS hook timeout kills descendants' in (root/'build/hooks_test_run.log').read_text(),
}
report={'status':'PASS' if all(checks.values()) else 'FAIL','boundary':'Actual ARM32 rc adapter and dispatcher; vendor NVRAM/mount/service/signal operations are fixtures, not hardware execution','checks':checks}
(root/'output/hooks_tests.json').write_text(json.dumps(report,indent=2)+'\n')
for name,ok in checks.items():print(('PASS' if ok else 'FAIL'),name)
assert all(checks.values())
