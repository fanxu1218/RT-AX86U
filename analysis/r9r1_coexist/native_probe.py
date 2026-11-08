#!/usr/bin/env python3
"""Generate a metadata-only Fancyss latency probe without changing the bound soak."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
original=root/'analysis/r9r1_coexist/check.py'
s=original.read_text()
s=s.replace("source+=['analysis/r9r1_coexist/tls_trace.c','sources/localmod/httpd_bridge.c']", "source+=['analysis/r9r1_coexist/tls_trace.c','sources/localmod/httpd_bridge.c','analysis/r9r1_coexist/fancy_probe.go','analysis/r9r1_coexist/fancy_probe.py','analysis/r9r1_coexist/native_probe.py']")
s=s.replace("p=dest/Path(n).name;p.write_text(s);files.append(str(p));transforms[n]=dict(sha256=sha(p),changes=changes)", "\n  if n=='analysis/r9r1_coexist/workload.go':\n   assert s.count('c.handshakeProbe()')==1;s=s.replace('c.handshakeProbe()','c.fancyProbe()');changes.append('Owned focused Fancyss latency diagnostics instead of handshake probe')\n  p=dest/Path(n).name;p.write_text(s);files.append(str(p));transforms[n]=dict(sha256=sha(p),changes=changes)")
native_transform="""
  if n=='build/native_runtime_client.go':
   assert 'program := "/usr/bin/qemu-arm"' in s
   s=s.replace('program := "/usr/bin/qemu-arm"','program := "/usr/libexec/localmod/httpd"')
   old='argv := []string{"-L", nrQEMURoot(), "-E", "LD_PRELOAD=" + preload, "/usr/libexec/localmod/httpd", "-s", "-p", "34443"}'
   assert old in s;s=s.replace(old,'argv := []string{"-s", "-p", "34443"}')
   assert 'cmd.Dir = "/www"' in s;s=s.replace('cmd.Dir = "/www"','cmd.Env = append(os.Environ(), "LD_PRELOAD="+preload)\\n\\tcmd.Dir = "/www"')
   changes.append('Full Cortex-A53 system native ARM32 kernel compatibility executes original HTTPd directly; same LD_PRELOAD and TLS library')
"""
s=s.replace('  p=dest/Path(n).name;p.write_text(s);',native_transform+'  p=dest/Path(n).name;p.write_text(s);')
s=s.replace("label='probe' if a.probe", "label='fancy_native_latency' if a.probe")
start=s.index('  r=rows[0];cases=')
end=s.index(";return",start)+len(';return')
s=s[:start]+"  r=rows[0];assert len(r['cases'])==24 and r['data_preserved']\n  Path(f'output/{prefix}_fancy_native_latency_tests.json').write_text(json.dumps(dict(status='LOCAL_FANCYSS_LATENCY_DIAGNOSTIC_COMPLETE',candidate_sha256=v['sha256'],result=r,source_sha256=before,generated_test_source=transforms,baseline_preserved_sha256=baseline,log_sha256=sha(log),vm=receipt),indent=2)+'\\n');return"+s[end:]
s=s.replace("l.removeprefix('COEXIST_PROBE_RESULT ')","l.removeprefix('FANCY_LATENCY_RESULT ')").replace("l.startswith('COEXIST_PROBE_RESULT ')","l.startswith('FANCY_LATENCY_RESULT ')")
sys.argv=[str(original),'--probe']
exec(compile(s,str(original)+'[owned-latency-transform]','exec'),{'__file__':str(original),'__name__':'__main__'})
