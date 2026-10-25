#!/usr/bin/env python3
"""Stage the official rootfs and a narrowly scoped software-center overlay."""
import hashlib
import json
import os
import shutil
import stat
import argparse
from pathlib import Path

root=Path(__file__).resolve().parent.parent
official=root/'build/casefs/official_rootfs'
donor=root/'build/casefs/koolcenter_rootfs'
stage=root/'build/casefs/rootfs'
ap=argparse.ArgumentParser();ap.add_argument('--refresh-generated-stage',action='store_true');args=ap.parse_args()
if args.refresh_generated_stage and stage.exists():
    assert json.loads((stage/'rom/etc/localmod-release.json').read_text())['variant']=='localmod1'
    assert stage.resolve()==root/'build/casefs/rootfs' and not stage.is_symlink()
    shutil.rmtree(stage)
assert not stage.exists(), 'Staging directory already exists; keep it for review'
assert (official/'usr/lib/xtables/libxt_tos.so').read_bytes()!=(official/'usr/lib/xtables/libxt_TOS.so').read_bytes(), 'A case-sensitive build filesystem is required'
shutil.copytree(official,stage,symlinks=True)
meta=json.loads((root/'upstream/official/metadata.json').read_text())
donor_meta=json.loads((root/'upstream/koolcenter/metadata.json').read_text())

def put(source,path,mode):
    target=stage/path
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.is_symlink():target.unlink()
    shutil.copyfile(source,target)
    meta['/'+path]={'mode':stat.S_IFREG|mode,'uid':0,'gid':0,'inum':-1,'nlink':1,'xattr_count':0}

core='rom/etc/koolshare'
shutil.copytree(donor/core,stage/core,symlinks=True)
for path,entry in donor_meta.items():
    if path.startswith('/'+core):meta[path]=entry
# The donor's unauthenticated LAN debug/reset server and Merlin-specific
# bootstrap are incompatible with this official base. Keep the scoped launcher.
for relative in ['init.d/V02debug.sh','scripts/ks_debug.sh','bin/kscore.sh','perp/.control/perpd.pid']:
    (stage/core/relative).unlink(missing_ok=True)
for file in ['usr/bin/skipd','usr/bin/dbus']:
    assert not (stage/file).exists()
    put(donor/file,file,0o755)
link=stage/'koolshare'
assert not link.exists() and not link.is_symlink()
link.symlink_to('jffs/.koolshare')
meta['/koolshare']={'mode':stat.S_IFLNK|0o777,'uid':0,'gid':0,'inum':-1,'nlink':1,'xattr_count':0}
put(official/'usr/sbin/httpd','usr/libexec/localmod/httpd.vendor',0o500)
put(root/'build/httpd-launcher','usr/sbin/httpd',0o500)
put(root/'build/init-launcher','sbin/init',0o500)
put(root/'build/httpd_bridge.so','usr/lib/localmod/httpd_bridge.so',0o444)
put(root/'sources/localmod/bootstrap.sh','usr/libexec/localmod/bootstrap.sh',0o755)

base=stage/core/'scripts/base.sh'
text=base.read_text().replace('curl -X POST -d "$ARG0" http://$LANIP:3030/_resp/$ID',
    'curl --noproxy "*" --local-port 600-1023 -X POST -d "$ARG0" http://127.0.0.1:3032/_resp/$ID')
assert ':3030/_resp/' not in text
base.write_text(text)
perp=stage/core/'perp/httpdb/rc.main'
text=perp.read_text()
assert 'exec httpdb' in text
perp.write_text(text.replace('exec httpdb','exec httpdb -p 127.0.0.1:3032 -r 127.0.0.1:80'))
installer=stage/core/'scripts/ks_app_install.sh'
text=installer.read_text().replace('--no-check-certificate ','')
needle='install_ks_module() {'
assert needle in text
text=text.replace(needle,needle+'''
 if [ "${softcenter_installing_todo}" = "softcenter" ] || [ "${softcenter_installing_todo}" = "koolcenter" ]; then
  echo_date "此试验官改的软件中心核心由固件构建维护；请通过固件升级更新核心。普通插件可单独安装。"
  quit_ks_install
 fi
''',1)
installer.write_text(text)
state=stage/'www/state.js'
state.write_text(state.read_text()+'''
// localmod-software-center-entry: integrate with the stock asynchronous menu.
(function () {
 var render = showMenuTree;
 showMenuTree = function (list, exclude) {
  if (!Array.isArray(list)) return render(list, exclude);
  var menus = list.slice();
  var tabs = [{url:'Module_Softcenter.asp',tabName:'软件中心'},
              {url:'Module_Localmod.asp',tabName:'版本说明'}];
  if (/^Module_/.test(current_url) && current_url !== 'Module_Softcenter.asp' && current_url !== 'Module_Localmod.asp') {
   tabs.push({url:current_url,tabName:'__HIDE__'});
  }
  menus.push({menuName:'软件中心',index:'menu_Localmod',tab:tabs});
  return render(menus, exclude);
 };
})();
''')
put(root/'sources/localmod/Module_Localmod.asp','www/Module_Localmod.asp',0o644)
ui=stage/core/'res/soft-v19/assets/index.3d07b566.js'
text=ui.read_text()
assert 'href:"http://"+a.netaddr+":3032"' in text
text=text.replace('href:"http://"+a.netaddr+":3032"','href:"/Module_Localmod.asp"')
ui.write_text(text)
release={'base':'ASUS 3.0.0.4.388_24437-g81951d7','variant':'localmod1','status':'EXPERIMENTAL_NOT_DEVICE_TESTED',
         'software_center':'KoolCenter 1.9.50 from 388.11_0-20260429',
         'uu':'vendor files retained; service operation requires device verification',
         'source_httpd_sha256':hashlib.sha256((official/'usr/sbin/httpd').read_bytes()).hexdigest()}
