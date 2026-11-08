#!/usr/bin/env python3
"""Portable native-variant syntax/config checks; no vendor inputs or router."""
import ast,json,re,shutil,subprocess,tempfile
from pathlib import Path
from urllib.parse import urlsplit
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def main():
 for p in HERE.glob('*.py'):ast.parse(p.read_text(),filename=str(p))
 for p in [*HERE.glob('*.json'),*HERE.glob('vendor/*.json')]:json.loads(p.read_text())
 release=json.loads((HERE/'release.json').read_text())
 assert release['schema']==1 and release['model']=='RT-AX86U' and release['base']=='3004.388.12_2'
 assert re.fullmatch(r'P[1-9][0-9]*',release['revision'])
 assert re.fullmatch(r'[a-z0-9][a-z0-9._-]{1,79}',release['release_tag'])
 u=urlsplit(release['repository']);assert u.scheme=='https' and u.netloc=='github.com' and len(u.path.strip('/').split('/'))==2 and not u.query and not u.fragment
 zig=ROOT/'sources/zig-aarch64-macos-0.15.2/zig'
 compiler=[str(zig),'cc','-target','arm-linux-gnueabi.2.26','-mcpu=cortex_a53'] if zig.is_file() else [shutil.which('cc') or 'cc']
 with tempfile.TemporaryDirectory(prefix='native-variant-compile-') as temporary:
  for p in HERE.glob('*.c'):subprocess.run([*compiler,'-c','-Werror=implicit-function-declaration',str(p),'-o',str(Path(temporary)/(p.stem+'.o'))],check=True,cwd=ROOT)
 for p in HERE.glob('*.sh'):subprocess.run(['sh','-n',str(p)],check=True)
 for p in HERE.glob('*.go'):subprocess.run(['gofmt','-e',str(p)],stdout=subprocess.DEVNULL,check=True)
 print('PASS native-variant syntax and release metadata; no firmware/runtime/device claim')
if __name__=='__main__':main()
