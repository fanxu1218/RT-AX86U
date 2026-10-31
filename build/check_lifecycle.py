#!/usr/bin/env python3
"""Exercise native certificate persistence and center/UU coexistence, offline."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent.parent
os.chdir(root)
ap = argparse.ArgumentParser()
ap.add_argument('--skip-native-regression', action='store_true',
                help='Only for build_candidate, which has just run those jobs')
args = ap.parse_args()
stage = root / 'build/casefs/rootfs'
official = root / 'build/casefs/official_rootfs'
assert (root / 'build/casefs').is_mount()
verification = json.loads((root / 'output/verification.json').read_text())
image = root / verification['image']
assert hashlib.sha256(image.read_bytes()).hexdigest() == verification['sha256']
assert all(verification['checks'].values()) and not verification['errors']
for name, target in [('httpd_bridge.so', 'usr/lib/localmod/httpd_bridge.so'),
                     ('rc_bridge.so', 'usr/lib/localmod/rc_bridge.so'),
                     ('localmod-event', 'usr/libexec/localmod/localmod-event')]:
    assert (root / 'build' / name).read_bytes() == (stage / target).read_bytes(), name

def run(*command):
    subprocess.run(command, cwd=root, check=True)

def job(name, destination):
    print('Running offline VM job:', name, flush=True)
    shutil.copyfile(root / f'build/linux_{name}_job.sh', root / 'build/linux_job.sh')
    with (root / destination).open('w') as output:
        subprocess.run(['python3', 'build/run_linux.py'], cwd=root, check=True,
                       stdout=output, stderr=subprocess.STDOUT)

private = root / 'build/native-lifecycle-private'
def clean_private():
    if private.exists():
        assert private.is_dir() and not private.is_symlink()
        assert private.resolve() == root / 'build/native-lifecycle-private'
        shutil.rmtree(private)

clean_private()
try:
    flags = [str(root / 'sources/zig-aarch64-macos-0.15.2/zig'), 'cc',
             '-target', 'arm-linux-gnueabi.2.26', '-mcpu=cortex_a53', '-O2']
    run(str(root / 'analysis/.venv/bin/python'), 'build/prepare_native_fixtures.py')
    run(*flags, '-shared', '-fPIC', '-o', 'build/native_hw_fixture.so', 'build/native_hw_fixture.c')
    run(*flags, '-shared', '-fPIC', '-o', 'build/native_uu_transport.so', 'build/native_uu_transport.c', '-ldl')
    run(*flags, '-DNATIVE_NVRAM_CLI', '-o', 'build/native-nvram', 'build/native_hw_fixture.c')
    programs = [('cert-lifecycle', ['build/test_cert_lifecycle.go', 'build/native_runtime_client.go']),
                ('coexist', ['build/test_coexist.go', 'build/native_runtime_client.go'])]
    if not args.skip_native_regression:
        programs += [('native-httpd', ['build/test_native_httpd.go']),
                     ('native-uu', ['build/test_native_uu.go'])]
    for name, files in programs:
        subprocess.run(['go', 'build', '-o', 'build/test-' + name, *files], check=True,
                       env=dict(os.environ, GOOS='linux', GOARCH='arm64', CGO_ENABLED='0'))
    if not args.skip_native_regression:
        for name in ['native_httpd', 'native_uu']:
            job(name, 'build/' + name + '_tests_run.log')
        run('python3', 'build/verify_native_runtime.py')
        for name in ['native_httpd', 'native_uu']:
            shutil.copyfile(root / f'build/{name}_tests_run.log', root / f'output/{name}_tests_run.log')
    for name in ['cert_generate', 'cert_restore', 'coexist']:
        (root / f'build/{name}_result.json').unlink(missing_ok=True)
        job(name, 'build/' + name + '_tests_run.log')

    checks, details = {}, {}
    for name, expected in [('cert_generate', 4), ('cert_restore', 4), ('coexist', 9)]:
        data = json.loads((root / f'build/{name}_result.json').read_text())
        log = (root / f'build/{name}_tests_run.log').read_text()
        assert len(data['checks']) == expected and len(set(data['checks'])) == expected
        for key in data['checks']:
            assert key not in checks and 'PASS ' + key + '\n' in log
            checks[key] = True
        details[name] = data['details']
        shutil.copyfile(root / f'build/{name}_tests_run.log', root / f'output/{name}_tests_run.log')
    assert details['cert_generate']['generated_leaf_sha256'] == details['cert_restore']['restored_leaf_sha256'] == details['coexist']['leaf_sha256']
    paths = {'usr/sbin/httpd': 'usr/libexec/localmod/httpd', 'sbin/rc': 'usr/libexec/localmod/rc.vendor',
             'usr/sbin/gencert.sh': 'usr/sbin/gencert.sh', 'usr/sbin/openssl': 'usr/sbin/openssl',
             'usr/lib/libshared.so': 'usr/lib/libshared.so', 'rom/etc/openssl.cnf': 'rom/etc/openssl.cnf'}
    hashes = {}
    for source, target in paths.items():
        assert (official / source).read_bytes() == (stage / target).read_bytes(), target
        hashes[source] = hashlib.sha256((stage / target).read_bytes()).hexdigest()
    fixture_names = {'native_hw_fixture.so', 'native_uu_transport.so', 'native-nvram',
                     'native_defaults.bin', 'native_shadow_hash.txt', 'owned-uu-worker.sh',
                     'coexist_probe.sh', 'native-lifecycle-private'}
    assert not [str(p) for p in stage.rglob('*') if p.name in fixture_names]
    assert hashlib.sha256(image.read_bytes()).hexdigest() == verification['sha256']
    report = {
        'status': 'PASS', 'candidate_image': verification['image'],
        'candidate_sha256': verification['sha256'], 'checks': checks, 'details': details,
        'retained_vendor_sha256': hashes,
        'native_certificate_generation_save_restore_and_tls_functions_replaced': False,
        'tls_chain_and_hostname_verification_disabled': False,
        'real_uu_monitor_executed': False, 'test_fixtures_in_firmware': [],
        'environment': [
            'Networkless ARM64 Linux 6.12 VM with actual ARM32 vendor applications via QEMU',
            'Actual retained gencert.sh and OpenSSL, synthetic NVRAM/shadow/LAN inputs',
            'Fresh VM restores only an owned cert.tgz from the previous VM; real flash/NVRAM are not exercised',
            'Native certificate chain and SAN checked, generated private key permissions checked',
            'Actual packaged perpboot/perpd/httpdb/skipd/dbus and production bootstrap lifecycle',
            'Guest CPU/proc wrappers, Alpine curl and legacy xtables; controlled UU download and owned worker',
        ],
        'not_tested': [
            'Router flash, physical reboot, target kernel 4.1, real NVRAM and power-loss durability',
            'Browser acceptance, ACME renewal and uploaded certificate workflows',
            'Real UU download/TLS, accounts, entitlement, discovery and acceleration',
            'Arbitrary third-party plugins and hardware network coexistence',
        ],
    }
    (root / 'output/lifecycle_tests.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS all 17 certificate/coexistence checks; candidate SHA256', verification['sha256'])
finally:
    clean_private()
