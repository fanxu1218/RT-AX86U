#!/usr/bin/env python3
"""Remove only the completed P7 hour's audited, regenerable scratch files."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'build'))
from sealed_vm import encoded, inventory, sha


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--apply', action='store_true'); args = parser.parse_args()
    gate = json.loads((ROOT / 'output/merlin38813_hour_gate.json').read_text())
    assert gate['status'] == 'P7_ONE_HOUR_LOCAL_VALIDATION_PASS_NOT_DEVICE_ACCEPTED'
    image = ROOT / gate['candidate']['image']; assert sha(image) == gate['candidate']['sha256']
    audit = ROOT / gate['generated_inputs_archive']['path']
    assert sha(audit) == gate['generated_inputs_archive']['sha256']
    hour_path = ROOT / gate['hour_report']['path']; assert sha(hour_path) == gate['hour_report']['sha256']
    hour = json.loads(hour_path.read_text()); vm = hour['vm']
    assert vm['sealed_inputs_verified_before_and_after'] and not vm['preserved_after_failure']
    assert subprocess.run(['pgrep', '-f', '[L]inuxBuilder|[q]emu-system|[c]heck_native_soak'], capture_output=True).returncode == 1
    targets = []
    work = ROOT / 'build/merlin38813-native-soak'
    if work.exists():
        assert work.is_dir() and not work.is_symlink()
        for p in work.rglob('*'):
            if p.is_dir(): continue
            assert p.is_file() and not p.is_symlink()
            name = p.relative_to(ROOT).as_posix()
            assert name in vm['inputs'] and sha(p) == vm['inputs'][name], ('Unexpected scratch file', name)
        targets.append(work)
    workspace = ROOT / vm['workspace_path']; job = workspace.parent
    vm_workspace_auto_removed = not job.exists()
    if job.exists():
        assert job.parent == ROOT / 'build/casefs/sealed-private' and not job.is_symlink()
        assert re.fullmatch(r'job-[0-9a-f]{24}', job.name)
        owner = json.loads((job / 'owner.json').read_text())
        assert owner['job'] == job.name and owner['phase'] == 'candidate-merlin-system'
        expected = json.loads((job / 'manifest.json').read_text())
        assert hashlib.sha256(encoded(expected)).hexdigest() == vm['sealed_manifest_sha256']
        assert inventory(workspace) == expected
        targets.append(job)
    rows = {}
    for directory in targets:
        rows[directory.relative_to(ROOT).as_posix()] = sum(p.stat().st_size for p in directory.rglob('*') if p.is_file())
    if not args.apply:
        print('AUDITED_HOUR_CACHE_TARGETS', json.dumps(rows)); return
    free = shutil.disk_usage(ROOT).free
    for directory in targets: shutil.rmtree(directory)
    assert sha(image) == gate['candidate']['sha256'] and sha(audit) == gate['generated_inputs_archive']['sha256']
    assert not workspace.exists()
    report = dict(status='P7_HOUR_TEMPORARY_CACHE_CLEANED', removed_directories=rows,
        logical_bytes_removed=sum(rows.values()), system_free_before=free, system_free_after=shutil.disk_usage(ROOT).free,
        successful_vm_workspace_auto_removed=vm_workspace_auto_removed,
        firmware_and_generated_source_audit_retained=True,
        source_sha256={'analysis/merlin_vpn_38813/cleanup_hour_cache.py': sha(Path(__file__).resolve())})
    (ROOT / 'output/merlin38813_hour_cleanup.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'], len(rows), 'audited scratch directories', report['logical_bytes_removed'], 'bytes')


if __name__ == '__main__': main()
