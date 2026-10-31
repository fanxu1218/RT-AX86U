#!/usr/bin/env python3
"""Corrupt sealed checkpoints and exhaust only an owned guest JFFS disk."""
import hashlib,json,os,shutil,subprocess
from pathlib import Path
from check_interrupt import compile_fixtures
from run_readonly_linux import run
ROOT=Path(__file__).resolve().parent.parent
PRIVATE=ROOT/'build/interrupt-private'
CASES=['damage-tree','damage-database','damage-manifest','damage-ready','damage-commit','damage-meta','damage-active-link','space-full','space-low','space-replay','legacy-r5']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def pinned_legacy_helper():
    commit='791ec5eb6c983c1d1ee24bda471d1194afb8734b'
    code=subprocess.check_output(['git','show',commit+':sources/localmod/plugin_txn.c'])
    p=ROOT/'build/r5-pinned-helper.c';p.write_bytes(code)
    subprocess.run(['sources/zig-aarch64-macos-0.15.2/zig','cc','-target','arm-linux-gnueabi.2.26','-mcpu=cortex_a53','-O2','-s','-o','build/plugin-txn-r5-baseline',str(p)],check=True)
    old=json.loads(subprocess.check_output(['git','show',commit+':output/interruption_tests.json']))
    actual=sha(ROOT/'build/plugin-txn-r5-baseline')
    assert actual==old['production_files']['usr/libexec/localmod/plugin-txn']
    return {'source_commit':commit,'binary_sha256':actual,'candidate_sha256':old['candidate_sha256']}

def boot(case,phase,disk,baseline=False,cut=False):
    (ROOT/'build/interrupt-phase.json').write_text(json.dumps({'case':case,'boot':phase,'baseline':baseline,'initialize':False})+'\n')
    (ROOT/'build/real-plugin-phase').write_text('interrupt-safety\n' if phase=='safety' else 'interrupt-run\n')
    print('Recovery safety VM:',case,phase,flush=True)
    log=ROOT/f'output/recovery_{case}_{phase}.log'
    text=run(log,state_disk=disk,expect_cut=cut)
    checks=[line[5:] for line in text.splitlines() if line.startswith('PASS ')]
    assert checks and len(checks)==len(set(checks))
    if phase=='safety':
        rows=[json.loads(line[len('SAFETY_RESULT '):]) for line in text.splitlines() if line.startswith('SAFETY_RESULT ')]
        assert len(rows)==1
        result=rows[0]
        assert result['case']==case and not result['baseline'] and result['blocked'] and result['retained']
        assert result['client']=={'api_status':423,'tls_archive_preserved':True,'uu_data_preserved':True,'uu_native_control_alive':True}
        assert not any(result['processes'].values())
    else:
        rows=[json.loads(line[len('INTERRUPT_RESULT '):]) for line in text.splitlines() if line.startswith('INTERRUPT_RESULT ')]
        assert rows and all(row['case']==case and row['boot']==phase for row in rows)
        result={'checks':[n for row in rows for n in row['checks']]}
        assert set(checks)==set(result['checks'])
    return checks,result

def main():
    os.chdir(ROOT)
    verification=json.loads((ROOT/'output/verification.json').read_text())
    assert verification['image'].endswith('localmod2_r6_EXPERIMENTAL.w') and all(verification['checks'].values())
    assert sha(ROOT/verification['image'])==verification['sha256']
    stage=ROOT/'build/casefs/rootfs';back=ROOT/'build/casefs/roundtrip'
    paths=['usr/libexec/localmod/plugin-txn','usr/libexec/localmod/bootstrap.sh','usr/libexec/localmod/installer-guard.sh','usr/lib/localmod/httpd_bridge.so']
    assert all((stage/p).read_bytes()==(back/p).read_bytes() for p in paths)
    compile_fixtures();legacy=pinned_legacy_helper()
    foundation=PRIVATE/'foundation.img';assert foundation.is_file() and foundation.stat().st_size==96*1024*1024
    checks={};details={};seeds=[]
    for name,old in [('safety-seed',False),('safety-seed-legacy',True)]:
        disk=PRIVATE/(name+'.img');assert not disk.exists();shutil.copyfile(foundation,disk);disk.chmod(0o600)
        names,result=boot(name,'cut',disk,baseline=old,cut=True)
        checks.update({name+'_'+n:True for n in names});seeds.append(disk)
    for case in CASES:
        disk=PRIVATE/('safety-'+case+'.img');assert not disk.exists();shutil.copyfile(seeds[case=='legacy-r5'],disk);disk.chmod(0o600)
        names,result=boot(case,'safety',disk);checks.update({case+'_stop_'+n:True for n in names});details[case]={'failure':result}
        if case!='legacy-r5':
            names,result=boot(case,'verify',disk);checks.update({case+'_resume_'+n:True for n in names});details[case]['next_boot']=result
        disk.unlink()
    for disk in seeds:disk.unlink()
    assert sha(ROOT/verification['image'])==verification['sha256']
    report={'status':'LOCAL_RECOVERY_FAILURE_SAFETY_PASS','candidate_image':verification['image'],'candidate_sha256':verification['sha256'],'checks':checks,'cases':details,'legacy_fixture':legacy,
        'production_files':{p:sha(stage/p) for p in paths},
        'r5_reproduction':'recovery_r5_baseline.json',
        'test_vm_count':2+2*(len(CASES)-1)+1,'disk_fixture_vcpus':1,'fixture_kernel_sha256':sha(ROOT/'build/tools/linux-Image'),
        'isolation':['No NIC/physical disk; read-only workspace; one owned 96 MiB ext4 virtual disk per case','Guest fallocate exhausts real fixture filesystem space before or during replay; only the fixture fill file is removed for retry','Corrupted bytes are repaired from known synthetic fixture originals, never by trusting or re-sealing corrupt user data'],
        'verified':['Corruption/low space leaves logical checkpoint, current or restored plugin files and quarantined original database available','Failed recovery stops center services and its newly started replay database; same-boot retry stays blocked','Native login/TLS, original UU control with owned monitor/worker, persistent UU test data and certificate archive remain usable','A later VM restores exact plugin records/files, real DDNS-Go autostart and allows changed-version retry after trusted repair/space release','Unsealed r5 journal is retained for manual review instead of adoption'],
        'not_tested':['Physical NAND/UBIFS faults, stock 4.1 kernel durability and hardware boot','Real UU account/discovery/entitlement/game traffic','Reconstruction of already lost/corrupt bytes without a known good backup; active root attacker modifying both data and seals','Rollback outside the center tree/skipd or concurrent external writers']}
    (ROOT/'output/recovery_safety_tests.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS',len(checks),'recovery safety checks across',len(CASES),'cases;',verification['sha256'])
if __name__=='__main__':main()
