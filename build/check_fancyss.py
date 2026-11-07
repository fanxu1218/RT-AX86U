#!/usr/bin/env python3
"""Validate pinned Fancyss on the published base plus a RAM-only source overlay."""
import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from prepare_fancyss import prepare, render_page
from run_readonly_linux import run

ROOT = Path(__file__).resolve().parent.parent
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser();mode=ap.add_mutually_exclusive_group();mode.add_argument('--baseline',action='store_true');mode.add_argument('--proxy',action='store_true');mode.add_argument('--components',action='store_true');mode.add_argument('--candidate',action='store_true');args=ap.parse_args()
    os.chdir(ROOT)
    manifest=prepare()
    from prepare_extended_plugins import prepare as prepare_extended
    extended=prepare_extended()
    v=json.loads((ROOT/'output/verification.json').read_text())
    assert sha(ROOT/v['image'])==v['sha256']
    if args.candidate:
        from check_softcenter import prepare_upgrade_inputs
        prepare_upgrade_inputs()
    subprocess.run(['go','build','-trimpath','-o','build/test-fancyss','build/test_fancyss.go',
                    'build/test_softcenter_upgrade.go','build/test_extended_plugins.go','build/test_online.go','build/native_runtime_client.go','build/coexist_helpers.go'],check=True,
                    env=dict(os.environ,GOOS='linux',GOARCH='arm64',CGO_ENABLED='0'))
    phase='candidate-fancyss-baseline' if args.baseline else 'hardening-fancyss'
    if args.proxy:phase='candidate-fancyss-proxy'
    if args.components:phase='hardening-fancyss-components'
    if args.candidate:phase='candidate-fancyss'
    overlay_files={}
    if not args.baseline and not args.proxy and not args.candidate:
        from check_installer_boundaries import overlay
        overlay_files=overlay()
        import shutil
        policy=ROOT/'build/hardening-overlay/usr/libexec/localmod/fancyss-packages.sha256'
        shutil.copyfile(ROOT/'sources/localmod/fancyss-packages.sha256',policy)
        overlay_files[str(policy.relative_to(ROOT/'build/hardening-overlay'))]=sha(policy)
        assert policy.read_text()==''.join(p['adapted_sha256']+'  shadowsocks\n' for p in manifest['packages'])
        from release_config import CONFIG
        www=ROOT/'build/hardening-overlay/www';www.mkdir(exist_ok=True)
        (www/'Module_FancyssLocalmod.asp').write_text(render_page(manifest,CONFIG))
        (www/'Module_Localmod.asp').write_text((ROOT/'sources/localmod/Module_Localmod.asp').read_text().replace('@REVISION@',CONFIG['variant']+'-'+CONFIG['revision']))
        overlay_files={str(p.relative_to(ROOT/'build/hardening-overlay')):sha(p) for p in (ROOT/'build/hardening-overlay').rglob('*') if p.is_file()}
    if args.candidate:
        from release_config import CONFIG
        assert v['image']==CONFIG['image'] and all(v['checks'].values()) and not v['errors']
        for relative,source in [('usr/libexec/localmod/plugin-compat.sh','sources/localmod/plugin-compat.sh'),('usr/libexec/localmod/installer-guard.sh','sources/localmod/installer-guard.sh'),('usr/libexec/localmod/fancyss-packages.sha256','sources/localmod/fancyss-packages.sha256'),('rom/etc/koolshare/scripts/ks_tar_install.sh','sources/localmod/offline-installer.sh')]:
            assert (ROOT/'build/casefs/rootfs'/relative).read_bytes()==(ROOT/'build/casefs/roundtrip'/relative).read_bytes()==(ROOT/source).read_bytes(),relative
        assert (ROOT/'build/casefs/roundtrip/www/Module_FancyssLocalmod.asp').read_text()==render_page(manifest,CONFIG)
        assert (ROOT/'build/httpd_bridge.so').read_bytes()==(ROOT/'build/casefs/rootfs/usr/lib/localmod/httpd_bridge.so').read_bytes()==(ROOT/'build/casefs/roundtrip/usr/lib/localmod/httpd_bridge.so').read_bytes()
    source_paths=['sources/localmod/plugin-compat.sh','build/patch_online_installer.py','build/check_installer_boundaries.py','build/check_fancyss.py','build/prepare_fancyss.py','build/fancyss_sources.json','build/prepare_extended_plugins.py','build/extended_plugin_sources.json','build/test_fancyss.go','build/test_extended_plugins.go','build/test_online.go','build/native_runtime_client.go','build/coexist_helpers.go','build/run_readonly_linux.py','build/linux_real_plugins_job.sh','build/real_plugins_setup.sh','sources/localmod/installer-guard.sh','sources/localmod/offline-installer.sh','sources/localmod/fancyss-packages.sha256','sources/localmod/Module_FancyssLocalmod.asp','sources/localmod/Module_Localmod.asp','sources/localmod/fancyss-LICENSE.txt']
    source_hashes={p:sha(ROOT/p) for p in source_paths}
    for p in ['build/test_softcenter_upgrade.go','build/check_softcenter.py','build/prepare_softcenter.py','build/softcenter_frontend_contract.mjs','build/softcenter_sources.json']:
        source_hashes[p]=sha(ROOT/p)
    executable_sha=sha(ROOT/'build/test-fancyss')
    (ROOT/'build/real-plugin-phase').write_text(phase+'\n')
    log=ROOT/('build/fancyss_components.log' if args.components else 'build/fancyss_proxy.log' if args.proxy else 'output/fancyss_baseline.log' if args.baseline else 'output/fancyss_lifecycle.log')
    text=run(log,timeout=660)
    rows=[json.loads(line[len('FANCYSS_RESULT '):]) for line in text.splitlines() if line.startswith('FANCYSS_RESULT ')]
    assert len(rows)==1 and rows[0]['checks'] and all(rows[0]['checks'].values())
    assert sha(ROOT/v['image'])==v['sha256']
    assert source_hashes=={p:sha(ROOT/p) for p in source_hashes}
    assert executable_sha==sha(ROOT/'build/test-fancyss')
    if overlay_files:assert overlay_files=={str(p.relative_to(ROOT/'build/hardening-overlay')):sha(p) for p in (ROOT/'build/hardening-overlay').rglob('*') if p.is_file()}
    report=dict(status='BASELINE_REPRODUCED' if args.baseline else 'LOCAL_CANDIDATE_PLUGINS_PASS' if args.candidate else 'LOCAL_SOURCE_OVERLAY_PASS',
                base_candidate_image=v['image'],base_candidate_sha256=v['sha256'],firmware_rebuilt=bool(args.candidate),checks=rows[0]['checks'],
                sources=manifest,extended_sources=extended,result=rows[0],overlay_files=overlay_files,log_sha256=sha(log),
                source_sha256=source_hashes,test_executable_sha256=executable_sha,
                isolation=['No guest NIC, host workspace read-only, synthetic accounts, RAM-only 128 MiB test JFFS (production capacity is unchanged)',
                           'Original ASUS login/TLS and UU download/checksum flow with owned local UU worker',
                           'Original third-party ELF files; five Fancyss management/installer files adapted',
                           'FRPC and PushPlus current packages follow pinned upstream HND build recipes; firmware applies only hash-pinned cleanup/callback fixes before checkpoint'],
                not_tested=['Physical router/kernel/NAND and real UU account/traffic',
                            'Real proxy node, WAN/DNS/IPv6 routing, provider subscriptions and cloud rule downloads',
                            'Original 4.1.52 kernel: package identity check uses a declared uname fixture on Alpine 6.12',
                            'WebSocket-only live streaming features: upstream authenticated HTTP fallbacks selected'])
    if args.candidate:report.update(candidate_image=v['image'],candidate_sha256=v['sha256'])
    out=ROOT/('build/fancyss_components.json' if args.components else 'build/fancyss_proxy.json' if args.proxy else 'build/fancyss_baseline.json' if args.baseline else 'output/fancyss_tests.json')
    out.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS',len(rows[0]['checks']),'Fancyss checks; '+('rebuilt candidate' if args.candidate else 'baseline' if args.baseline else 'source overlay only'),flush=True)


if __name__=='__main__':main()
