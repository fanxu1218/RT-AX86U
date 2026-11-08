#!/usr/bin/env python3
"""Save a reviewable development source snapshot without committing other work.

This includes current uncommitted device-profile dependencies. It does not
publish, select a release, or bundle firmware/real account/state-disk data.
"""
import gzip,hashlib,io,json,re,subprocess,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 candidate=json.loads((ROOT/'output/merlin38812_native_candidate_tests.json').read_text())
 assert sha(ROOT/candidate['image']['image'])==candidate['image']['sha256']
 revision=re.search(r'_native_(P[0-9]+)_',candidate['image']['image']).group(1)
 original=json.loads((ROOT/'output/merlin38812-native-P2-sources.tar.manifest.json').read_text())
 names=set(original['files'])
 for prefix in ['analysis/merlin_vpn_38812','build/devices']:
  for p in (ROOT/prefix).rglob('*'):
   if p.is_file() and not p.is_symlink() and p.suffix in {'.py','.c','.h','.go','.json','.txt','.sh'} and '__pycache__' not in p.parts:names.add(p.relative_to(ROOT).as_posix())
 evidence={}
 for suffix in ['native_candidate_tests','native_hooks_tests','candidate_runtime_tests','sync_aux_tests','persistence_tests','plugins_fancyss_tests','plugins_hnd_upgrade_tests','plugins_hnd_fresh_tests','restore_probe_tests','vpn_generation_tests','real_tunnel_tests','native_coexist_probe_tests','native_coexist_smoke_tests','native_coexist_60m_tests','local_gate']:
  p=ROOT/('output/merlin38812_'+suffix+'.json')
  if not p.exists():continue
  report=json.loads(p.read_text())
  bound=report.get('stage',{}).get('image',{}).get('sha256') or report.get('image',{}).get('sha256') or report.get('candidate',{}).get('sha256') or report.get('candidate_sha256')
  evidence[p.relative_to(ROOT).as_posix()]=dict(status=report['status'],sha256=sha(p),candidate_sha256=bound,matches_snapshot_candidate=bound==candidate['image']['sha256'])
  for name,expected in report.get('source_sha256',{}).items():
   assert sha(ROOT/name)==expected,('Source evidence no longer current',name,p.name)
   names.add(name)
 # Source/document inputs only; reject accidental binary or private state data.
 names={n for n in names if not n.startswith('output/')}
 files={}
 for n in sorted(names):
  p=ROOT/n;assert p.is_file() and not p.is_symlink(),n
  data=p.read_bytes();assert len(data)<=8*1024*1024 and b'\0' not in data,n
  files[n]=dict(bytes=len(data),sha256=sha(p),mode=p.stat().st_mode&0o777)
 head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
 state=json.loads((ROOT/'output/merlin38812_migration_state.json').read_text())
 meta=dict(status='DEVELOPMENT_SOURCE_SNAPSHOT_NOT_A_RELEASE',git_head=head,working_tree_snapshot=True,contains_uncommitted_device_profile_dependencies=True,candidate_sha256=candidate['image']['sha256'],full_upgrade_complete=False,local_validation_complete=state.get('local_validation_complete',False),firmware_or_upstream_monitor_binaries_included=False,evidence=evidence,remaining_contracts=state['remaining_contracts'],known_fancyss_gap=state.get('fancyss_native_coexistence'),files=files)
 target=ROOT/('output/merlin38812-native-'+revision+'-sources.tar.gz');assert not target.exists()
 with target.open('xb') as out,gzip.GzipFile(filename='',mode='wb',fileobj=out,mtime=0) as zipped,tarfile.open(fileobj=zipped,mode='w|') as archive:
  for n,r in files.items():
   info=tarfile.TarInfo(n);info.size=r['bytes'];info.mode=r['mode'];archive.addfile(info,io.BytesIO((ROOT/n).read_bytes()))
  data=(json.dumps(meta,indent=2)+'\n').encode();info=tarfile.TarInfo('SOURCE_SNAPSHOT.json');info.size=len(data);info.mode=0o644;archive.addfile(info,io.BytesIO(data))
 with tarfile.open(target,'r:gz') as archive:
  assert len(archive.getmembers())==len(files)+1
  for n,r in files.items():assert hashlib.sha256(archive.extractfile(n).read()).hexdigest()==r['sha256'] and sha(ROOT/n)==r['sha256']
 target.with_suffix('.manifest.json').write_text(json.dumps(meta,indent=2)+'\n')
 target.with_suffix(target.suffix+'.sha256').write_text(sha(target)+'  '+target.name+'\n')
 report=dict(status='LOCAL_DEVELOPMENT_SNAPSHOT_SAVED_NOT_RELEASED',archive=str(target.relative_to(ROOT)),bytes=target.stat().st_size,sha256=sha(target),files=len(files),git_head_at_snapshot=head,working_tree_snapshot=True,git_commit_created=False,github_push_owner='user',agent_pushed_or_published=False,full_upgrade_complete=False,local_validation_complete=state.get('local_validation_complete',False),candidate_sha256=candidate['image']['sha256'])
 (ROOT/'output/merlin38812_source_snapshot.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'],target.name,len(files))
if __name__=='__main__':main()
