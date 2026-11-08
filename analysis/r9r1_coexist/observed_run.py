#!/usr/bin/env python3
"""Run the bound coexistence suite using full-system ARM32 HTTPd execution."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
original=root/'analysis/r9r1_coexist/check.py'
s=original.read_text()
s=s.replace("source+=['analysis/r9r1_coexist/tls_trace.c','sources/localmod/httpd_bridge.c']", "source+=['analysis/r9r1_coexist/tls_trace.c','sources/localmod/httpd_bridge.c','analysis/r9r1_coexist/native_run.py','analysis/r9r1_coexist/observed_run.py']")
native_transform="""
  if n=='build/native_runtime_client.go':
   assert 'program := "/usr/bin/qemu-arm"' in s
   s=s.replace('program := "/usr/bin/qemu-arm"','program := "/usr/libexec/localmod/httpd"')
   old='argv := []string{"-L", nrQEMURoot(), "-E", "LD_PRELOAD=" + preload, "/usr/libexec/localmod/httpd", "-s", "-p", "34443"}'
   assert old in s;s=s.replace(old,'argv := []string{"-s", "-p", "34443"}')
   assert 'cmd.Dir = "/www"' in s;s=s.replace('cmd.Dir = "/www"','cmd.Env = append(os.Environ(), "LD_PRELOAD="+preload)\\n\\tcmd.Dir = "/www"')
   changes.append('Full Cortex-A53 system native ARM32 kernel compatibility executes original HTTPd directly; same LD_PRELOAD and TLS library')
"""
native_transform+='\n  if n==\'analysis/r9r1_coexist/workload.go\':\n   s=s.replace(\'"os"\',\'"os"\\n\\t"os/exec"\',1)\n   key=\'func (c *coexistRun) rpc(method, action string) string {\'\n   replacement=key+\'\\n defer func(){if p:=recover();p!=nil{b,_:=exec.Command("/bin/ps","w").CombinedOutput();fmt.Printf("LIVE_RPC_FAILURE method=%s action=%s id=%d\\\\n%s\\\\n",method,action,c.x.id,b);panic(p)}}()\\n\'\n   assert s.count(key)==1;s=s.replace(key,replacement,1)\n   changes.append(\'Capture live process state on RPC failure before cleanup; normal path and10s deadline unchanged\')\n'
s=s.replace('  p=dest/Path(n).name;p.write_text(s);',native_transform+'  p=dest/Path(n).name;p.write_text(s);')

s=s.replace("label='probe' if a.probe else ('smoke' if a.smoke else '60m')", "label='native_probe' if a.probe else ('native_smoke' if a.smoke else '60m')")
s=s.replace("Path(f'output/{prefix}_probe_tests.json')", "Path(f'output/{prefix}_native_probe_tests.json')")
s=s.replace("source_overlay_used=a.bridge_overlay,result=r", "httpd_execution='native ARM32 through full Cortex-A53 kernel compatibility; no QEMU-user',source_overlay_used=a.bridge_overlay,result=r")
s=s.replace("report=dict(maintenance_windows=windows", "report=dict(httpd_execution='native ARM32 through full Cortex-A53 kernel compatibility; no QEMU-user',maintenance_windows=windows")
exec(compile(s,str(original)+'[owned-native-execution-transform]','exec'),{'__file__':str(original),'__name__':'__main__'})
