#!/usr/bin/env python3
"""Native VPN configuration writers, user postconf and non-PID1 controls.

This does not start tunnels or emulate the target's PID1/kernel. Notification
signals are captured by an owned fixture instead of reaching Alpine's init.
"""
import builtins,json,sys,types
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
import check_native_restore as shared
def run_derived(code,namespace):
 source=(ROOT/'build/merlin38813-native-restore-probe/derived_check.py').read_text()
 def change(old,new):
  nonlocal source
  assert source.count(old)==1,(old,source.count(old));source=source.replace(old,new)
 change("'restore_probe.go','restore_kernel_fixture.c','check_native_restore.py'","'vpn_generate.go','vpn_generate_probe.c','vpn_notify_fixture.c','vendor/openvpn_config.h','check_native_restore.py','check_native_vpn.py'")
 change("'analysis/merlin_vpn_38813/restore_probe.go']:","'analysis/merlin_vpn_38813/vpn_generate.go']:")
 source=source.replace('build/merlin38813-native-restore-probe','build/merlin38813-native-vpn-generation').replace('merlin38813_restore_probe','merlin38813_vpn_generation').replace('RESTORE_PROBE_RESULT','VPN_GENERATE_RESULT').replace('LOCAL_NATIVE_RESTORE_OBSERVATIONS_RECORDED','LOCAL_NATIVE_VPN_GENERATION_PASS')
 change("str(HERE/'native_hook_probe.c')","str(HERE/'vpn_generate_probe.c')")
 change("'-lshared','-lnvram','-Wl,--allow-shlib-undefined'","'-lshared','-lnvram','-ldl','-Wl,--allow-shlib-undefined'")
 source=source.replace('restore_kernel_fixture.so','vpn_notify_fixture.so').replace("str(HERE/'restore_kernel_fixture.c')","str(HERE/'vpn_notify_fixture.c')")
 change("'Actual candidate restore adapter; declared test-only exec boundary applies output with Alpine legacy xtables; native 4.1 kernel/backend ABI, physical router, actual UU account/game acceleration remain unverified'","'Actual candidate native libovpn/libshared generate synthetic files and run user postconf; non-PID1 start/stop notifications are captured, not delivered to init. No tunnels, WAN/providers, kernel routes, physical router or actual UU acceleration tested'")
 marker="assert len(rows)==1"
 change(marker,marker+";assert len(rows[0]['checks'])==8 and rows[0]['configurations']==7 and rows[0]['service_notifications']==14")
 folder=ROOT/'build/merlin38813-native-vpn-generation';folder.mkdir(exist_ok=True);(folder/'derived_check.py').write_text(source)
 builtins.exec(compile(source,str(folder/'derived_check.py'),'exec'),namespace)
if __name__=='__main__':
 shared.builtins=types.SimpleNamespace(exec=run_derived)
 shared.controller.exec=shared.run_derived
 shared.controller.main()
