#!/usr/bin/env python3
"""Reproduce pinned upstream HND packaging recipes without running vendor code."""
import gzip
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path
from prepare_real_plugins import inspect

ROOT=Path(__file__).resolve().parent.parent
sha=lambda b:hashlib.sha256(b).hexdigest()


def fetch(path,url,digest):
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists() or sha(path.read_bytes())!=digest:
        temp=path.with_suffix('.download')
        subprocess.run(['curl','--fail','--location','--silent','--show-error','--max-time','45','--output',str(temp),url],check=True)
        assert sha(temp.read_bytes())==digest,url
        temp.replace(path)
    return path.read_bytes()


def prepare():
    manifest=json.loads((ROOT/'build/extended_plugin_sources.json').read_text())
    for p in manifest['packages']:
        path=ROOT/p['path']
        if p['packaging']=='original-published-archive':
            data=fetch(path,p['source_url'],p['sha256'])
        else:
            files={}
            prefix=p['module']+'/'+p['module']+'/'
            for f in p['source_files']:
                data=fetch(ROOT/'sources/extended-plugin-tree'/f['path'],
                           f"https://raw.githubusercontent.com/koolshare/rogsoft/{p['source_commit']}/{f['path']}",f['sha256'])
                if f['path'].startswith(prefix):files[f['path'][len(prefix):]]=(data,int(f['mode'],8)&0o777)
                if f['path']==p['module']+'/build.sh':
                    assert ('VERSION="'+p['version']+'"').encode() in data
            # Exact upstream build.sh/build_base.sh recipe: HND metadata and,
            # for FRPC, select the original ARM binary under its runtime name.
            files['version']=((p['version']+'\n').encode(),0o644)
            files['.valid']=(b'hnd\n',0o644)
            if p['module']=='frpc':
                binary=files['bin/frpc-arm'][0]
                files={n:v for n,v in files.items() if not n.startswith('bin/')}
                files['bin/frpc']=(binary,0o755)
            out=io.BytesIO()
            with tarfile.open(fileobj=out,mode='w',format=tarfile.USTAR_FORMAT) as t:
                for name,(data,mode) in sorted(files.items()):
                    h=tarfile.TarInfo(p['module']+'/'+name);h.mode=mode;h.size=len(data);t.addfile(h,io.BytesIO(data))
            out2=io.BytesIO()
            with gzip.GzipFile(fileobj=out2,mode='wb',filename='',mtime=0) as z:z.write(out.getvalue())
            data=out2.getvalue();path.write_bytes(data)
            if p.get('sha256'):assert sha(data)==p['sha256']
        p['sha256']=sha(data);p['md5']=hashlib.md5(data).hexdigest()
        details=inspect(data,p['module']);assert details['internal_version']==p['version'];p.update(details)
        p['runtime_files']=dict(p['files'])
        for name,rule in p.get('runtime_adaptations',{}).items():
            assert p['files'][name]==rule['input_sha256']
            p['runtime_files'][name]=rule['output_sha256']
    (ROOT/'build/extended_plugin_inputs.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    print('Verified',len(prepare()['packages']),'extended HND package versions')
