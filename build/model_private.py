#!/usr/bin/env python3
"""Private copies for trusted legacy model/build jobs; no checkout export.

Actual third-party plugin jobs use sealed_vm's read-only exports. These older
controlled jobs need writable result paths, so only their private copy is RW;
input manifests must still match before any named result is collected.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import selectors
import shutil
import stat
import subprocess
import time
from sealed_vm import ROOT, acquire_slot, copy_file, encoded, inventory, sha

JOBS = ['build', 'filemap', 'hooks', 'restore', 'center', 'native_httpd', 'native_uu',
        'cert_generate', 'cert_restore', 'coexist', 'online']
INPUTS = ['bridge-fixture', 'libfilemap_vendor.so', 'filemap-fixture', 'rc_bridge.so',
          'httpd_bridge.so', 'httpd-launcher', 'init-launcher', 'rc-launcher',
          'iptables-restore-launcher', 'localmod-event', 'plugin-txn', 'archive-guard',
          'plugin-run', 'log-limit', 'localmod-status', 'rc_bridge_fixture.so',
          'librc_vendor_fixture.so', 'rc-fixture', 'runtime-fixture', 'restore-fixture',
          'test-bridge', 'test-real-backend', 'test-restore', 'test-center',
          'test-launcher-vendor', 'test-native-httpd', 'test-native-uu',
          'test-cert-lifecycle', 'test-coexist', 'test-online', 'native-nvram',
          'native_defaults.bin', 'native_shadow_hash.txt', 'native_hw_fixture.so',
          'native_uu_transport.so', 'model_helpers_setup.sh', 'native_lifecycle_setup.sh']
OUTPUTS = {
    'localmod-rootfs.ubifs': 96 * 1024 * 1024,
    'hooks_trace.log': 1024 * 1024, 'hooks_dnsmasq.conf': 1024 * 1024,
    'launcher_forward.json': 65536, 'launcher_disabled.json': 65536,
    'httpd_launcher_forward.json': 65536, 'httpd_launcher_disabled.json': 65536,
    'restore_kernel_version.txt': 65536, 'restore_helper_version.txt': 65536,
    'restore_hook_trace.log': 1024 * 1024,
    'center_install_trace.log': 1024 * 1024, 'center_bootstrap_trace.log': 1024 * 1024,
    'native_http_server.log': 1024 * 1024, 'native_https_server.log': 1024 * 1024,
    'native_httpd_result.json': 1024 * 1024, 'native_uu_result.json': 1024 * 1024,
    'cert_generate_result.json': 1024 * 1024, 'cert_restore_result.json': 1024 * 1024,
    'coexist_result.json': 1024 * 1024, 'cert-generate-server.log': 1024 * 1024,
    'cert-service-restart-server.log': 1024 * 1024, 'cert-key-mismatch-server.log': 1024 * 1024,
    'cert-cold-restore-server.log': 1024 * 1024, 'cert-corrupt-archive-server.log': 1024 * 1024,
    'cert-nosave-server.log': 1024 * 1024, 'coexist-server.log': 1024 * 1024,
    'coexist-https-restart-server.log': 1024 * 1024,
    'coexist-ntp.log': 1024 * 1024,
    'online_success_result.json': 1024 * 1024, 'online_errors_result.json': 1024 * 1024,
    'online_concurrent_result.json': 1024 * 1024,
    'online-success-server.log': 1024 * 1024, 'online-errors-server.log': 1024 * 1024,
    'online-concurrent-server.log': 1024 * 1024,
    'online-success-ntp.log': 1024 * 1024, 'online-errors-ntp.log': 1024 * 1024,
    'online-concurrent-ntp.log': 1024 * 1024,
    'native_ntp_uu_start_once.log': 1024 * 1024,
    'native_uu_bad_checksum_blocks_execution.log': 1024 * 1024,
    'native_uu_api_failure_blocks_execution.log': 1024 * 1024,
    'native_uu_malformed_response_blocks_execution.log': 1024 * 1024,
    'native_uu_non_china_sku_skipped.log': 1024 * 1024,
    'native_uu_ap_mode_skipped.log': 1024 * 1024,
}


def tree_inventory(folder):
    data = inventory(folder)
    aliases = {}
    for name, entry in data.items():
        if entry['type'] == 'file':
            s = (folder / name).stat()
            if s.st_nlink > 1:
                aliases.setdefault((s.st_dev, s.st_ino), []).append(name)
    for paths in aliases.values():
        if len(paths) > 1:
            anchor = min(paths)
            for path in paths:
                data[path]['hardlink_group'] = anchor
    return data


def copy_tree(source, target):
    # Preserve vendor aliases within the new copy, never link to an input inode.
    seen = {}
    def member(left, right):
        s = Path(left).stat()
        key = (s.st_dev, s.st_ino)
        if s.st_nlink > 1 and key in seen:
            os.link(seen[key], right)
            return right
        result = copy_file(left, right)
        if s.st_nlink > 1:
            seen[key] = right
        return result
    return shutil.copytree(source, target, symlinks=True, copy_function=member)


def regular(path, cap):
    s = path.lstat()
    assert stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_uid == os.getuid()
    assert 0 <= s.st_size <= cap, 'Model output size limit: ' + str(path)
    return s


class ModelJob:
    def __init__(self, name, phase=None, state_id=None, guest_script=None):
        assert name in JOBS
        assert (phase in ['success', 'errors', 'concurrent']) if name == 'online' else phase is None
        assert (state_id is not None) == (name in ['cert_generate', 'cert_restore', 'coexist'])
        assert (ROOT / 'build/casefs').is_mount()
        self.name, self.phase, self.ok = name, phase, False
        self.runner_path = Path(__file__).resolve()
        self.runner_sha256 = sha(self.runner_path)
        self.state_fd, self.state_dir = None, None
        parent = ROOT / 'build/casefs/model-private'
        assert not parent.is_symlink()
        parent.mkdir(mode=0o700, exist_ok=True)
        parent.chmod(0o700)
        assert shutil.disk_usage(parent).free >= 256 * 1024 * 1024
        self.job = parent / ('job-' + secrets.token_hex(12))
        self.job.mkdir(mode=0o700)
        self.workspace = self.job / 'workspace'
        self.workspace.mkdir(mode=0o700)
        (self.job / 'owner.json').write_bytes(encoded(dict(job=self.job.name, name=name, phase=phase)))
        try:
            paths = ['build/casefs/rootfs', 'build/casefs/official_rootfs']
            paths += ['build/' + p for p in INPUTS if (ROOT / 'build' / p).is_file()]
            paths += ['build/tools/' + p for p in ['LinuxBuilder', 'linux-Image', 'linux-initramfs.gz']]
            paths += subprocess.check_output(['git', 'ls-files', '--', 'sources/localmod'], cwd=ROOT, text=True).splitlines()
            self.sources = {}
            for name in sorted(paths):
                source, target = ROOT / name, self.workspace / name
                assert source.exists() and not source.is_symlink(), name
                target.parent.mkdir(parents=True, exist_ok=True)
                if source.is_dir():
                    original = tree_inventory(source)
                    copy_tree(source, target)
                    assert tree_inventory(source) == original == tree_inventory(target), name
                    self.sources[name] = hashlib.sha256(encoded(original)).hexdigest()
                else:
                    original = sha(source)
                    copy_file(source, target)
                    assert original == sha(source) == sha(target), name
                    self.sources[name] = original
            original_job = ROOT / ('build/linux_' + self.name + '_job.sh')
            body = original_job.read_bytes()
            self.sources[original_job.relative_to(ROOT).as_posix()] = sha(original_job)
            script = b'''#!/bin/sh
set -eu
[ "$(ls /sys/class/net)" = lo ]
[ ! -e /work/.git ] && [ ! -e /work/upstream ]
echo MODEL_PRIVATE_EXPORT_READY
''' + (body if guest_script is None else guest_script)
            (self.workspace / 'build/linux_job.sh').write_bytes(script)
            if phase is not None:
                (self.workspace / 'build/online-phase').write_text(phase + '\n')
            if state_id is not None:
                assert re.fullmatch(r'state-[0-9a-f]{24}', state_id)
                state_parent = ROOT / 'build/model-state-private'
                assert not state_parent.is_symlink()
                state_parent.mkdir(mode=0o700, exist_ok=True)
                self.state_dir = state_parent / state_id
                assert not self.state_dir.is_symlink()
                self.state_dir.mkdir(mode=0o700, exist_ok=True)
                assert not any((self.state_dir / p).exists() or (self.state_dir / p).is_symlink() for p in ['pending', 'previous']), 'Incomplete synthetic state handoff retained'
                marker = self.state_dir / 'owner.json'
                if not marker.exists():
                    marker.write_bytes(encoded(dict(state_id=state_id, purpose='synthetic-model-lifecycle')))
                assert not marker.is_symlink()
                regular(marker, 1024)
                assert json.loads(marker.read_text()) == dict(state_id=state_id, purpose='synthetic-model-lifecycle')
                self.state_fd = os.open(self.state_dir / 'lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
                lock_stat = os.fstat(self.state_fd)
                assert stat.S_ISREG(lock_stat.st_mode) and lock_stat.st_uid == os.getuid() and lock_stat.st_nlink == 1 and lock_stat.st_size == 0
                fcntl.flock(self.state_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                data = self.state_dir / 'data'
                if data.exists():
                    assert data.is_dir() and not data.is_symlink()
                    original_state = inventory(data)
                    assert len(original_state) <= 100 and all(x['type'] in ['directory', 'file'] for x in original_state.values())
                    assert sum(x.get('bytes', 0) for x in original_state.values()) <= 8 * 1024 * 1024
                    target = self.workspace / 'build/native-lifecycle-private'
                    shutil.copytree(data, target, symlinks=True, copy_function=copy_file)
                    assert inventory(data) == original_state == inventory(target)
            self.before = self.immutable()
            (self.job / 'manifest.json').write_bytes(encoded(self.before))
            self.manifest_sha256 = hashlib.sha256(encoded(self.before)).hexdigest()
        except BaseException:
            print('Owned failed model workspace retained:', self.job, flush=True)
            self.close()
            raise

    def immutable(self):
        data = tree_inventory(self.workspace)
        return {p: v for p, v in data.items() if p != 'build/linux-job.status'
                and p not in {'build/' + n for n in OUTPUTS}
                and p != 'build/native-lifecycle-private' and not p.startswith('build/native-lifecycle-private/')}

    def verify(self):
        assert sha(self.runner_path) == self.runner_sha256, 'Model runner changed during job'
        assert self.before == self.immutable(), 'Model input manifest changed: ' + str(self.job)

    def collect(self, output_root=None):
        self.verify()
        if output_root is None:
            output_root = ROOT / 'build'
        else:
            output_root = Path(output_root)
            assert output_root.parent in [ROOT / 'build/model-draft-results', ROOT / 'build/model-results']
            assert re.fullmatch(r'run-[0-9a-f]{24}', output_root.name) and not output_root.is_symlink()
            output_root.parent.mkdir(mode=0o700, exist_ok=True)
            output_root.mkdir(mode=0o700)
        # Validate every result before replacing any caller-visible output.
        selected, total = {}, 0
        for name, cap in OUTPUTS.items():
            source = self.workspace / 'build' / name
            if not source.exists() and not source.is_symlink():
                continue
            s = regular(source, cap)
            total += s.st_size
            assert total <= 128 * 1024 * 1024
            target = output_root / name
            assert not target.is_symlink()
            if target.exists():
                regular(target, cap)
            selected[name] = source
        state_source = self.workspace / 'build/native-lifecycle-private'
        if self.state_dir is not None and state_source.exists():
            assert state_source.is_dir() and not state_source.is_symlink()
            state = inventory(state_source)
            assert len(state) <= 100 and all(x['type'] in ['directory', 'file'] for x in state.values())
            assert sum(x.get('bytes', 0) for x in state.values()) <= 8 * 1024 * 1024
            for p, entry in state.items():
                if entry['type'] == 'file':
                    regular(state_source / p, 8 * 1024 * 1024)
        else:
            assert not state_source.exists() and not state_source.is_symlink(), 'Unexpected model state output'
        results = {}
        for name, source in selected.items():
            target = output_root / name
            temporary = output_root / ('.model-output-' + secrets.token_hex(12))
            try:
                copy_file(source, temporary)
                assert sha(temporary) == sha(source)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
            results[name] = sha(target)
        if self.state_dir is not None:
            source = self.workspace / 'build/native-lifecycle-private'
            if source.exists():
                assert source.is_dir() and not source.is_symlink()
                state = inventory(source)
                assert len(state) <= 100 and all(x['type'] in ['directory', 'file'] for x in state.values())
                assert sum(x.get('bytes', 0) for x in state.values()) <= 8 * 1024 * 1024
                data, pending = self.state_dir / 'data', self.state_dir / 'pending'
                assert not pending.exists() and not pending.is_symlink()
                shutil.copytree(source, pending, copy_function=copy_file)
                assert inventory(pending) == state
                old = self.state_dir / 'previous'
                assert not old.exists()
                if data.exists():
                    data.rename(old)
                pending.rename(data)
                if old.exists():
                    shutil.rmtree(old)
        return results

    def close(self):
        if self.state_fd is not None:
            os.close(self.state_fd)
            self.state_fd = None
        if self.ok:
            assert self.job.parent == ROOT / 'build/casefs/model-private' and not self.job.is_symlink()
            assert json.loads((self.job / 'owner.json').read_text())['job'] == self.job.name
            shutil.rmtree(self.job)


def cleanup_state(state_id):
    """Remove only the completed caller's marked synthetic group, never globals."""
    assert re.fullmatch(r'state-[0-9a-f]{24}', state_id)
    path = ROOT / 'build/model-state-private' / state_id
    assert path.is_dir() and not path.is_symlink()
    regular(path / 'owner.json', 1024)
    assert json.loads((path / 'owner.json').read_text()) == dict(state_id=state_id, purpose='synthetic-model-lifecycle')
    fd = os.open(path / 'lock', os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert not any((path / p).exists() or (path / p).is_symlink() for p in ['pending', 'previous'])
        shutil.rmtree(path)
    finally:
        os.close(fd)


def run_model(name, timeout=55, phase=None, state_id=None, guest_script=None, cancel=None, receipt=None, output_root=None, on_started=None):
    assert 1 <= timeout <= 180
    slot = acquire_slot(cancel)
    job, proc, console = None, None, bytearray()
    try:
        job = ModelJob(name, phase, state_id, guest_script)
        if receipt is not None:
            receipt.update(job=job.job.relative_to(ROOT).as_posix(), name=name, phase=phase,
                           runner_sha256=job.runner_sha256, outcome='STARTED')
        job.verify()
        args = [str(job.workspace / ('build/tools/' + x)) for x in ['LinuxBuilder', 'linux-Image', 'linux-initramfs.gz']]
        args.append(str(job.workspace))
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                env=dict(os.environ, LOCALMOD_TEST_CPUS='1'), pass_fds=(slot,))
        stream = selectors.DefaultSelector()
        stream.register(proc.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout
        status = job.workspace / 'build/linux-job.status'
        try:
            if on_started is not None:
                on_started(proc.pid, job)
            while time.monotonic() < deadline:
                if cancel is not None and cancel.is_set():
                    raise InterruptedError('Owned model VM cancelled')
                for key, _ in stream.select(.1):
                    part = key.fileobj.read1(65536)
                    if part:
                        console.extend(part)
                        assert len(console) <= 8 * 1024 * 1024
                        assert b'Internal error: Oops' not in console and b'Kernel panic - not syncing' not in console
                    else:
                        stream.unregister(key.fileobj)
                if status.exists() or proc.poll() is not None:
                    break
            else:
                raise TimeoutError('Private model VM exceeded time limit')
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            stream.close()
            os.set_blocking(proc.stdout.fileno(), False)
            drain_end = time.monotonic() + .5
            while time.monotonic() < drain_end and len(console) <= 8 * 1024 * 1024:
                part = proc.stdout.read1(min(65536, 8 * 1024 * 1024 + 1 - len(console)))
                if part == b'':
                    break
                if part:
                    console.extend(part)
                else:
                    time.sleep(.01)
            proc.stdout.close()
            (job.job / 'console.log').write_bytes(bytes(console).replace(b'\r', b''))
        assert len(console) <= 8 * 1024 * 1024
        regular(status, 16)
        assert status.read_text().strip() == '0', 'Private model job failed: ' + str(job.job)
        results = job.collect(output_root)
        job.ok = True
        if receipt is not None:
            receipt.update(job=job.job.relative_to(ROOT).as_posix(), name=name, phase=phase,
                           manifest_sha256=job.manifest_sha256, input_sha256=job.sources,
                           runner_sha256=job.runner_sha256,
                           named_output_sha256=results, checkout_exported=False,
                           immutable_inputs_verified=True, guest_network_devices=0, cpus=1, memory_mib=1024,
                           state_id=state_id, state_lock_exclusive=state_id is not None,
                           output_root=str(Path(output_root).relative_to(ROOT)) if output_root is not None else 'build',
                           console_sha256=sha(job.job / 'console.log'), outcome='PASS')
        return bytes(console).decode('utf-8', errors='replace').replace('\r', '')
    except BaseException as error:
        if job is not None:
            print('Owned failed model workspace retained:', job.job, flush=True)
            if receipt is not None:
                receipt.update(outcome='FAIL', error_type=type(error).__name__, workspace_retained=True)
        raise
    finally:
        if job is not None:
            job.close()
        os.close(slot)
