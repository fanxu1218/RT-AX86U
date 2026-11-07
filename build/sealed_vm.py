#!/usr/bin/env python3
"""Owned, manifest-checked VM inputs; never export the whole checkout."""
import ctypes
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import time

ROOT = Path(__file__).resolve().parent.parent
COMMON = ['linux_real_plugins_job.sh', 'real_plugins_setup.sh', 'native-nvram', 'native_defaults.bin',
          'native_shadow_hash.txt', 'httpd_bridge.so', 'rc_bridge.so',
          'native_hw_fixture.so', 'native_uu_transport.so', 'soak-init-fixture']
OPTIONAL = ['test-real-plugins', 'test-fancyss', 'test-interrupt', 'test-https-stability',
            'test-soak', 'test-health', 'test-installer-boundaries', 'test-resource-bounds',
            'test-uu-recovery', 'test-history', 'history_fault_fixture.so',
            'txn_fault_fixture.so', 'https_trace_fixture.so', 'httpd_bridge_next.so',
            'httpd_tls_cache_fixture.so', 'memory-exec-fixture', 'relay-idle-fixture',
            'log-limit-bounds-fixture', 'event-bounds-fixture', 'barrier-bounds-fixture',
            'plugin-txn-r5-baseline',
            'irq-tls-probe', 'irq-old-httpd-bridge',
            'history-phase', 'interrupt-phase.json', 'soak-plan.json']


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def inventory(folder):
    """Do not follow symlinks (including the vendor's absolute links)."""
    result = {}
    def visit(path):
        s = path.lstat()
        entry = dict(mode=stat.S_IMODE(s.st_mode))
        if stat.S_ISLNK(s.st_mode):
            entry.update(type='link', target=os.readlink(path))
        elif stat.S_ISREG(s.st_mode):
            entry.update(type='file', bytes=s.st_size, sha256=sha(path))
        elif stat.S_ISDIR(s.st_mode):
            entry.update(type='directory')
        else:
            raise ValueError('Unsupported exported file type: ' + str(path))
        result[path.relative_to(folder).as_posix()] = entry
        if entry['type'] == 'directory':
            for child in sorted(path.iterdir()):
                visit(child)
    for path in sorted(folder.iterdir()):
        visit(path)
    return result


def copy_file(source, target):
    # APFS clones have independent inodes and preserve later-write isolation.
    # Hard links are deliberately not used for immutable inputs.
    if os.uname().sysname == 'Darwin':
        libc = ctypes.CDLL(None, use_errno=True)
        clone = libc.clonefile
        clone.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
        clone.restype = ctypes.c_int
        if clone(os.fsencode(source), os.fsencode(target), 0) == 0:
            shutil.copystat(source, target, follow_symlinks=False)
            return target
        if ctypes.get_errno() not in (errno.EXDEV, errno.ENOTSUP, errno.EINVAL):
            raise OSError(ctypes.get_errno(), 'clonefile', str(source))
    return shutil.copy2(source, target, follow_symlinks=False)


