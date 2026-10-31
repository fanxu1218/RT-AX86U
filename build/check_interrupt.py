#!/usr/bin/env python3
"""Cut isolated VMs at install boundaries; restart with the same owned disk."""
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from run_readonly_linux import run

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = ROOT / 'build/interrupt-private'
CASES = ['download', 'checkpoint', 'kill-parent', 'kill-tree', 'offline', 'fresh',
         'real-ddnsgo', 'before-commit', 'after-commit', 'committed-cleanup', 'no-space']


def compile_fixtures():
    subprocess.run(['go', 'build', '-trimpath', '-o', 'build/test-interrupt',
                    'build/test_interrupt_main.go', 'build/interrupt_scenarios.go',
                    'build/test_interrupt.go', 'build/test_online.go',
                    'build/native_runtime_client.go', 'build/coexist_helpers.go'], check=True,
                   env=dict(os.environ, GOOS='linux', GOARCH='arm64', CGO_ENABLED='0'))
    subprocess.run(['sources/zig-aarch64-macos-0.15.2/zig', 'cc', '-target',
                    'arm-linux-gnueabi.2.26', '-mcpu=cortex_a53', '-O2', '-shared', '-fPIC',
                    '-o', 'build/txn_fault_fixture.so', 'build/txn_fault_fixture.c', '-ldl'], check=True)


def boot(case, phase, disk, initialize=False, cut=False):
    (ROOT / 'build/interrupt-phase.json').write_text(json.dumps({
        'case': case, 'initialize': initialize, 'boot': phase}) + '\n')
    (ROOT / 'build/real-plugin-phase').write_text('interrupt-run\n')
    print('Interruption VM:', case, phase, flush=True)
    text = run(ROOT / f'output/interrupt_{case}_{phase}.log', state_disk=disk, expect_cut=cut)
    results = [json.loads(line.removeprefix('INTERRUPT_RESULT ')) for line in text.splitlines()
               if line.startswith('INTERRUPT_RESULT ')]
    assert results and all(r['case'] == case and r['boot'] == phase for r in results)
    checks = [name for r in results for name in r['checks']]
    assert checks and len(checks) == len(set(checks))
    assert all('PASS ' + name + '\n' in text for name in checks)
    return checks


def main():
    os.chdir(ROOT)
    verification = json.loads((ROOT / 'output/verification.json').read_text())
    image = ROOT / verification['image']
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    assert sha(image) == verification['sha256'] and all(verification['checks'].values())
    stage = ROOT / 'build/casefs/rootfs'
    readback = ROOT / 'build/casefs/roundtrip'
    paths = ['usr/libexec/localmod/plugin-txn', 'usr/libexec/localmod/installer-guard.sh',
             'usr/libexec/localmod/bootstrap.sh', 'usr/lib/localmod/httpd_bridge.so',
             'rom/etc/koolshare/scripts/ks_app_install.sh', 'rom/etc/koolshare/scripts/ks_tar_install.sh']
    assert all((stage / p).read_bytes() == (readback / p).read_bytes() for p in paths)
    compile_fixtures()
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    PRIVATE.chmod(0o700)
    foundation = PRIVATE / 'foundation.img'
    # Only this runner's named, owned, disposable fixture may be initialized.
    assert not foundation.is_symlink()
    with foundation.open('wb') as f:
        f.truncate(96 * 1024 * 1024)
    foundation.chmod(0o600)
    checks = {'foundation_' + n: True for n in boot('foundation', 'foundation', foundation, True)}
    details = {}
    for case in CASES:
        disk = PRIVATE / (case + '.img')
        assert not disk.exists(), 'Retained failure fixture: ' + str(disk)
        shutil.copyfile(foundation, disk)
        disk.chmod(0o600)
        phases = [('exercise', False)] if case == 'no-space' else [('cut', True), ('verify', False)]
        if case == 'kill-tree':
            phases.insert(1, ('recover-cut', True))
        if case == 'kill-parent':
            phases.insert(1, ('recover-db-cut', True))
        details[case] = {}
        for phase, cut in phases:
            names = boot(case, phase, disk, cut=cut)
            details[case][phase] = names
            checks.update({case + '_' + phase + '_' + n: True for n in names})
        disk.unlink()  # Completed disposable disk only; failed disks stay private.
    assert sha(image) == verification['sha256']
    report = {
        'status': 'LOCAL_INTERRUPTION_RECOVERY_PASS', 'candidate_image': verification['image'],
        'candidate_sha256': verification['sha256'], 'checks': checks, 'cases': details,
        'production_files': {p: sha(stage / p) for p in paths},
        'r4_baseline': {'image': 'RT-AX86U_388_24437_localmod2_r4_EXPERIMENTAL.w',
                        'sha256': '921c26da74881f868739c0a42a20171c530755c18df6f6349e69e0351c0f3abb',
                        'reproduction_log': 'interrupt_r4_reproductions.log'},
        'isolation': ['No NIC or physical device; read-only host workspace; one owned 96 MiB ext4 virtual disk',
                      'VM process terminated at explicit boundary without guest shutdown/sync; next boot is a new VM',
                      'Test-only fault interposer and cp wrapper stay outside firmware and archives remain unchanged'],
        'data_checked': ['Exact plugin YAML and binary bytes, literal multiline/quoted skipd records, unrelated plugin key',
                         'Real DDNS-Go 1.28 configuration, version, watchdog autostart and local page after recovery',
                         'UU synthetic persistent cache/checksum/user-state bytes and temporary download; TLS archive bytes',
                         'Failed new center/database quarantined; authenticated write lock and successful retry after reboot'],
        'not_tested': ['Physical UBIFS/NAND power cuts, stock 4.1 kernel and actual JFFS durability',
                       'Real UU account, monitor, cloud discovery and acceleration traffic',
                       'Rollback outside the center tree/skipd, arbitrary privileged installer behavior or concurrent background file writers'],
    }
    (ROOT / 'output/interruption_tests.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS', len(checks), 'interruption checks across', len(CASES), 'cases;', verification['sha256'])


if __name__ == '__main__':
    main()
