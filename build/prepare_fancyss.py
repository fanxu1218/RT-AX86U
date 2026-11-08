#!/usr/bin/env python3
"""Pin and adapt upstream Fancyss without executing its files on the host."""
import argparse
import copy
import gzip
import hashlib
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path, PurePosixPath
from device_config import DEVICE, render_source

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / DEVICE['sources']['fancyss']


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def replace(text, old, new, count=1):
    assert text.count(old) == count, (old[:100], text.count(old), count)
    return text.replace(old, new)


def adapt(name, blob):
    if name == 'install.sh':
        text = blob.decode()
        # This plugin must never reclaim another service's data or router logs.
        text = replace(text, '\n\tcleanup_jffs_install_tmp\n',
                       '\n\techo_date "localmod: 保留 UU 安装包和原厂日志，不清理其它服务数据。"\n')
        text = replace(text, '\techo 1 > /proc/sys/vm/drop_caches\n', '')
        text = replace(text, '\tcp -rf /tmp/shadowsocks/ss /koolshare/\n',
                       '\tcp -rf /tmp/shadowsocks/ss /koolshare/\n'
                       '\tcp -f "${DIR}/COPYING" "${DIR}/LOCALMOD-NOTICE.txt" /koolshare/ss/ || exit_install 1\n')
        for function in ['restart_websocketd_async', 'handle_websocketd_after_install']:
            anchor = function + '() {'
            text = replace(text, anchor, anchor + '\n\t# localmod: use authenticated native HTTP callbacks and log polling.\n\treturn 0')
        return text.encode()
    if name == 'ss/ssconfig.sh':
        text = blob.decode()
        text = replace(text, 'start_ws(){',
                       'start_ws(){\n\t# localmod: management stays behind the original ASUS login/TLS.\n\treturn 0')
        return text.encode()
    if name == 'webs/Module_shadowsocks.asp':
        text = blob.decode()
        text = replace(text, 'var ws_enable = 1;', 'var ws_enable = 0; // localmod: native authenticated HTTP', 1)
        text = replace(text, 'function refresh_ws_enable(){\n\tws_enable = 1;',
                       'function refresh_ws_enable(){\n\tws_enable = 0;')
        text = replace(text, 'function is_ws_transport_allowed() {\n\treturn window.location.protocol == "http:";',
                       'function is_ws_transport_allowed() {\n\treturn false; // localmod: use upstream HTTP fallbacks on HTTP and HTTPS')
        return text.encode()
    if name == 'scripts/ss_update.sh':
        # Upstream's self-updater extracts/executes unchecked future installers
        # outside the software-center transaction. Preserve one managed path.
        return '''#!/bin/sh
# localmod adaptation of Fancyss ss_update.sh; upstream GPL-3.0.
. /koolshare/scripts/base.sh
mkdir -p /tmp/upload
printf '%s\\n' 'localmod: 请在软件中心离线安装经过适配和校验的新版包；当前版本不执行插件内自更新。' 'XU6J03M6' > /tmp/upload/ss_log.txt
http_response "$1"
'''.encode()
    if name == 'uninstall.sh':
        # Both regular binaries and system aliases are shared by other plugins.
        # Keeping the alias costs no duplicated JQ binary on Merlin bases.
        text = replace(blob.decode(), 'if [ -n /usr/bin/jq ];then\n\trm -rf /koolshare/bin/jq >/dev/null 2>&1\nfi',
                       '# localmod: retain shared JQ binaries and system aliases for other plugins.')
        return text.encode()
    return blob


