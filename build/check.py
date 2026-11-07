#!/usr/bin/env python3
"""Unified quick CI, pinned dependency, and complete local release checks."""
import argparse,ast,hashlib,io,json,os,shutil,subprocess,tarfile,tempfile,time
from pathlib import Path
from release_config import ROOT,CONFIG
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def owned_sources():
 paths=subprocess.check_output(['git','ls-files','-co','--exclude-standard','--','sources/localmod','build','.github'],cwd=ROOT,text=True).splitlines()
 return {p:sha(ROOT/p) for p in sorted(set(paths)) if (ROOT/p).is_file() and Path(p).suffix in {'.c','.h','.go','.py','.sh','.asp','.swift','.json','.yml','.sha256','.txt','.mjs'}}
def run(*args):subprocess.run(args,cwd=ROOT,check=True)
def quick():
 paths=owned_sources()
 for p in paths:
  if p.endswith('.py'):ast.parse((ROOT/p).read_text(),filename=p)
  if p.endswith('.sh'):run('sh','-n',p)
  if p.endswith('.mjs'):run('node','--check',p)
 c=[str(p.relative_to(ROOT)) for p in sorted((ROOT/'sources/localmod').glob('*.c'))]
 zig=ROOT/'sources/zig-aarch64-macos-0.15.2/zig'
 cc=[str(zig),'cc','-target','arm-linux-gnueabi.2.26'] if zig.exists() else ['cc']
 with tempfile.TemporaryDirectory(prefix='localmod-compile-') as output:
  for p in c:run(*cc,'-O2','-c','-Werror=implicit-function-declaration',p,'-o',str(Path(output)/(Path(p).stem+'.o')))
 # Host-side boundary smoke checks need no router images or private fixtures.
 with tempfile.TemporaryDirectory(prefix='localmod-quick-') as name:
  t=Path(name);guard=t/'archive-guard';runner=t/'plugin-run'
  run('cc','-O2','-DGZIP_PATH="'+shutil.which('gzip')+'"','-o',str(guard),'sources/localmod/archive_guard.c')
  run('cc','-O2','-o',str(runner),'sources/localmod/plugin_run.c')
  for name,member,link,accepted in [('regular','probe/install.sh',None,True),('safe-link','probe/link','install.sh',True),('escape','probe/../escape',None,False),('unsafe-link','probe/link','../../outside',False)]:
   archive=t/(name+'.tar.gz')
   with tarfile.open(archive,'w:gz',format=tarfile.USTAR_FORMAT) as tar:
    h=tarfile.TarInfo('probe/install.sh');h.size=1;tar.addfile(h,io.BytesIO(b'x'))
    if member!='probe/install.sh':
     h=tarfile.TarInfo(member)
     if link:h.type=tarfile.SYMTYPE;h.linkname=link
     tar.addfile(h)
   result=subprocess.run([str(guard),str(archive),'probe'],capture_output=True)
   assert (result.returncode==0)==accepted,name
  before=time.monotonic();r=subprocess.run([str(runner),'1','-','0','sh','-c','sleep 10'],capture_output=True)
  elapsed=time.monotonic()-before
  assert r.returncode==124 and elapsed<4, dict(returncode=r.returncode,elapsed_seconds=elapsed,stderr=r.stderr.decode(errors='replace'))
 print('PASS quick syntax, ARM ABI (when Zig available), archive boundaries and owned timeout',flush=True)
def dependencies():
 lock=json.loads((ROOT/'build/dependencies.lock.json').read_text())
 for p,entry in lock['files'].items():
  f=ROOT/p;assert f.is_file() and f.stat().st_size==entry['bytes'] and sha(f)==entry['sha256'],p
 assert subprocess.check_output(['go','version'],text=True).strip()==lock['go_version']
 assert subprocess.check_output(['node','--version'],text=True).strip()==lock['node_version']
 print('PASS pinned dependencies',len(lock['files']),flush=True)
