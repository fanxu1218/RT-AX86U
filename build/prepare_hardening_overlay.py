#!/usr/bin/env python3
"""Assemble new owned helpers in guest RAM; keep the published stage intact."""
from device_config import compiler_flags
import os,subprocess
from pathlib import Path
from check_installer_boundaries import overlay,sha,ROOT

def prepare_resources():
 os.chdir(ROOT);overlay();folder=ROOT/'build/hardening-overlay'
 flags=['sources/zig-aarch64-macos-0.15.2/zig','cc',*compiler_flags(),'-O2','-s']
 for name,src,extra in [('localmod-event','event.c',['sources/localmod/runtime.c'])]:
  p=folder/'usr/libexec/localmod'/name;subprocess.run(flags+['-o',str(p),'sources/localmod/'+src]+extra,check=True);p.chmod(0o755)
 p=folder/'usr/libexec/localmod/bootstrap.sh';p.write_bytes((ROOT/'sources/localmod/bootstrap.sh').read_bytes());p.chmod(0o755)
 return {str(p.relative_to(folder)):sha(p) for p in folder.rglob('*') if p.is_file()}
