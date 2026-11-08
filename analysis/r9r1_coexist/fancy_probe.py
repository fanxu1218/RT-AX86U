#!/usr/bin/env python3
"""Generate a metadata-only Fancyss latency probe without changing the bound soak."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
original=root/'analysis/r9r1_coexist/check.py'
s=original.read_text()
s=s.replace("source+=['analysis/r9r1_coexist/tls_trace.c','sources/localmod/httpd_bridge.c']", "source+=['analysis/r9r1_coexist/tls_trace.c','sources/localmod/httpd_bridge.c','analysis/r9r1_coexist/fancy_probe.go','analysis/r9r1_coexist/fancy_probe.py']")
s=s.replace("p=dest/Path(n).name;p.write_text(s);files.append(str(p));transforms[n]=dict(sha256=sha(p),changes=changes)", "\n  if n=='analysis/r9r1_coexist/workload.go':\n   assert s.count('c.handshakeProbe()')==1;s=s.replace('c.handshakeProbe()','c.fancyProbe()');changes.append('Owned focused Fancyss latency diagnostics instead of handshake probe')\n  p=dest/Path(n).name;p.write_text(s);files.append(str(p));transforms[n]=dict(sha256=sha(p),changes=changes)")
s=s.replace("label='probe' if a.probe", "label='fancy_latency' if a.probe")
start=s.index('  r=rows[0];cases=')
end=s.index(";return",start)+len(';return')
s=s[:start]+"  r=rows[0];assert len(r['cases'])==24 and r['data_preserved']\n  Path(f'output/{prefix}_fancy_latency_tests.json').write_text(json.dumps(dict(status='LOCAL_FANCYSS_LATENCY_DIAGNOSTIC_COMPLETE',candidate_sha256=v['sha256'],result=r,source_sha256=before,generated_test_source=transforms,baseline_preserved_sha256=baseline,log_sha256=sha(log),vm=receipt),indent=2)+'\\n');return"+s[end:]
s=s.replace("l.removeprefix('COEXIST_PROBE_RESULT ')","l.removeprefix('FANCY_LATENCY_RESULT ')").replace("l.startswith('COEXIST_PROBE_RESULT ')","l.startswith('FANCY_LATENCY_RESULT ')")
sys.argv=[str(original),'--probe']
exec(compile(s,str(original)+'[owned-latency-transform]','exec'),{'__file__':str(original),'__name__':'__main__'})