def finalize(inputs):
 receipt=json.loads((ROOT/'build/release_run_inputs.json').read_text())
 previous=receipt['source_sha256']
 changed={p for p in set(previous)|set(inputs) if previous.get(p)!=inputs.get(p)}
 assert changed<=set(receipt.get('allowed_source_changes',[])),('Changed inputs need full release rerun',changed)
 for p,digest in receipt.get('previous_reports',{}).items():assert sha(ROOT/p)==digest,p
 # Recompile every production object: a test-only readiness change may reuse
 # artifact-bound passed phases only if the shipped code is byte-identical.
 run('python3','build/build_candidate.py','--compile-only')
 stage=ROOT/'build/casefs/rootfs';back=ROOT/'build/casefs/roundtrip'
 pairs={'httpd_bridge.so':'usr/lib/localmod/httpd_bridge.so','rc_bridge.so':'usr/lib/localmod/rc_bridge.so',
        'httpd-launcher':'usr/sbin/httpd','init-launcher':'sbin/init','rc-launcher':'sbin/rc','iptables-restore-launcher':'usr/sbin/iptables-restore'}
 for name in ['localmod-event','plugin-txn','archive-guard','plugin-run','log-limit','localmod-status','miniupnp-compat']:pairs[name]='usr/libexec/localmod/'+name
 for p,target in pairs.items():assert (ROOT/'build'/p).read_bytes()==(stage/target).read_bytes()==(back/target).read_bytes(),p
 from prepare_merlin import PIN as MERLIN_PIN,verify as verify_merlin
 verify_merlin(stage);verify_merlin(back)
 for name,entry in MERLIN_PIN['programs'].items():
  assert (ROOT/('build/merlin-'+name+'-launcher')).read_bytes()==(back/entry['path']).read_bytes()
 for name in ['bootstrap.sh','dispatch.sh','installer-guard.sh','plugin-compat.sh','fancyss-packages.sha256']:
  assert (ROOT/'sources/localmod'/name).read_bytes()==(back/'usr/libexec/localmod'/name).read_bytes(),name
 assert (ROOT/'sources/localmod/offline-installer.sh').read_bytes()==(back/'rom/etc/koolshare/scripts/ks_tar_install.sh').read_bytes()
 from patch_online_installer import patch_online_installer
 from prepare_softcenter import prepare as prepare_softcenter,patch_frontend
 core,_=prepare_softcenter()
 assert patch_online_installer((core/'scripts/ks_app_install.sh').read_text())==(back/'rom/etc/koolshare/scripts/ks_app_install.sh').read_text()
 assert (back/'rom/etc/koolshare/.soft_ver').read_text().strip()==CONFIG['software_center_version']
 for name in ['webs/Module_Softcenter.asp','res/soft-v19/assets/index-DhXhkv_Y.js']:
  assert patch_frontend((core/name).read_text())==(back/'rom/etc/koolshare'/name).read_text(),name
 assert (ROOT/'sources/localmod/Module_Localmod.asp').read_text().replace('@REVISION@',CONFIG['variant']+'-'+CONFIG['revision'])==(back/'www/Module_Localmod.asp').read_text()
 from prepare_fancyss import prepare as prepare_fancyss,render_page as fancyss_page
 fancyss=prepare_fancyss()
 assert (ROOT/'sources/localmod/fancyss-packages.sha256').read_text()==''.join(p['adapted_sha256']+'  shadowsocks\n' for p in fancyss['packages'])
 assert fancyss_page(fancyss,CONFIG)==(back/'www/Module_FancyssLocalmod.asp').read_text()
 v=json.loads((ROOT/'output/verification.json').read_text());assert v['image']==CONFIG['image'] and sha(ROOT/v['image'])==v['sha256'] and all(v['checks'].values()) and not v['errors']
 reports={}
 for name in ['lifecycle_tests','online_plugin_tests','real_plugin_tests','fancyss_tests','softcenter_upgrade_tests','softcenter_frontend_tests','merlin_component_tests','history_tests','shard_tests','model_isolation_tests','https_stability_tests','interruption_tests','recovery_safety_tests','hardening_tests','tls_input_tests']:
  p=ROOT/('output/'+name+'.json');x=json.loads(p.read_text());assert x['candidate_sha256']==v['sha256'],name
  assert ('checks' not in x or all(x['checks'].values())) and (x['status']=='PASS' or x['status'].endswith('_PASS')),name
  reports[str(p.relative_to(ROOT))]=sha(p)
 for name in ['lifecycle_tests','online_plugin_tests']:
  x=json.loads((ROOT/('output/'+name+'.json')).read_text())
  jobs=x['private_model_job_receipts'];assert len(jobs)>=3
  for job in jobs:assert job['outcome']=='PASS' and job['immutable_inputs_verified'] and not job['checkout_exported'] and job['runner_sha256']==inputs['build/model_private.py']
 model=json.loads((ROOT/'output/model_isolation_tests.json').read_text())
 assert all(inputs[p]==digest for p,digest in model['source_sha256'].items())
 ui_path=ROOT/'output/softcenter_ui_mock_tests.json';ui=json.loads(ui_path.read_text())
 assert ui['status']=='LOCAL_BROWSER_MOCK_PASS' and all(ui['checks'].values())
 assert ui['frontend_asp_sha256']==sha(back/'rom/etc/koolshare/webs/Module_Softcenter.asp')
 reports[str(ui_path.relative_to(ROOT))]=sha(ui_path)
 p=ROOT/'output/base_migration_tests.json';base=json.loads(p.read_text())
 assert base['status']=='LOCAL_BASE_MIGRATION_AUDIT_PASS' and all(base['checks'].values()) and not base['errors']
 assert base['candidate_sha256']==sha(ROOT/CONFIG['vendor_image'])
 reports[str(p.relative_to(ROOT))]=sha(p)
 modified={'rom/etc/profile','sbin/init','sbin/rc','usr/sbin/httpd','usr/sbin/iptables-restore','www/state.js'} | {e['path'] for e in MERLIN_PIN['programs'].values()}
 added={'koolshare','rom/etc/localmod-core-id','rom/etc/localmod-release.json','rom/etc/localmod-merlin.json','rom/etc/localmod-merlin-notice.txt','usr/bin/dbus','usr/bin/skipd','usr/bin/jffsinit.sh','usr/bin/tee','usr/bin/xargs','usr/libexec','usr/sbin/helper.sh','www/Module_Localmod.asp','www/Module_FancyssLocalmod.asp'}
 prefixes=['rom/etc/koolshare','usr/lib/localmod','usr/libexec/localmod']
 changes=json.loads((ROOT/'build/changes.json').read_text())
 for row in changes:
  p=row['path'];assert (row['change']=='modified' and p in modified) or (row['change']=='added' and (p in added or any(p==q or p.startswith(q+'/') for q in prefixes))),('Unreviewed vendor change',row)
 assert owned_sources()==inputs
 return dict(previous_phase_reports_verified=receipt.get('previous_reports',{}),artifact_bound_reports=reports,compiled_production_matches_readback=True,change_allowlist_entries_verified=len(changes),test_only_source_changes=sorted(changed),test_only_source_change_reviews=receipt.get('test_only_source_change_reviews',{}),snapshot_origin=receipt.get('snapshot_origin','before full run'))