def prepare():
    manifest = json.loads(MANIFEST.read_text())
    license_bytes=(ROOT/'sources/localmod/fancyss-LICENSE.txt').read_bytes()
    assert sha(license_bytes)=='3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986'
    for package in manifest['packages']:
        path = ROOT / package['path']
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or sha(path.read_bytes()) != package['sha256']:
            temp = path.with_suffix('.download')
            subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error',
                            '--max-time', '90', '--output', str(temp), package['source_url']], check=True)
            assert sha(temp.read_bytes()) == package['sha256'], 'upstream package digest differs'
            temp.replace(path)
        blob = path.read_bytes()
        assert sha(blob) == package['sha256']
        assert hashlib.md5(blob).hexdigest() == package['upstream_md5']
        files, changes, total, adapted_total, seen = {}, {}, 0, 0, set()
        out = io.BytesIO()
        with tarfile.open(fileobj=io.BytesIO(blob)) as src, tarfile.open(fileobj=out, mode='w', format=tarfile.USTAR_FORMAT) as dst:
            for original in src:
                parts = PurePosixPath(original.name).parts
                assert parts and parts[0] == 'shadowsocks' and '..' not in parts
                assert not original.name.startswith('/') and original.name not in seen
                seen.add(original.name)
                assert original.isdir() or original.isfile()
                assert not original.mode & 0o7000
                item = copy.copy(original)
                item.uid = item.gid = item.mtime = 0
                item.uname = item.gname = ''
                item.pax_headers = {}
                data = None
                if item.isfile():
                    assert item.size <= 16 * 1024 * 1024
                    data = src.extractfile(original).read()
                    total += len(data)
                    assert total <= 32 * 1024 * 1024
                    name = '/'.join(parts[1:])
                    patched = adapt(name, data)
                    files[name] = dict(upstream_sha256=sha(data), sha256=sha(patched))
                    if patched != data:
                        changes[name] = files[name]
                    data = patched
                    adapted_total += len(data)
                    item.size = len(data)
                    if name == 'ss/version':
                        assert data.decode().strip() == package['version']
                    if name == '.valid':
                        assert data == b'hnd_v8\n'
                dst.addfile(item, io.BytesIO(data) if data is not None else None)
            notice=('Fancyss '+package['version']+' HND v8 Full, localmod adaptation 2.\n'
                    'Upstream archive: '+package['source_url']+'\n'
                    'Upstream SHA256: '+package['sha256']+'\n'
                    'Corresponding Fancyss source: '+manifest['source_repository']+'\n'
                    'Adaptation source: https://github.com/fanxu1218/RT-AX86U/blob/main/build/prepare_fancyss.py\n'
                    'Modified files: '+', '.join(sorted(changes))+'\n'
                    'Changes: retain UU/logs; native authenticated HTTP management; managed updates; shared JQ retention.\n'
                    'Original ELF files are unchanged. Component licenses remain applicable.\n'
                    'Reproduce: python3 build/prepare_fancyss.py in the matching localmod source tag.\n').encode()
            for name,data in [('COPYING',license_bytes),('LOCALMOD-NOTICE.txt',notice)]:
                assert name not in files
                item=tarfile.TarInfo('shadowsocks/'+name);item.mode=0o644;item.size=len(data)
                dst.addfile(item,io.BytesIO(data));files[name]=dict(upstream_sha256=None,sha256=sha(data))
                adapted_total += len(data)
        assert set(changes) == {'install.sh', 'uninstall.sh', 'ss/ssconfig.sh', 'webs/Module_shadowsocks.asp', 'scripts/ss_update.sh'}
        compressed=io.BytesIO()
        with gzip.GzipFile(fileobj=compressed,mode='wb',filename='',mtime=0) as z:z.write(out.getvalue())
        zipped=compressed.getvalue()
        adapted = ROOT / package['adapted_path']
        adapted.write_bytes(zipped)
        package.update(adapted_sha256=sha(zipped), adapted_md5=hashlib.md5(zipped).hexdigest(),
                       upstream_expanded_bytes=total, expanded_bytes=adapted_total, files=files, changed_files=changes)
    dest = ROOT / 'build/fancyss_inputs.json'
    dest.write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def render_page(manifest, config):
    p=next(p for p in manifest['packages'] if p['phase']=='current')
    text=render_source('sources/localmod/Module_FancyssLocalmod.asp',config)
    for key,value in {'@TAG@':config['tag'],'@FANCYSS_VERSION@':p['version'],
                      '@FANCYSS_MD5@':p['adapted_md5'],'@FANCYSS_FILENAME@':Path(p['adapted_path']).name}.items():
        assert key in text
        text=text.replace(key,value)
    assert '@FANCYSS_' not in text and '@TAG@' not in text
    return text


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    data = prepare()
    print('Verified/adapted', len(data['packages']), 'pinned Fancyss HND v8 archives; no host execution')