class SealedWorkspace:
    def __init__(self, phase=None, overrides=None, state_disk=None, guest_job=None):
        assert (ROOT / 'build/casefs').is_mount(), 'Case-sensitive build volume required'
        if phase is None:
            phase = (ROOT / 'build/real-plugin-phase').read_text().strip()
        assert re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', phase)
        self.phase, self.ok, self.started = phase, False, False
        self.state_fd = None
        self.original_disk = None
        parent = ROOT / 'build/casefs/sealed-private'
        assert not parent.is_symlink()
        parent.mkdir(mode=0o700, exist_ok=True)
        parent.chmod(0o700)
        assert shutil.disk_usage(parent).free >= 256 * 1024 * 1024, 'Insufficient scratch space; retained jobs were not removed'
        self.job = parent / ('job-' + secrets.token_hex(12))
        self.job.mkdir(mode=0o700)
        self.workspace = self.job / 'workspace'
        self.workspace.mkdir(mode=0o700)
        self.state = None
        self.inputs = {}
        self.before = None
        (self.job / 'owner.json').write_bytes(encoded(dict(schema=1, phase=phase, job=self.job.name)))
        try:
            paths = ['build/casefs/rootfs'] + ['build/' + p for p in COMMON]
            component_phase=phase in {'candidate-merlin-components','candidate-merlin-system'}
            selected=['test-merlin','merlin-vpn-config-fixture.so','merlin-vpn-config-probe'] if component_phase else OPTIONAL
            paths += ['build/' + p for p in selected if (ROOT / 'build' / p).is_file()]
            paths += ['build/tools/' + p for p in ['LinuxBuilder', 'linux-Image', 'linux-initramfs.gz']]
            if phase.startswith('hardening-'):
                paths.append('build/hardening-overlay')
            for name in ['real_plugin_inputs.json', 'fancyss_inputs.json', 'extended_plugin_inputs.json']:
                if component_phase:
                    continue
                path = ROOT / 'build' / name
                if not path.is_file():
                    continue
                paths.append('build/' + name)
                for package in json.loads(path.read_text())['packages']:
                    for key in ['path', 'adapted_path']:
                        if key in package:
                            relative = Path(package[key])
                            assert relative.parts[:2] == ('sources', 'realplugins') and '..' not in relative.parts
                            paths.append(relative.as_posix())
            if not component_phase and (ROOT / 'build/installer-boundary-inputs').is_dir():
                paths.append('build/installer-boundary-inputs')
            if phase.endswith('fancyss') or 'fancyss-components' in phase:
                paths.append('sources/extended-plugin-tree')
            if phase == 'candidate-fancyss':
                paths += ['build/softcenter-old-core','build/softcenter-old-inputs.json','build/softcenter_frontend_payloads.json']
            if phase == 'candidate-merlin-probe':
                paths.append('build/casefs/merlin38812_rootfs')
            if phase == 'candidate-merlin-system':
                paths += ['build/merlin-system','build/merlin_nested_initramfs.gz','build/merlin_nested_job.sh']
            for name in sorted(set(paths)):
                source, target = ROOT / name, self.workspace / name
                assert source.exists() and not source.is_symlink(), name
                target.parent.mkdir(parents=True, exist_ok=True)
                if source.is_dir():
                    before = inventory(source)
                    shutil.copytree(source, target, symlinks=True, copy_function=copy_file)
                    assert inventory(source) == before == inventory(target), 'Input changed while sealing: ' + name
                    self.inputs[name] = hashlib.sha256(encoded(before)).hexdigest()
                else:
                    before = sha(source)
                    copy_file(source, target)
                    assert before == sha(source) == sha(target), 'Input changed while sealing: ' + name
                    self.inputs[name] = before
            updates = dict(overrides or {})
            updates['build/real-plugin-phase'] = (phase + '\n').encode()
            if guest_job is not None:
                # Test-only dispatch replacement in this owned export, never in
                # the production image or another job's checkout.
                updates['build/linux_real_plugins_job.sh'] = guest_job
            for name, data in updates.items():
                assert name in {'build/real-plugin-phase', 'build/history-phase', 'build/interrupt-phase.json', 'build/linux_real_plugins_job.sh'}
                target = self.workspace / name
                assert not target.is_symlink()
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            # Persistent state is transferred through a locked, owned 96 MiB
            # fixture only. It is not part of the sealed input manifest.
            if state_disk is not None:
                disk = Path(state_disk)
                assert not disk.is_symlink()
                disk = disk.resolve()
                assert disk.parent == (ROOT / 'build/interrupt-private').resolve() and disk.suffix == '.img'
                self.state_fd = os.open(disk, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
                fcntl.flock(self.state_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                s = os.fstat(self.state_fd)
                assert stat.S_ISREG(s.st_mode) and s.st_uid == os.getuid() and s.st_nlink == 1 and stat.S_IMODE(s.st_mode) == 0o600
                assert s.st_size == 96 * 1024 * 1024
                self.original_disk = (disk, s.st_dev, s.st_ino)
                self.state = self.workspace / 'build/interrupt-private/state.img'
                self.state.parent.mkdir(mode=0o700)
                copy_file(disk, self.state)
            self.before = self.current_inventory()
            assert len(self.before) <= 20000
            assert sum(x.get('bytes', 0) for x in self.before.values()) <= 768 * 1024 * 1024, 'Sealed input size limit exceeded'
            self.manifest_sha256 = hashlib.sha256(encoded(self.before)).hexdigest()
            (self.job / 'manifest.json').write_bytes(encoded(self.before))
            self.verify()
        except BaseException:
            self.close()
            raise

    def current_inventory(self):
        data = inventory(self.workspace)
        # The sole mutable file is the explicitly attached fixture disk. Its
        # size/ownership and exact path remain validated by the VM launcher.
        if self.state is not None:
            key = self.state.relative_to(self.workspace).as_posix()
            s = self.state.lstat()
            assert stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_uid == os.getuid()
            assert s.st_size == 96 * 1024 * 1024 and stat.S_IMODE(s.st_mode) == 0o600
            data[key] = dict(type='owned-state-disk', bytes=96 * 1024 * 1024, mode=0o600)
        return data

    def verify(self):
        assert self.current_inventory() == self.before, 'Sealed VM inputs changed: ' + str(self.job)

    def receipt(self):
        return dict(schema=1, phase=self.phase, sealed_manifest_sha256=self.manifest_sha256,
                    exported_entries=len(self.before), inputs=self.inputs,
                    workspace_path=str(self.workspace.relative_to(ROOT)),
                    state_disk_attached=self.state is not None, state_lock_exclusive=self.state is not None,
                    host_export_readonly=True, guest_network_devices=0,
                    preserved_after_failure=not self.ok)

    def close(self):
        try:
            if self.state_fd is not None and self.started:
                path, dev, ino = self.original_disk
                s = path.lstat()
                assert not path.is_symlink() and (s.st_dev, s.st_ino) == (dev, ino)
                assert self.state.stat().st_size == 96 * 1024 * 1024
                os.lseek(self.state_fd, 0, os.SEEK_SET)
                with self.state.open('rb') as source:
                    while block := source.read(1024 * 1024):
                        while block:
                            n = os.write(self.state_fd, block)
                            assert n > 0
                            block = block[n:]
                os.fsync(self.state_fd)
        finally:
            if self.state_fd is not None:
                os.close(self.state_fd)
                self.state_fd = None
        if self.ok:
            assert self.job.parent == ROOT / 'build/casefs/sealed-private'
            assert re.fullmatch(r'job-[0-9a-f]{24}', self.job.name) and not self.job.is_symlink()
            assert json.loads((self.job / 'owner.json').read_text())['job'] == self.job.name
            shutil.rmtree(self.job)


def acquire_slot(cancel=None, timeout=120):
    """At most two read-only VMs across processes; release via closing the fd."""
    parent = ROOT / 'build/vm-private'
    assert not parent.is_symlink()
    parent.mkdir(mode=0o700, exist_ok=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cancel is not None and cancel.is_set():
            raise InterruptedError('Owned VM cancelled before slot acquisition')
        for index in range(2):
            fd = os.open(parent / ('slot' + str(index)), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
            s = os.fstat(fd)
            try:
                assert stat.S_ISREG(s.st_mode) and s.st_uid == os.getuid() and s.st_nlink == 1 and s.st_size == 0 and stat.S_IMODE(s.st_mode) == 0o600
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except BlockingIOError:
                os.close(fd)
            except BaseException:
                os.close(fd)
                raise
        time.sleep(.1)
    raise TimeoutError('No read-only VM slot available within bounded wait')