def main():
 ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['quick','dependencies','release','finalize']);a=ap.parse_args();os.chdir(ROOT)
 if a.mode=='dependencies':dependencies();return
 quick()
 if a.mode=='quick':return
 dependencies();inputs=owned_sources();resume={}
 if a.mode=='finalize':resume=finalize(inputs)
 else:
  (ROOT/'build/release_run_inputs.json').write_text(json.dumps(dict(schema=1,source_sha256=inputs,allowed_source_changes=[]),indent=2)+'\n')
  run(str(ROOT/'analysis/.venv/bin/python'),'build/base_migration.py','--image',CONFIG['vendor_image'])
  run('python3','build/build_candidate.py')
  run('python3','build/check_model_isolation.py')
  run('python3','build/check_hardening.py')
  run('python3','build/check_shards.py','--candidate')
  run('python3','build/check_tls_input.py','--candidate')
  resume=finalize(inputs)
 assert owned_sources()==inputs,'Sources changed during release validation; rerun required'
 v=json.loads((ROOT/'output/verification.json').read_text());assert v['image']==CONFIG['image'] and sha(ROOT/v['image'])==v['sha256']
 (ROOT/'output/release_gates.json').write_text(json.dumps(dict(status='LOCAL_RELEASE_GATES_PASS',config=CONFIG,candidate_sha256=v['sha256'],source_sha256=inputs,dependency_lock_sha256=sha(ROOT/'build/dependencies.lock.json'),resumed_validation=resume,physical_router_accessed=False),indent=2)+'\n')
 print('PASS all local release gates; device acceptance remains untested',flush=True)
if __name__=='__main__':main()
