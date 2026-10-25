#!/usr/bin/env python3
"""Run one bounded build job, then release the temporary Linux VM."""
import subprocess
import time
from pathlib import Path

root = Path(__file__).resolve().parent.parent
status = root/'build/linux-job.status'
status.unlink(missing_ok=True)
with (root/'build/linux_builder.log').open('w') as log:
    proc = subprocess.Popen([str(root/'build/tools/LinuxBuilder'),str(root/'build/tools/linux-Image'),
                             str(root/'build/tools/linux-initramfs.gz'),str(root)],stdout=log,stderr=log)
    deadline = time.monotonic()+55
    while time.monotonic()<deadline and proc.poll() is None and not status.exists():
        time.sleep(.2)
    if proc.poll() is None:
        proc.terminate()
        try: proc.wait(timeout=3)
        except subprocess.TimeoutExpired: proc.kill();proc.wait()
if not status.exists() or status.read_text().strip()!='0':
    print((root/'build/linux_builder.log').read_text())
    raise SystemExit('Linux job did not succeed')
print((root/'build/linux_builder.log').read_text())
