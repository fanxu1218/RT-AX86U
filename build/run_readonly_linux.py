#!/usr/bin/env python3
"""Run unmodified third-party scripts with no host-writable share or guest NIC."""
import os
import selectors
import subprocess
import time
from pathlib import Path


def run(log_path, timeout=270, state_disk=None, expect_cut=False):
    root = Path(__file__).resolve().parent.parent
    args = [str(root / 'build/tools/LinuxBuilder'), str(root / 'build/tools/linux-Image'),
            str(root / 'build/tools/linux-initramfs.gz'), str(root), '--readonly']
    if state_disk is not None:
        disk = Path(state_disk).resolve()
        assert disk.parent == (root / 'build/interrupt-private').resolve()
        assert disk.suffix == '.img' and disk.stat().st_size == 96 * 1024 * 1024
        args.append(str(disk))
    env = dict(os.environ)
    if state_disk is not None:
        env["LOCALMOD_TEST_CPUS"] = "1"
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    stream = selectors.DefaultSelector()
    stream.register(proc.stdout, selectors.EVENT_READ)
    data = bytearray()
    deadline = time.monotonic() + timeout
    guest_fault = None
    try:
        while time.monotonic() < deadline:
            for key, _ in stream.select(.2):
                chunk = key.fileobj.read1(65536)
                if not chunk:
                    stream.unregister(key.fileobj)
                    break
                data.extend(chunk)
                Path(log_path).write_bytes(data)
                if b'Internal error: Oops' in data or b'Kernel panic - not syncing' in data:
                    if guest_fault is None:
                        guest_fault = time.monotonic()
                if len(data) > 8 * 1024 * 1024:
                    raise RuntimeError('guest console exceeded bounded output limit')
            if guest_fault is not None and time.monotonic() - guest_fault > 2:
                raise RuntimeError('test guest kernel fault before completion; inspect ' + str(log_path))
            if any(b'\nLINUX_READONLY_JOB_STATUS=' + value in data for value in (b'0', b'1')):
                break
            if expect_cut and b'\nINTERRUPT_CUT_READY\r\n' in data:
                break
            if not stream.get_map():
                break
        else:
            raise RuntimeError('read-only VM exceeded time limit')
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        stream.close()
        proc.stdout.close()
        Path(log_path).write_bytes(data)
    text = data.decode('utf-8', errors='replace').replace('\r\n', '\n').replace('\r', '')
    if guest_fault is not None:
        raise RuntimeError('test guest kernel fault before completion; inspect ' + str(log_path))
    if (expect_cut and '\nINTERRUPT_CUT_READY\n' not in text) or (not expect_cut and '\nLINUX_READONLY_JOB_STATUS=0' not in text):
        raise RuntimeError('read-only job failed; inspect ' + str(log_path))
    # Serial consoles emit CRLF. Keep reviewable logs in the repository's LF format.
    Path(log_path).write_text(text.rstrip('\n') + '\n')
    return text


if __name__ == '__main__':
    print(run(Path(__file__).resolve().parent / 'real_plugins_vm.log'))