release_file=stage/'rom/etc/localmod-release.json'
release_file.write_text(json.dumps(release,ensure_ascii=False,indent=2)+'\n')
meta['/rom/etc/localmod-release.json']={'mode':stat.S_IFREG|0o444,'uid':0,'gid':0,'inum':-1,'nlink':1,'xattr_count':0}

# Preserve regular-file hardlinks exported from UBIFS. A directory copy alone
# would silently convert these to independent inodes.
groups={}
for path,m in meta.items():
    if m['inum']>=0 and stat.S_ISREG(m['mode']):
        origin='donor' if path.startswith('/'+core) else 'official'
        groups.setdefault((origin,m['inum']),[]).append(stage/path.lstrip('/'))
for paths in groups.values():
    existing=[p for p in paths if p.is_file() and not p.is_symlink()]
    for p in existing[1:]:
        assert p.read_bytes()==existing[0].read_bytes()
        p.unlink();os.link(existing[0],p)

# Rebuild filesystem metadata using the source inode modes instead of macOS defaults.
for p in stage.rglob('*'):
    path='/'+str(p.relative_to(stage))
    if path not in meta:
        meta[path]={'mode':(stat.S_IFLNK|0o777) if p.is_symlink() else
                           (stat.S_IFDIR|0o755) if p.is_dir() else (stat.S_IFREG|0o644),
                    'uid':0,'gid':0,'inum':-1,'nlink':1,'xattr_count':0}
# All source owners are root. Copy exact inode modes here, then let mkfs -U
# squash the host's uid/gid. A device-table entry per hardlink alias is rejected
# by mkfs.ubifs after the first alias consumes that inode's entry.
for path,m in meta.items():
    p=stage/path.lstrip('/')
    if p.exists() and not p.is_symlink():os.chmod(p,m['mode']&0o7777)
table=[]
for path,m in sorted(meta.items()):
    mode=m['mode'];p=stage/path.lstrip('/')
    if not p.exists() and not p.is_symlink():continue
    if stat.S_ISLNK(mode):continue
    kind='d' if stat.S_ISDIR(mode) else 'f'
    assert stat.S_ISDIR(mode) or stat.S_ISREG(mode), (path,oct(mode))
    assert m['uid']==m['gid']==0 and m['xattr_count']==0
    table.append(f"{path} {kind} {mode&0o7777:o} 0 0 0 0 - - -")
(root/'build/device_table.txt').write_text('\n'.join(table)+'\n')
(root/'build/staged_metadata.json').write_text(json.dumps(meta,indent=2))

def entry(p):
    if p.is_symlink():return {'link':os.readlink(p)}
    if p.is_file():return {'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    return {'directory':True}
changes=[]
for p in sorted(stage.rglob('*')):
    relative=p.relative_to(stage);original=official/relative
    now=entry(p)
    if not original.exists() and not original.is_symlink():changes.append({'path':str(relative),'change':'added',**now})
    elif now!=entry(original):changes.append({'path':str(relative),'change':'modified',**now})
assert (stage/'sbin/rc').read_bytes()==(official/'sbin/rc').read_bytes()
assert (stage/'www/UUAccelerator.asp').read_bytes()==(official/'www/UUAccelerator.asp').read_bytes()
for p in (official/'lib/modules').rglob('*'):
    if p.is_file() and not p.is_symlink():assert p.read_bytes()==(stage/p.relative_to(official)).read_bytes()
(root/'build/changes.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2))
print('staged entries',len(meta),'changes',len(changes),'rc, UU page, all kernel modules retained')
