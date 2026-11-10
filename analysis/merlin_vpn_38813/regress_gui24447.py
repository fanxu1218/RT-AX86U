#!/usr/bin/env python3
"""Run existing native suites in a separate, firmware-bound evidence namespace."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PREFIX = 'merlin38813gui24447'
PROFILE = ROOT / 'analysis/merlin_vpn_38813gui24447'
sys.path.insert(0, str(ROOT / 'build'))
sys.path.insert(0, str(HERE))
from sealed_vm import inventory, encoded, sha
from audit_gui24447 import read_image, write_report
from build_gui24447 import inventory as full_inventory


def read(path):
    return json.loads((ROOT / path).read_text())


def save(path, value):
    (ROOT / path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def extract(image, target):
    from ubireader.ubi_io import ubi_file
    from ubireader.ubifs import ubifs
    from ubireader.ubifs.output import extract_files
    volumes = target.with_name(target.name + '-volumes')
    subprocess.run([sys.executable, str(ROOT / 'build/inspect_upstream.py'), str(image), str(volumes)],
                   check=True, stdout=subprocess.DEVNULL)
    target.mkdir()
    extract_files(ubifs(ubi_file(str(volumes / 'rootfs_ubifs'), 126976)), str(target))


def prepare():
    candidate = read('output/merlin38813_gui24447_candidate.json')
    image = ROOT / candidate['image']
    assert sha(image) == candidate['sha256']
    actual, _, _, _ = read_image(image, hardlinks=True)
    stage = ROOT / candidate['stage']
    assert full_inventory(stage) == actual
    assert not PROFILE.exists(), 'A prepared profile is retained; use it rather than overwrite it'
    preserved_names = ['output/merlin38813_gui24447_candidate.json',
        'output/merlin38813_native_candidate_tests.json', 'output/merlin38813_local_gate.json',
        'output/merlin38813_hour_gate.json', 'output/merlin38813_release_delivery.json', candidate['image']]
    preserved = {p: sha(ROOT / p) for p in preserved_names}
    factory = read('build/gui24447-factory-input.json')
    factory_image = ROOT / factory['config']['image']
    assert sha(factory_image) == factory['candidate_sha256']
    factory_root = ROOT / 'build/casefs/gui24447_factory_rootfs'
    if not factory_root.exists(): extract(factory_image, factory_root)
    # Exercise the archived r8's actual 1.9.50 core as the upgrade fixture.
    old = factory_root / 'rom/etc/koolshare'
    pin = read('build/softcenter_sources.json')
    old_inventory = inventory(old)
    old_tree_sha = hashlib.sha256(encoded(old_inventory)).hexdigest()
    assert old_tree_sha == '33c82a714fb2f774ae3ef87606d4ec503cda3ce6536806c1524e0b747f7bff44'
    assert (old / '.soft_ver').read_text().strip() == '1.9.50'
    core_id = (factory_root / 'rom/etc/localmod-core-id').read_text().strip()
    assert core_id == 'b1c2ed363f6844579f0df9f2170253c5e5dde221b5b1d46f8d1e4189e8a53392'
    old_core = ROOT / 'build/softcenter-old-core'
    assert not old_core.exists()
    shutil.copytree(old, old_core, symlinks=True)
    save('build/softcenter-old-inputs.json', dict(core_id=core_id,
        baseline_image=factory['config']['image'], baseline_image_sha256=factory['candidate_sha256'],
        tree=old_inventory, tree_sha256=old_tree_sha,
        reference='Actual 1.9.50 runtime core from the SHA256-verified archived r8 image; distinct from the historical r9 fixture'))
    factory_entries, _, _, _ = read_image(factory_image)
    for name, row in factory_entries.items():
        path = factory_root / name.lstrip('/')
        if row['type'] == 'link': os.lchmod(path, stat.S_IMODE(row['mode']))
        else: path.chmod(stat.S_IMODE(row['mode']))
    default = ROOT / 'build/casefs/rootfs'
    assert not default.exists()
    shutil.copytree(stage, default, symlinks=True)
    assert inventory(default) == inventory(stage)
    official = ROOT / 'build/casefs/official_rootfs'
    assert not official.exists()
    shutil.copytree(ROOT / 'build/casefs/asus24437_rootfs', official, symlinks=True)
    data = ROOT / 'upstream/gui24447'; data.mkdir(exist_ok=True)
    save('upstream/gui24447/metadata.json', {p: {k: row[k] for k in ['mode', 'uid', 'gid']} for p, row in actual.items()})

    PROFILE.mkdir()
    lineage = {}
    for source in sorted(HERE.rglob('*')):
        if not source.is_file() or source.suffix not in {'.py', '.go', '.c', '.h', '.sh', '.json', '.txt'}:
            continue
        if source.name == Path(__file__).name: continue
        relative = source.relative_to(HERE); target = PROFILE / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        text = source.read_text().replace('merlin_vpn_38813', 'merlin_vpn_38813gui24447').replace('merlin38813', PREFIX)
        if source.name == 'test_softcenter_upgrade.go':
            raise AssertionError('Shared Go source is adapted separately')
        if source.name == 'uu_matrix.py':
            text = text.replace("ROOT/'output/release_gates.json'", "ROOT/'build/gui24447-factory-input.json'")
            needle = "assert sha(ROOT/pin['archive']['image'])==pin['archive']['image_sha256']"
            assert text.count(needle) == 1
            text = text.replace(needle, "candidate=json.loads((ROOT/'output/" + PREFIX + "_native_candidate_tests.json').read_text());assert sha(ROOT/candidate['image']['image'])==candidate['image']['sha256']")
            text = text.replace("('factory','build/casefs/rootfs'", "('factory','build/casefs/gui24447_factory_rootfs'")
            text = text.replace("'/sbin/rc')]:", "'/usr/libexec/localmod/rc.vendor')]:")
            text = text.replace("src=ROOT/'build/casefs/" + PREFIX + "_rootfs'", "src=ROOT/candidate['rootfs']")
            text = text.replace('upstream/' + PREFIX + '/metadata.json', 'upstream/gui24447/metadata.json')
            text = text.replace("upstream_image_sha256=pin['archive']['image_sha256']", "executed_candidate_sha256=candidate['image']['sha256']")
            marker = "    if label=='merlin':"
            assert text.count(marker) == 1
            text = text.replace(marker, """    if label=='factory':
     src=ROOT/tree;dest=self.workspace/tree
     before=inventory(src);shutil.copytree(src,dest,symlinks=True,copy_function=copy_file)
     assert before==inventory(src)==inventory(dest)
     self.inputs[tree]=hashlib.sha256(encoded(before)).hexdigest()
