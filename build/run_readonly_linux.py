#!/usr/bin/env python3
"""Run unmodified third-party scripts with no host-writable share or guest NIC."""
import selectors
import subprocess
import time
from pathlib import Path


def run(log_path, timeout=270):
    root = Path(__file__).resolve().parent.parent
    args = [str(root / 'build/tools/LinuxBuilder'), str(root / 'build/tools/linux-Image'),
            str(root / 'build/tools/linux-initramfs.gz'), str(root), '--readonly']
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stream = selectors.DefaultSelector()
    stream.register(proc.stdout, selectors.EVENT_READ)
    data = bytearray()
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            for key, _ in stream.select(.2):
                chunk = key.fileobj.read1(65536)
                if not chunk:
                    stream.unregister(key.fileobj)
                    break
                data.extend(chunk)
                Path(log_path).write_bytes(data)
                if len(data) > 8 * 1024 * 1024:
                    raise RuntimeError('guest console exceeded bounded output limit')
            if any(b'\nLINUX_READONLY_JOB_STATUS=' + value in data for value in (b'0', b'1')):
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
    text = data.decode('utf-8', errors='replace').replace('\r\n', '\n')
    if '\nLINUX_READONLY_JOB_STATUS=0' not in text:
        raise RuntimeError('read-only job failed; inspect ' + str(log_path))
    # Serial consoles emit CRLF. Keep reviewable logs in the repository's LF format.
    Path(log_path).write_text(text.rstrip('\n') + '\n')
    return text


if __name__ == '__main__':
    print(run(Path(__file__).resolve().parent / 'real_plugins_vm.log'))
