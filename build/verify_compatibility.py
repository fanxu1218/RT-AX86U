#!/usr/bin/env python3
import json,re
from pathlib import Path
root=Path(__file__).resolve().parent.parent
restore=(root/'build/restore_tests_run.log').read_text()
center=(root/'build/center_tests_run.log').read_text()
trace=(root/'build/restore_hook_trace.log').read_text()
checks={
 'privileged_api_connection':'PASS privileged source port' in restore,
 'filter_replacement_has_no_observed_exposure':'PASS 24 live table replacements reject all' in restore,
 'noflush_guard_first':'PASS noflush rules keep private API guard first' in restore,
 'nonrouting_flush_preserves_policy_and_chain_definitions':'PASS non-routing flush preserves custom chains and private API isolation' in restore,
 'dry_run_and_errors_do_not_emit_events':all(x in restore for x in ['PASS test-only restore does not emit events','PASS malformed input and vendor failures preserve guard and emit no hooks']),
 'nat_filter_event_dispatch':'nat-start ' in trace and 'CENTER-N-start_nat' in trace and 'firewall-start ppp0' in trace,
 'restore_input_retained_and_recovery_supported':'PASS filename input and original rules retained' in restore and 'PASS recovery marker delegates original behavior' in restore,
 'database_commit_and_restart':'PASS immediate writes survive skipd service restarts' in center,
 'legacy_startup_link_archived':'PASS legacy asusrouter symlink archived without executing the replacement core' in center,
 'migration_conflicts_leave_active_core_intact':'PASS broken backup links rejected without changing the active old core' in center,
 'real_multipart_upload_through_adapter':'PASS multipart archive uploaded byte-for-byte through authenticated adapter and actual httpdb' in center,
 'install_and_callback_through_adapter':'PASS upload, install RPC and script callback traverse the authenticated adapter' in center,
 'custom_uninstall_through_adapter':'PASS actual uninstall RPC executes module_uninstall hook and removes registration and page' in center,
 'core_migration_preserves_user_state':'PASS initial center migration archives old plugins; managed-core upgrade preserves current plugins and user hooks' in center and 'PASS database value and exact user hook bytes survive managed-core upgrade' in center,
 'offline_install_through_real_httpdb_skipd':'PASS actual software-center API invokes offline installer and registers fixture plugin' in center,
 'installed_script_fields_and_callback':'PASS installed plugin script reads fields and returns via actual curl callback' in center,
 'wrong_platform_and_core_overwrite_rejected':'PASS wrong_platform not installed' in center and 'PASS softcenter core overwrite blocked' in center,
 'offline_cleanup_cannot_remove_runtime':'PASS offline cleanup preserves private runtime directory' in center,
 'recovery_marker_stops_backend':'PASS recovery marker stops the actual private API backend' in center,
}
probes=re.search(r'attempts (\d+)',restore)
report={'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'filter_restore_cycles':24,'nonrouting_flush_cycles':5,
 'unprivileged_connection_attempts':int(probes.group(1)) if probes else 0,
 'live_test_kernel':(root/'build/restore_kernel_version.txt').read_text().strip(),
 'live_xtables_helper':(root/'build/restore_helper_version.txt').read_text().strip(),
 'boundary':'ARM32 production adapters and real packaged httpdb/skipd/dbus; native Alpine curl, xtables and process-launch helper are used in the networkless ARM64 guest. Vendor rc hardware operations and login are fixtures. Stock kernel 4.1/xtables 1.4.12.2 still require device verification.'}
(root/'output/compatibility_tests.json').write_text(json.dumps(report,indent=2)+'\n')
for name,ok in checks.items():print(('PASS' if ok else 'FAIL'),name)
assert all(checks.values())