""" + marker)
        if source.name == 'candidate_runtime.go':
            marker = '\ts.login()\n'
            assert text.count(marker) == 1
            assertion = '''\tcodeLang, bodyLang := s.request("GET", "/state.js", "")
\tif codeLang != 200 || strings.Contains(bodyLang, "<% shown_language_css(); %>") { panic("language menu was not rendered") }
\tfor language, name := range map[string]string{"CN":"简体中文", "TW":"繁體中文", "JP":"日本語", "KR":"한국어", "TH":"ไทย", "UK":"Українська", "BR":"Português(Brazil)", "FR":"Français", "ES":"Español", "CZ":"Česky", "SL":"Slovenščina", "TR":"Türkçe"} {
\t\tif !strings.Contains(bodyLang, "id=\\\""+language+"\\\">"+name+"</a>") { panic("rendered language menu mismatch: "+language) }
\t}
\tcandidateRecord("candidate_native_https_renders_utf8_language_menu_from_backported_data")
'''
            text = text.replace(marker, marker + assertion)
        target.write_text(text)
        lineage[str(target.relative_to(ROOT))] = dict(source=str(source.relative_to(ROOT)),
            source_sha256=sha(source), generated_sha256=sha(target))
    # The old-core archive identity is a fixture provenance assertion. Keep it
    # strict against the actual recovered r8 image, without claiming r9 bytes.
    shared = ROOT / 'build/test_softcenter_upgrade.go'
    fixture = ROOT / ('build/' + PREFIX + '-softcenter-upgrade.go')
    text = shared.read_text(); assert text.count(pin['baseline_image_sha256']) == 1
    fixture.write_text(text.replace(pin['baseline_image_sha256'], factory['candidate_sha256']))
    controller = PROFILE / 'check_native_plugins.py'
    text = controller.read_text().replace("'build/test_softcenter_upgrade.go'", repr(str(fixture.relative_to(ROOT))))
    controller.write_text(text); lineage[str(controller.relative_to(ROOT))]['generated_sha256'] = sha(controller)
    lineage[str(fixture.relative_to(ROOT))] = dict(source=str(shared.relative_to(ROOT)),
        source_sha256=sha(shared), generated_sha256=sha(fixture))
    fresh = dict(read('output/merlin38813_native_candidate_tests.json'))
    packing = dict(candidate['packing'], image=candidate['image'])
    fresh.update(image=packing, rootfs=candidate['stage'],
        stage_inventory_sha256=hashlib.sha256(encoded(inventory(stage))).hexdigest(),
        inventory_sha256=hashlib.sha256(encoded(inventory(stage))).hexdigest(),
        upstream_paths_changed=['rom/etc/profile','sbin/rc','usr/sbin/httpd','usr/sbin/iptables-restore','www/Lang_Hdr.txt','www/state.js'],
        protected_sha256=preserved,
        source_sha256={str(Path(__file__).relative_to(ROOT)): sha(Path(__file__)),
            'output/merlin38813_gui24447_candidate.json': sha(ROOT/'output/merlin38813_gui24447_candidate.json')},
        note='Existing rebuilt/read-back GUI24447 image; this manifest selects it for fresh isolated executions and does not reuse old dynamic results')
    save('output/' + PREFIX + '_native_candidate_tests.json', fresh)
    save('output/' + PREFIX + '_native_preview_stage.json', fresh)
    save('output/' + PREFIX + '_upstream_audit.json', dict(status='P7_PARENT_REFERENCE_ONLY',
        parent_sha256=candidate['base_sha256'], candidate_sha256=candidate['sha256']))
    save('build/' + PREFIX + '_sources.json', read('build/merlin38813_sources.json'))
    # Execute the current frontend's actual functions with isolated report names.
    original = ROOT / 'build/softcenter_frontend_contract.mjs'
    frontend = ROOT / ('build/' + PREFIX + '-frontend.mjs')
    text = original.read_text().replace('output/verification.json', 'build/' + PREFIX + '-frontend-input.json')
    text = text.replace('build/release_config.json', 'build/' + PREFIX + '-frontend-input.json')
    text = text.replace('output/softcenter_frontend_tests.json', 'output/' + PREFIX + '_frontend_tests.json')
    frontend.write_text(text)
    save('build/' + PREFIX + '-frontend-input.json', dict(image=candidate['image'], sha256=candidate['sha256']))
    lineage[str(frontend.relative_to(ROOT))] = dict(source=str(original.relative_to(ROOT)),
        source_sha256=sha(original), generated_sha256=sha(frontend))
    save('output/' + PREFIX + '_lineage.json', dict(schema=1, candidate_sha256=candidate['sha256'],
        generator_sha256=sha(Path(__file__)), files=lineage, preserved_sha256=preserved,
        adaptations=['Separate controller/output namespace; original dynamic assertions retained',
            'UU matrix executes archived factory r8 plus the actual GUI24447 native rc; candidate launcher is separately covered by candidate_runtime',
            'Old 1.9.50 upgrade fixture is the actual archived r8 core, with strict image/core/tree identities; it is distinct from the historical r9 core',
            'Additional authenticated native HTTPS assertion verifies the corrected language menu']))
    print('GUI24447_PROFILE_PREPARED', candidate['sha256'], flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--refresh-bindings', action='store_true')
    args = parser.parse_args()
    if args.prepare: prepare()
    if args.refresh_bindings:
        lineage = read('output/' + PREFIX + '_lineage.json')
        for name, row in lineage['files'].items():
            assert sha(ROOT / row['source']) == row['source_sha256']
            row['generated_sha256'] = sha(ROOT / name)
        lineage['generator_sha256'] = sha(Path(__file__))
        save('output/' + PREFIX + '_lineage.json', lineage)
        candidate = read('output/' + PREFIX + '_native_candidate_tests.json')
        candidate['source_sha256'][str(Path(__file__).relative_to(ROOT))] = sha(Path(__file__))
        save('output/' + PREFIX + '_native_candidate_tests.json', candidate)
        save('output/' + PREFIX + '_native_preview_stage.json', candidate)


if __name__ == '__main__': main()
