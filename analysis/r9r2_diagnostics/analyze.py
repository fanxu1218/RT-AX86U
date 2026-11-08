#!/usr/bin/env python3
"""Review diagnostic observations; deliberate faults never become stability passes."""
import argparse,hashlib,json,re,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def summary(values):
 return dict(count=len(values),minimum=min(values),median=statistics.median(values),maximum=max(values)) if values else None
def gc_parse(line):
 m=re.search(r'^gc (\d+) @([\d.]+)s.*? ([\d.]+)->([\d.]+)->([\d.]+) MB, ([\d.]+) MB goal',line)
 if not m:return None
 n,elapsed,before,after,live,goal=m.groups()
 return dict(number=int(n),process_elapsed_seconds=float(elapsed),heap_before_trace_mb=float(before),heap_after_trace_mb=float(after),live_heap_trace_mb=float(live),goal_trace_mb=float(goal),runtime_forced='(forced)' in line,raw=line)
def stages_parse(text):
 out={}
 for l in text.splitlines():
  m=re.match(r'([\d.]+) pid=(\d+) stage=([a-z_]+)',l)
  if m:out.setdefault(m[3],[]).append(float(m[1]))
 return out
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--mode',choices=['preflight','cycles'],default='preflight');a=ap.parse_args()
 p=ROOT/f'output/r9r2_diagnostic_{a.mode}_tests.json';r=json.loads(p.read_text());x=r['result'];assert r['status']=='LOCAL_ATTRIBUTION_DIAGNOSTIC_COMPLETE'
 assert sha(ROOT/r['candidate_image'])==r['candidate_sha256'] and sha(ROOT/f'output/r9r2_diagnostic_{a.mode}.log')==r['log_sha256']
 for n,h in r['source_sha256'].items():assert sha(ROOT/n)==h,n
 assert r['vm']['host_export_readonly'] and r['vm']['guest_network_devices']==0 and r['vm']['sealed_inputs_verified_before_and_after']
 assert x['no_thp_control_same_pid'] and x['no_thp_control_binary_matches']
 assert all(s['no_thp_control']['process']['THP_enabled']=='0' and s['no_thp_control']['anon_huge_pages_kib']==0 for s in x['samples'])
 assert x['same_memory_pid'] and x['data_preserved'] and x['runtime_script_restored'] and x['background_load_errors']==[]
 samples=x['samples'];assert samples and len({(s['process']['pid'],s['process']['start_ticks']) for s in samples})==1
 assert all(s['process']['executable'].endswith('/ddnsgo') and 'qemu' not in s['process']['executable'] for s in samples)
 assert all(s['coexist_processes'][k]['pid']==v for s in samples for k,v in x['pids'].items())
 assert x['duration_seconds']>=x['requested_memory_seconds']
 gc=[g for l in x['runtime_lines'] if (g:=gc_parse(l))]
 boundaries=[]
 for s in x['phase_boundaries']:
  g=gc_parse(s.get('latest_gc',''))
  boundaries.append(dict(stage=s['stage'],role=s['role'],elapsed_seconds=s['elapsed_seconds'],rss_kib=s['smaps_rss_kib'],anonymous_kib=s['anonymous_kib'],private_dirty_kib=s['private_dirty_kib'],huge_kib=s['anon_huge_pages_kib'],gc_count=s['gc_count'],latest_gc=g,threads=s['process']['Threads'],fds=s['process']['fds']))
 control_gc=[g for l in x['no_thp_control_runtime_lines'] if (g:=gc_parse(l))]
 groups={};observations=[]
 for case in x['latency_cases']:
  k=(case['kind'],case['method']);groups.setdefault(k,[]).append(case)
  completed=x['completed_script_stages'].get(str(case['id']),case['script_stages']);st=stages_parse(completed);span=st.get('after_base',[None])[0];start=st.get('before_base',[None])[0]
  observations.append(dict(id=case['id'],kind=case['kind'],method=case['method'],valid=case['valid'],code=case['code'],elapsed_seconds=case['elapsed_seconds'],error=case['error'],script_base_seconds=span-start if span is not None and start is not None else None,callback_ids=re.findall(r'stage=before_callback callback_id=(\d+)',completed),script_invocations=len(st.get('before_base',[])),controlled_pause_seconds=case['controlled_httpd_pause_seconds']))
 timing=[]
 for (kind,method),cases in sorted(groups.items()):
  values=[c['elapsed_seconds'] for c in cases];tls=[c['timings']['tls_done']-c['timings'].get('tls_start',0) for c in cases if 'tls_done' in c['timings']]
  base=[o['script_base_seconds'] for o in observations if o['kind']==kind and o['method']==method and o['script_base_seconds'] is not None]
  timing.append(dict(kind=kind,method=method,valid=sum(c['valid'] for c in cases),errors=sum(not c['valid'] for c in cases),total_seconds=summary(values),tls_seconds=summary(tls),script_base_seconds=summary(base)))
 expected=[o for o in observations if o['controlled_pause_seconds']>0];natural=[o for o in observations if o['controlled_pause_seconds']==0];unexpected=[o for o in natural if not o['valid']]
 assert all(all(v==str(o['id']) for v in o['callback_ids']) for o in observations)
 assert all(o['script_invocations']<=1 for o in observations),'A single RPC executed more than once'
 quiet=[b for b in boundaries if b['stage'].startswith('idle_') or b['role']=='final_idle_end']
 load=[b for b in boundaries if b['stage'].startswith('load_')]
 if a.mode=='cycles':
  assert len(quiet)==7 and len(load)==6 and len(gc)>=12 and len(control_gc)>=12
  assert len(samples)>=180 and all(x['page_counts'].get(f'load_{i}',0)>=100 for i in range(1,7))
 else:assert len(quiet)==2 and len(load)==1
 quiet_control=[]
 for b in quiet:
  s=next(s for s in samples if s['stage']==b['stage'] and s['role']==b['role']);c=s['no_thp_control'];g=gc_parse(c.get('latest_gc',''))
  quiet_control.append(dict(stage=b['stage'],elapsed_seconds=b['elapsed_seconds'],rss_kib=c['smaps_rss_kib'],anonymous_kib=c['anonymous_kib'],huge_kib=c['anon_huge_pages_kib'],gc_count=c['gc_count'],latest_gc=g,rollup=c['rollup'],default_minus_control_rss_kib=s['smaps_rss_kib']-c['smaps_rss_kib']))
 quiet_delta=[b['rss_kib']-aa['rss_kib'] for aa,b in zip(quiet,quiet[1:])]
 mapping_changes=[];first,last=quiet[0],quiet[-1]
 first_sample=next(s for s in samples if s['stage']==first['stage'] and s['role']==first['role']);last_sample=samples[-1]
 for k in sorted(set(first_sample['maps'])|set(last_sample['maps'])):
  aa=first_sample['maps'].get(k,{});b=last_sample['maps'].get(k,{})
  mapping_changes.append(dict(group=k,first_rss_kib=aa.get('rss_kib',0),final_rss_kib=b.get('rss_kib',0),rss_delta_kib=b.get('rss_kib',0)-aa.get('rss_kib',0),private_dirty_delta_kib=b.get('private_dirty_kib',0)-aa.get('private_dirty_kib',0)))
 report=dict(status='LOCAL_ATTRIBUTION_REVIEW_COMPLETE',mode=a.mode,candidate_sha256=r['candidate_sha256'],same_pid=x['memory_pid'],duration_seconds=x['duration_seconds'],normal_status_queries=x['normal_status_queries'],page_requests=x['target_page_requests'],page_counts=x['page_counts'],gc_cycles=len(gc),gc_live_trace_mb_values=sorted(set(g['live_heap_trace_mb'] for g in gc)),runtime_forced_gc_count=sum(g['runtime_forced'] for g in gc),gc=gc,no_thp_control_gc=control_gc,no_thp_control_gc_live_trace_mb_values=sorted(set(g['live_heap_trace_mb'] for g in control_gc)),no_thp_control_quiet_boundaries=quiet_control,no_thp_control_page_counts=x['no_thp_control_page_counts'],no_thp_control_final_minus_first_idle_rss_kib=quiet_control[-1]['rss_kib']-quiet_control[0]['rss_kib'],quiet_boundaries=quiet,load_boundaries=load,quiet_rss_deltas_kib=quiet_delta,final_minus_first_idle_rss_kib=quiet[-1]['rss_kib']-quiet[0]['rss_kib'],mapping_changes_after_first_idle=mapping_changes,timing_groups=timing,latency_observations=observations,natural_latency_failures=unexpected,controlled_fault_observations=expected,pprof_available=x['heap_profile_probe']['available'],resource_ranges={k:summary([s[k] for s in samples]) for k in ['smaps_rss_kib','private_dirty_kib','anonymous_kib','anon_huge_pages_kib','swap_kib']},fd_range=summary([s['process']['fds'] for s in samples]),thread_values=sorted(set(s['process']['Threads'] for s in samples)),source_sha256={str(p.relative_to(ROOT)):sha(p),'analysis/r9r2_diagnostics/analyze.py':sha(Path(__file__).resolve())},limits=['Deliberate SIGSTOP is an attribution control, not reproduction of the unexplained natural timeout','No latency success threshold turns failure observations into a stability pass; requests are not replayed','GC trace labels have coarse MB precision; RSS is resident mappings, not retained application objects','Target DDNS-Go is native ARM32 in the system guest; only the labelled HTTPd calibration uses QEMU-user','Repeated quiet baselines bound observed growth only; no multiday or real-device proof'])
 (ROOT/f'output/r9r2_diagnostic_{a.mode}_review.json').write_text(json.dumps(report,indent=2)+'\n')
 print('Reviewed',a.mode,'GC',len(gc),'natural latency failures',len(unexpected),'quiet RSS',[q['rss_kib'] for q in quiet],'live trace MB',report['gc_live_trace_mb_values'])
 print('Latency groups',json.dumps(timing,separators=(',',':')))
if __name__=='__main__':main()
