#!/usr/bin/env python3
"""Re-extract both inputs into the mounted case-sensitive build volume."""
import json
from pathlib import Path
from ubireader.ubi_io import ubi_file
from ubireader.ubifs import ubifs
from ubireader.ubifs.output import extract_files

root=Path(__file__).resolve().parent.parent
base=root/'build/casefs'
assert base.is_mount(), 'Mount the case-sensitive build volume first'
for label in ['official','koolcenter']:
    target=base/(label+'_rootfs')
    assert not target.exists(), f'{target} already exists'
    target.mkdir()
    image=ubifs(ubi_file(str(root/f'upstream/{label}/rootfs_ubifs'),126976))
    extract_files(image,str(target))
    expected=set(json.loads((root/f'upstream/{label}/metadata.json').read_text()))
    found={'/'+str(p.relative_to(target)) for p in target.rglob('*')}|{'/'}
    assert found==expected, {'missing':sorted(expected-found),'extra':sorted(found-expected)}
    print(label,'all',len(found),'paths restored, including case-distinct netfilter modules')
