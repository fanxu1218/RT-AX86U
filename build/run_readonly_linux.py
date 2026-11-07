#!/usr/bin/env python3
"""Run unmodified third-party scripts with no host-writable share or guest NIC."""
import os
import selectors
import subprocess
import time
from pathlib import Path


def _run(log_path, root, timeout=270, state_disk=None, expect_cut=False,
         cancel=None, cpus=2, on_started=None, slot_fd=None):
    args = [str(root / 'build/tools/LinuxBuilder'), str(root / 'build/tools/linux-Image'),
            str(root / 'build/tools/linux-initramfs.gz'), str(root), '--readonly']
    if state_disk is not None:
        disk = Path(state_disk).resolve()
        assert disk.parent == (root / 'build/interrupt-private').resolve()
        assert disk.suffix == '.img' and disk.stat().st_size == 96 * 1024 * 1024
        args.append(str(disk))
    env = dict(os.environ)
    assert cpus in (1, 2)
    env["LOCALMOD_TEST_CPUS"] = "1" if state_disk is not None else str(cpus)
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                            pass_fds=() if slot_fd is None else (slot_fd,))
    stream = selectors.DefaultSelector()
    stream.register(proc.stdout, selectors.EVENT_READ)
    data = bytearray()
    deadline = time.monotonic() + timeout
    guest_fault = None
    try:
        if on_started is not None:
            on_started(proc.pid)
        while time.monotonic() < deadline:
            if cancel is not None and cancel.is_set():
                raise InterruptedError('Owned read-only VM cancelled')
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


def run(log_path, timeout=270, state_disk=None, expect_cut=False, *,
        sealed=None, cancel=None, cpus=2, on_started=None, receipt=None):
    """Seal before launch; cancellation only terminates this owned VM process.

    Legacy checker preparation remains serial. The shard executor prepares all
    jobs first and supplies separate sealed inputs before running at most two.
    """
    import json
    from sealed_vm import SealedWorkspace, acquire_slot
    assert 0 < timeout <= 7200
    log_path = Path(log_path)
    slot = None
    job = sealed
    try:
        slot = acquire_slot(cancel)
        if job is None:
            job = SealedWorkspace(state_disk=state_disk)
        else:
            assert state_disk is None, 'State must be attached when sealing'
        job.verify()
        job.started = True
        result = _run(log_path, job.workspace, timeout=timeout, state_disk=job.state,
                      expect_cut=expect_cut, cancel=cancel, cpus=cpus, on_started=on_started, slot_fd=slot)
        job.verify()
        job.ok = True
        return result
    finally:
        try:
            if job is not None:
                details = job.receipt()
                details.update(cpus=1 if job.state is not None else cpus, memory_mib=1024,
                               timeout_seconds=timeout, sealed_inputs_verified_before_and_after=job.ok)
                if receipt is not None:
                    receipt.update(details)
                log_path.with_suffix(log_path.suffix + '.vm.json').write_text(json.dumps(details, indent=2) + '\n')
                job.close()
        finally:
            if slot is not None:
                os.close(slot)


if __name__ == '__main__':
    print(run(Path(__file__).resolve().parent / 'real_plugins_vm.log'))
