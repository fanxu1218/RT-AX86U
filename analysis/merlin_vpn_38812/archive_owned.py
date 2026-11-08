#!/usr/bin/env python3
"""Archive and verify one terminal owned sealed job, then free only that copy."""
import argparse,hashlib,json,os,re,shutil,stat,subprocess,sys,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'build'))
from sealed_vm import inventory,encoded
def main():
 ap=argparse.ArgumentParser();ap.add_argument('receipt');args=ap.parse_args()
 receipt=ROOT/args.receipt
 assert receipt.parent==ROOT/'output' and re.fullmatch(r'merlin38812_[\w.-]+\.log\.vm\.json',receipt.name)
 r=json.loads(receipt.read_text());p=ROOT/r['workspace_path'];job=p.parent
 assert p.name=='workspace' and job.parent==ROOT/'build/casefs/sealed-private' and re.fullmatch(r'job-[a-f0-9]{24}',job.name)
 assert r['preserved_after_failure'] and r['host_export_readonly'] and r['guest_network_devices']==0
 owner=json.loads((job/'owner.json').read_text());assert owner['job']==job.name and owner['phase']==r['phase'] and r['phase'] in {'candidate-merlin-components','candidate-merlin-system','candidate-fancyss','native-hnd-upgrade','native-hnd-fresh'}
 active='\n'.join(l for l in subprocess.check_output(['ps','-axo','command'],text=True).splitlines() if 'LinuxBuilder' in l)
 assert job.name not in active
 expected=json.loads((job/'manifest.json').read_text());actual=inventory(p)
 if r.get('state_disk_attached'):
  key='build/interrupt-private/state.img';state=p/key;s=state.lstat()
  assert expected[key]==dict(type='owned-state-disk',bytes=96*1024*1024,mode=0o600)
  assert stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o600 and s.st_size==96*1024*1024
  actual[key]=expected[key]
 assert actual==expected
 assert hashlib.sha256(encoded(expected)).hexdigest()==r['sealed_manifest_sha256']
 before=inventory(job);target=ROOT/'build'/('uu-preview-archive-'+job.name+'.tar.gz');assert not target.exists()
 with tarfile.open(target,'w:gz',dereference=False,compresslevel=1) as t:t.add(job,arcname=job.name)
 target.chmod(0o600)
 with tarfile.open(target,'r:gz') as t:
  for n,row in before.items():
   m=t.getmember(job.name+'/'+n);assert m.mode==row['mode']
   if row['type']=='file':assert hashlib.sha256(t.extractfile(m).read()).hexdigest()==row['sha256']
   elif row['type']=='link':assert m.issym() and m.linkname==row['target']
   else:assert m.isdir()
 assert inventory(job)==before
 target.with_suffix('.manifest.json').write_text(json.dumps(before,sort_keys=True))
 f=ROOT/'output/merlin38812_preview_archives.json';rows=json.loads(f.read_text())
 rows.append(dict(source=str(job.relative_to(ROOT)),receipt=args.receipt,archive=str(target.relative_to(ROOT)),sha256=hashlib.sha256(target.read_bytes()).hexdigest(),entries=len(before),verified=True))
 f.write_text(json.dumps(rows,indent=2)+'\n');shutil.rmtree(job)
 print('ARCHIVED_VERIFIED_TERMINAL_JOB',job.name)
if __name__=='__main__':main()
