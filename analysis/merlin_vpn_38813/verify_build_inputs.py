#!/usr/bin/env python3
"""Independently rebuild the six adapters and bind their complete local inputs."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'build'))
from sealed_vm import sha


def main():
    candidate = json.loads((ROOT / 'output/merlin38813_native_candidate_tests.json').read_text())
    assert sha(ROOT / candidate['image']['image']) == candidate['image']['sha256']
    tree = ROOT / candidate['rootfs']
    cc = [str(ROOT / 'sources/zig-aarch64-macos-0.15.2/zig'), 'cc',
        '-target', 'arm-linux-gnueabi.2.26', '-mcpu=cortex_a53', '-O2', '-s']
    programs = [
        ('native_boot_bridge.so', HERE / 'native_boot_bridge.c', ['-shared', '-fPIC', str(ROOT / 'sources/localmod/runtime.c'), '-ldl'], 'usr/lib/localmod/native_boot_bridge.so'),
        ('native-rc', HERE / 'native_launcher.c', [], 'sbin/rc'),
        ('native-restore', HERE / 'native_restore.c', [str(ROOT / 'sources/localmod/runtime.c')], 'usr/sbin/iptables-restore'),
        ('compat-sleep', HERE / 'center_sleep.c', [], 'usr/libexec/localmod/compat-bin/sleep'),
        ('httpd_bridge.so', ROOT / 'sources/localmod/httpd_bridge.c', ['-shared', '-fPIC', '-ldl'], 'usr/lib/localmod/httpd_bridge.so'),
        ('httpd-launcher', ROOT / 'sources/localmod/launcher.c', [], 'usr/sbin/httpd')]
    inputs = [Path(__file__), ROOT / 'sources/localmod/runtime.c', ROOT / 'sources/localmod/runtime.h',
        ROOT / 'sources/localmod/bounded_log.h', ROOT / 'sources/zig-aarch64-macos-0.15.2/zig',
        ROOT / 'build/softcenter_sources.json', ROOT / 'build/fancyss_sources.json',
        *[source for _, source, _, _ in programs]]
    before = {str(p.relative_to(ROOT)): sha(p) for p in inputs}
    output = {}
    with tempfile.TemporaryDirectory(prefix='merlin38813-recompile-', dir=ROOT / 'build') as folder:
        for name, source, flags, target in programs:
            binary = Path(folder) / name
            subprocess.run([*cc, '-o', str(binary), str(source), *flags], check=True)
            assert sha(binary) == sha(tree / target), ('Adapter differs from current source', target)
            output[target] = sha(binary)
    assert before == {n: sha(ROOT / n) for n in before}
    report = dict(status='P7_ADAPTER_RECOMPILE_BYTE_EQUIVALENCE_PASS',
        candidate_sha256=candidate['image']['sha256'], programs=output, source_sha256=before,
        note='Independent compilation supplements the immutable candidate build receipt; no firmware bytes or execution reports changed')
    (ROOT / 'output/merlin38813_build_inputs.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'], len(output), 'adapters')


if __name__ == '__main__':
    main()
