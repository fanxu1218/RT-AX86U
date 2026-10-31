#!/usr/bin/env python3
"""Stage the official rootfs and a narrowly scoped software-center overlay."""
import hashlib
import json
import os
import shutil
import stat
import argparse
import re
from patch_online_installer import patch_online_installer
from pathlib import Path

root=Path(__file__).resolve().parent.parent
official=root/'build/casefs/official_rootfs'
donor=root/'build/casefs/koolcenter_rootfs'
stage=root/'build/casefs/rootfs'
ap=argparse.ArgumentParser();ap.add_argument('--refresh-generated-stage',action='store_true');args=ap.parse_args()
if args.refresh_generated_stage and stage.exists():
    assert json.loads((stage/'rom/etc/localmod-release.json').read_text())['variant'] in {'localmod1','localmod2'}
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
put(official/'usr/sbin/httpd','usr/libexec/localmod/httpd',0o500)
put(root/'build/httpd-launcher','usr/sbin/httpd',0o500)
put(root/'build/init-launcher','sbin/init',0o500)
put(official/'sbin/rc','usr/libexec/localmod/rc.vendor',0o500)
put(root/'build/rc-launcher','sbin/rc',0o500)
put(root/'build/httpd_bridge.so','usr/lib/localmod/httpd_bridge.so',0o444)
put(root/'build/rc_bridge.so','usr/lib/localmod/rc_bridge.so',0o444)
put(root/'build/localmod-event','usr/libexec/localmod/localmod-event',0o500)
put(root/'build/iptables-restore-launcher','usr/sbin/iptables-restore',0o500)
put(root/'sources/localmod/bootstrap.sh','usr/libexec/localmod/bootstrap.sh',0o755)
put(root/'sources/localmod/dispatch.sh','usr/libexec/localmod/dispatch.sh',0o755)
put(root/'sources/localmod/installer-guard.sh','usr/libexec/localmod/installer-guard.sh',0o755)
put(root/'build/plugin-txn','usr/libexec/localmod/plugin-txn',0o500)
put(root/'sources/localmod/jffsinit.sh','usr/bin/jffsinit.sh',0o755)
put(root/'sources/localmod/kscore.sh',core+'/bin/kscore.sh',0o755)
put(root/'sources/localmod/helper.sh','usr/sbin/helper.sh',0o755)
# The official BusyBox omits tee and xargs. Keep it untouched and expose only the
# required applets from the already pinned HND donor under a private name.
put(donor/'bin/busybox','usr/libexec/localmod/busybox',0o500)
for applet in ['tee', 'xargs']:
    target=stage/'usr/bin'/applet
    assert not target.exists() and not target.is_symlink()
    target.symlink_to('/usr/libexec/localmod/busybox')
    meta['/usr/bin/'+applet]={'mode':stat.S_IFLNK|0o777,'uid':0,'gid':0,'inum':-1,'nlink':1,'xattr_count':0}

# Both old user hooks and the compatibility dispatcher may call a center helper.
# A per-event directory makes each helper run once without rewriting user files.
for name in ['ks-services-start.sh','ks-services-stop.sh','ks-wan-start.sh','ks-nat-start.sh','ks-mount-start.sh','ks-unmount.sh']:
    p=stage/core/'bin'/name
    text=p.read_text();assert text.startswith('#!/bin/sh')
    guard='''
# localmod-event-dedup
if [ -n "$LOCALMOD_EVENT_DIR" ]; then
 case "$LOCALMOD_EVENT_DIR" in /tmp/.localmod/event.*) ;; *) exit 1;; esac
 mkdir "$LOCALMOD_EVENT_DIR/'''+name+'''" 2>/dev/null || exit 0
fi
'''
    text=text.replace('#!/bin/sh','#!/bin/sh\n'+guard,1)
    for variable in ['MOPATH','KSPATH','ACTION']:
        text=re.sub(r'(?m)^(\s*)\$i \$'+variable+r'\s*$',lambda m:m.group(1)+'"$i" "$'+variable+'"',text)
    p.write_text(text)

base=stage/core/'scripts/base.sh'
text=base.read_text().replace('curl -X POST -d "$ARG0" http://$LANIP:3030/_resp/$ID',
    'curl --noproxy "*" --resolve localhost:3032:127.0.0.1 --local-port 600-1023 -X POST -d "$ARG0" http://localhost:3032/_resp/$ID')
assert ':3030/_resp/' not in text
base.write_text(text)
perp=stage/core/'perp/httpdb/rc.main'
text=perp.read_text()
assert 'exec httpdb' in text
perp.write_text(text.replace('exec httpdb','exec httpdb -p 127.0.0.1:3032 -r 127.0.0.1:80'))
installer=stage/core/'scripts/ks_app_install.sh'
text=patch_online_installer(installer.read_text())
installer.write_text(text)
put(root/'sources/localmod/offline-installer.sh',core+'/scripts/ks_tar_install.sh',0o755)

profile=stage/'rom/etc/profile'
assert profile.is_file()
profile.write_text(profile.read_text()+'''
# localmod center tools for SSH sessions
if [ ! -e /jffs/localmod-disabled ] && [ -d /koolshare/bin ]; then
 PATH=/koolshare/bin:/koolshare/scripts:$PATH
 export PATH
fi
''')
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
release={'base':'ASUS 3.0.0.4.388_24437-g81951d7','variant':'localmod2','revision':'r7','status':'EXPERIMENTAL_NOT_DEVICE_TESTED',
         'software_center':'KoolCenter 1.9.50 from 388.11_0-20260429',
         'event_hooks':['init-start','services-start','services-stop','service-event','service-event-end','wan-event','wan-start','firewall-start','nat-start','pre-mount','post-mount','unmount'],
         'postconf':['dnsmasq'],
         'uu':'vendor files retained; service operation requires device verification',
         'source_httpd_sha256':hashlib.sha256((official/'usr/sbin/httpd').read_bytes()).hexdigest()}
release_file=stage/'rom/etc/localmod-release.json'
release_file.write_text(json.dumps(release,ensure_ascii=False,indent=2)+'\n')
meta['/rom/etc/localmod-release.json']={'mode':stat.S_IFREG|0o444,'uid':0,'gid':0,'inum':-1,'nlink':1,'xattr_count':0}
core_id=hashlib.sha256()
for p in sorted((stage/core).rglob('*')):
    core_id.update(str(p.relative_to(stage/core)).encode())
    if p.is_symlink():core_id.update(os.readlink(p).encode())
    elif p.is_file():core_id.update(p.read_bytes())
(stage/'rom/etc/localmod-core-id').write_text(core_id.hexdigest()+'\n')
meta['/rom/etc/localmod-core-id']={'mode':stat.S_IFREG|0o444,'uid':0,'gid':0,'inum':-1,'nlink':1,'xattr_count':0}

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
assert (stage/'usr/libexec/localmod/rc.vendor').read_bytes()==(official/'sbin/rc').read_bytes()
assert (stage/'usr/sbin/xtables-multi').read_bytes()==(official/'usr/sbin/xtables-multi').read_bytes()
assert (stage/'www/UUAccelerator.asp').read_bytes()==(official/'www/UUAccelerator.asp').read_bytes()
for p in (official/'lib/modules').rglob('*'):
    if p.is_file() and not p.is_symlink():assert p.read_bytes()==(stage/p.relative_to(official)).read_bytes()
(root/'build/changes.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2))
print('staged entries',len(meta),'changes',len(changes),'vendor rc/xtables, UU page, all kernel modules retained')
