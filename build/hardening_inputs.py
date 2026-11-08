"""Prepare shared fixture inputs serially before sealing independent VM jobs."""
from device_config import compiler_flags
import os
import subprocess
from check_installer_boundaries import fixtures, ROOT, sha


def prepare():
    os.chdir(ROOT)
    fixtures()
    arm = ['sources/zig-aarch64-macos-0.15.2/zig', 'cc', *compiler_flags(), '-O2', '-s']
    fixture = ['-DLM_BASE="/tmp/localmod-bounds"', '-DLM_DISPATCH="/tmp/bounds-dispatch.sh"',
               '-DLM_LOGGER="/work/build/log-limit-bounds-fixture"']
    for name, sources in [('log-limit', ['sources/localmod/log_limit.c']),
                          ('event', ['sources/localmod/event.c', 'sources/localmod/runtime.c']),
                          ('barrier', ['build/barrier_bounds_fixture.c', 'sources/localmod/runtime.c'])]:
        subprocess.run(arm + fixture + ['-o', 'build/' + name + '-bounds-fixture'] + sources, check=True)
    for name, source in [('soak-init', 'soak_init_fixture.c'), ('memory-exec', 'memory_exec_fixture.c')]:
        subprocess.run(['sources/zig-aarch64-macos-0.15.2/zig', 'cc', '-target', 'aarch64-linux-musl',
                        '-static', '-O2', '-o', 'build/' + name + '-fixture', 'build/' + source], check=True)
    subprocess.run(arm + ['-shared', '-fPIC', '-o', 'build/httpd_tls_cache_fixture.so',
                          'build/httpd_tls_cache_fixture.c', '-ldl'], check=True)
    common = ['build/native_runtime_client.go', 'build/test_online.go', 'build/coexist_helpers.go']
    programs = {
        'installer-boundaries': ['build/test_installer_boundaries.go'] + common,
        'resource-bounds': ['build/test_resource_bounds.go'] + common,
        'uu-recovery': ['build/test_uu_recovery.go'] + common,
        'health': ['build/test_health.go'] + common,
        'soak': ['build/test_soak.go', 'build/test_memory.go', 'build/memory_cycles.go', 'build/httpd_memory.go'] + common}
    inputs = {p: sha(ROOT / p) for p in sorted(set(sum(programs.values(), [])))}
    for name, sources in programs.items():
        subprocess.run(['go', 'build', '-trimpath', '-o', 'build/test-' + name] + sources,
                       check=True, env=dict(os.environ, GOOS='linux', GOARCH='arm64', CGO_ENABLED='0'))
    return inputs
