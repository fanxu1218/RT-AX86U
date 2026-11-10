#!/usr/bin/env python3
"""Compare pinned official images and P7 directly, without executing firmware."""
import collections
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import zipfile

from gui24447 import ROOT, PIN, digest, payload


def read_image(path, hardlinks=False):
    from ubireader.ubi_io import ubi_file
    from ubireader.ubifs import ubifs, walk
    from ubireader.ubifs.output import _process_reg_file
    sys.path.insert(0, str(ROOT / 'build'))
    from device_config import require_model
    raw = path.read_bytes()
    require_model(raw)
    with tempfile.TemporaryDirectory(prefix='gui24447-audit-', dir=ROOT / 'upstream') as temp:
        subprocess.run([sys.executable, str(ROOT / 'build/inspect_upstream.py'), str(path), temp],
                       check=True, stdout=subprocess.DEVNULL)
        folder = Path(temp)
        layout = json.loads((folder / 'layout.json').read_text())
        assert layout['whole_crc_valid'] and not any(k.endswith('_bad') and v for k, v in layout['checks'].items())
        parsed = ubifs(ubi_file(str(folder / 'rootfs_ubifs'), 126976))
        nodes, bad, entries, data, aliases = {}, [], {}, {}, {}
        walk.index(parsed, parsed.master_node.root_lnum, parsed.master_node.root_offs, nodes, bad)
        assert not bad
        def visit(number, path):
            node = nodes[number]; ino = node['ino']
            row = dict(mode=ino.mode, uid=ino.uid, gid=ino.gid)
            if stat.S_ISDIR(ino.mode):
                row['type'] = 'directory'
            elif stat.S_ISREG(ino.mode):
                content = _process_reg_file(parsed, node, path, nodes)
                assert len(content) == ino.size, path
                data[path] = content
                row.update(type='file', bytes=len(content), sha256=digest(content))
                aliases.setdefault(number, []).append(path)
            elif stat.S_ISLNK(ino.mode):
                row.update(type='link', target=ino.data.decode())
            else:
                raise AssertionError('Unsupported inode: ' + path)
            entries[path] = row
            for dent in node.get('dent', []):
                assert dent.name and '/' not in dent.name and dent.name not in {'.', '..'}
                visit(dent.inum, path.rstrip('/') + '/' + dent.name)
        visit(1, '/')
        if hardlinks:
            for paths in aliases.values():
                if len(paths) > 1:
                    for path in paths:
                        entries[path]['hardlink_group'] = min(paths)
        boot = {p.name: digest(p.read_bytes()) for p in (folder / 'bootfiles').iterdir()}
    return entries, data, boot, layout


def write_report(path, report):
    data = (json.dumps(report, indent=2, ensure_ascii=False) + '\n').encode()
    if path.exists():
        assert path.read_bytes() == data, 'Refusing to replace different evidence: ' + str(path)
    else:
        with path.open('xb') as output:
            output.write(data)


def main():
    pin, fixed = payload()
    inputs, trees, contents, boots, layouts = {}, {}, {}, {}, {}
    for version, row in pin['archives'].items():
        archive, image = ROOT / row['zip'], ROOT / row['image']
        assert digest(archive.read_bytes()) == row['zip_sha256']
        assert digest(image.read_bytes()) == row['image_sha256']
        with zipfile.ZipFile(archive) as zipped:
            assert zipped.testzip() is None and zipped.namelist() == [image.name]
            assert zipped.read(image.name) == image.read_bytes()
        inputs[version] = row
        trees[version], contents[version], boots[version], layouts[version] = read_image(image)
    target = ROOT / pin['target_image']
    assert digest(target.read_bytes()) == pin['target_image_sha256']
    p7, p7_data, _, _ = read_image(target)
    language = '/' + pin['path']
    assert contents['24447'][language] == fixed
    assert digest(p7_data[language]) == pin['before_sha256']
    assert b'Lang_Hdr.txt' in p7_data['/usr/libexec/localmod/httpd']
    before, after = trees['24437'], trees['24447']
    changed = [p for p in sorted(set(before) | set(after)) if before.get(p) != after.get(p)]
    def content(row):
        return {k: v for k, v in row.items() if k not in {'mode', 'uid', 'gid'}} if row else None
    files = [dict(path=p, before=before.get(p), after=after.get(p)) for p in changed
             if content(before.get(p)) != content(after.get(p))]
    metadata = [p for p in changed if content(before.get(p)) == content(after.get(p))]
    web = [row['path'] for row in files if row['path'].startswith('/www/')]
    assert web == [language], web
    anchors = {p: contents['24437']['/' + p] == contents['24447']['/' + p]
               for p in ['usr/sbin/httpd', 'sbin/rc', 'usr/lib/libssl.so.1.1', 'www/state.js',
                         'www/Main_Login.asp', 'www/UUAccelerator.asp']}
    modes = collections.Counter((oct(before[p]['mode']), oct(after[p]['mode'])) for p in changed
                                if p in before and p in after and before[p]['mode'] != after[p]['mode'])
    sources = ['analysis/merlin_vpn_38813/audit_gui24447.py',
               'analysis/merlin_vpn_38813/gui24447.py', 'build/asus24447_sources.json',
               'build/inspect_upstream.py', 'build/device_config.py', pin['source']]
    report = dict(schema=1, status='OFFICIAL_24447_COMPARED_P7_LANGUAGE_DEFECT_CONFIRMED',
        inputs=inputs, target_image=pin['target_image'], target_image_sha256=pin['target_image_sha256'],
        image_paths={v: len(t) for v, t in trees.items()}, p7_paths=len(p7),
        changed_paths=len(changed), metadata_only_paths=len(metadata), content_or_type_changes=len(files),
        permission_changes=[dict(before=a, after=b, paths=n) for (a, b), n in sorted(modes.items())],
        web_content_changes=web, unchanged_anchor_bytes=anchors,
        changed_bootfiles=[p for p in sorted(set(boots['24437']) | set(boots['24447']))
                           if boots['24437'].get(p) != boots['24447'].get(p)],
        content_changes=files, image_crc_checks={v: x['checks'] for v, x in layouts.items()},
        language_before_sha256=pin['before_sha256'], language_after_sha256=pin['after_sha256'],
        transplanted_paths=[pin['path']], source_sha256={p: digest((ROOT / p).read_bytes()) for p in sources},
        limits=['Binary differences are not proof of functional fixes or compatibility.',
                'Only the confirmed language-name fix is selected; official binaries, kernel, drivers and permission changes are not transplanted.',
                'No router access, flashing or device/visual acceptance.'])
    write_report(ROOT / 'output/merlin38813_gui24447_audit.json', report)
    print(report['status'], len(changed), 'changed paths;', len(files), 'content/type;', len(metadata), 'metadata only')


if __name__ == '__main__':
    main()
