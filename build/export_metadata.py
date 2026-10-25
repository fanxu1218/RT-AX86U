#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from ubireader.ubi_io import ubi_file
from ubireader.ubifs import ubifs, walk

ap=argparse.ArgumentParser();ap.add_argument('volume',type=Path);ap.add_argument('out',type=Path)
args=ap.parse_args()
image=ubifs(ubi_file(str(args.volume),126976))
inodes={};bad=[]
walk.index(image,image.master_node.root_lnum,image.master_node.root_offs,inodes,bad)
assert not bad
out={}
def visit(number,path):
    node=inodes[number];ino=node['ino']
    out[path]={'inum':number,'mode':ino.mode,'uid':ino.uid,'gid':ino.gid,
               'nlink':ino.nlink,'xattr_count':getattr(ino,'xattr_cnt',0)}
    for dent in node.get('dent',[]):
        visit(dent.inum,path.rstrip('/')+'/'+dent.name)
visit(1,'/')
args.out.write_text(json.dumps(out,indent=2))
print('inodes',len(out),'nonroot',sum(x['uid']!=0 or x['gid']!=0 for x in out.values()),
      'xattrs',sum(x['xattr_count'] for x in out.values()))
