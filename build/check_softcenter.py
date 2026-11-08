#!/usr/bin/env python3
"""Verify the real1.9.60 frontend, managed migration and plugin coexistence."""
from device_config import DEVICE, leb_size
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
from sealed_vm import ROOT, inventory, sha, encoded, copy_file
from prepare_softcenter import PIN


def prepare_upgrade_inputs():
    pin=json.loads(PIN.read_text())
    old_core=ROOT/'build/softcenter-old-core'
    old_receipt=ROOT/'build/softcenter-old-inputs.json'
    baseline=ROOT/pin['baseline_image']
    assert sha(baseline)==pin['baseline_image_sha256']
    if not old_core.exists():
        assert not old_core.is_symlink() and not old_receipt.exists()
        job=ROOT/'build/casefs/softcenter-private'/('baseline-'+secrets.token_hex(12))
        job.mkdir(mode=0o700)
        subprocess.run(['python3','build/inspect_upstream.py',str(baseline),str(job)],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
        extraction='from ubireader.ubi_io import ubi_file;from ubireader.ubifs import ubifs;from ubireader.ubifs.output import extract_files;import sys;extract_files(ubifs(ubi_file(sys.argv[1],int(sys.argv[3]))),sys.argv[2])'
        extracted=job/'rootfs';extracted.mkdir()
        subprocess.run([str(ROOT/'analysis/.venv/bin/python'),'-c',extraction,str(job/DEVICE['image']['rootfs_volume_name']),str(extracted),str(leb_size())],check=True)
        source=extracted/'rom/etc/koolshare';tree=inventory(source)
        assert hashlib.sha256(encoded(tree)).hexdigest()==pin['baseline_core_tree_sha256']
        core_id=(extracted/'rom/etc/localmod-core-id').read_text().strip()
        assert core_id==pin['baseline_core_id']
        shutil.copytree(source,old_core,symlinks=True,copy_function=copy_file)
        receipt=dict(baseline_image=pin['baseline_image'],baseline_image_sha256=pin['baseline_image_sha256'],core_id=core_id,tree=tree,tree_sha256=pin['baseline_core_tree_sha256'])
        old_receipt.write_bytes(encoded(receipt)+b'\n')
        shutil.rmtree(job)
    old=json.loads(old_receipt.read_text())
    tree=inventory(old_core)
    assert old['tree']==tree and old['tree_sha256']==hashlib.sha256(encoded(tree)).hexdigest()==pin['baseline_core_tree_sha256']
    assert old['baseline_image_sha256']==pin['baseline_image_sha256'] and old['core_id']==pin['baseline_core_id']
    assert (old_core/'.soft_ver').read_text().strip()=='1.9.50'
    subprocess.run(['node','build/softcenter_frontend_contract.mjs'],cwd=ROOT,check=True)


def main():
    os.chdir(ROOT)
    v=json.loads((ROOT/'output/verification.json').read_text())
    from release_config import CONFIG
    assert v['image']==CONFIG['image'] and sha(ROOT/v['image'])==v['sha256'] and all(v['checks'].values()) and not v['errors']
    sources=['build/check_softcenter.py','build/prepare_softcenter.py','build/softcenter_sources.json',
             'build/softcenter_frontend_contract.mjs','build/test_softcenter_upgrade.go','build/test_fancyss.go',
             'build/check_fancyss.py','build/stage_image.py','build/sealed_vm.py']
    before={p:sha(ROOT/p) for p in sources}
    subprocess.run(['python3','build/check_fancyss.py','--candidate'],check=True)
    log=ROOT/'output/fancyss_lifecycle.log'
    rows=[json.loads(s[len('SOFTCENTER_RESULT '):]) for s in log.read_text().splitlines() if s.startswith('SOFTCENTER_RESULT ')]
    assert len(rows)==1 and len(rows[0]['checks'])==9 and all(rows[0]['checks'].values())
    assert rows[0]['version']=='1.9.60' and rows[0]['uu_api_requests']==rows[0]['uu_downloads']==1
    frontend=json.loads((ROOT/'output/softcenter_frontend_tests.json').read_text())
    assert frontend['candidate_sha256']==v['sha256'] and all(frontend['checks'].values())
    assert before=={p:sha(ROOT/p) for p in sources} and sha(ROOT/v['image'])==v['sha256']
    shutil.copyfile(log,ROOT/'output/softcenter_upgrade.log')
    report=dict(status='LOCAL_SOFTCENTER_1960_UPGRADE_PASS',candidate_image=v['image'],candidate_sha256=v['sha256'],
                sources=json.loads(PIN.read_text()),source_sha256=before,checks=rows[0]['checks'],result=rows[0],
                frontend_report_sha256=sha(ROOT/'output/softcenter_frontend_tests.json'),
                full_fancyss_report_sha256=sha(ROOT/'output/fancyss_tests.json'),log_sha256=sha(log),
                limits=['Real pinned1.9.50 runtime core is copied into synthetic JFFS with authentic Fancyss data, then managed bootstrap upgrades it to1.9.60',
                        'New frontend functions generate RPC fixtures executed through actual retained ASUS HTTPS/login/httpdb/skipd; browser rendering is separate',
                        'No physical router/WAN/UU accounts or acceleration; host export read-only and no guest NIC',
                        'Unadapted Fancyss and direct core overwrite remain intentionally blocked; ordinary newer plugin updates work through the managed installer'])
    (ROOT/'output/softcenter_upgrade_tests.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS1.9.60 core migration, distributed frontend payloads and plugin/Fancyss/UU coexistence',flush=True)


if __name__=='__main__':main()
