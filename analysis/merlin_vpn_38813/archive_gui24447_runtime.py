#!/usr/bin/env python3
"""Archive small source inputs; reconstruct and hash-check per-boot controllers."""
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import types

ROOT = Path(__file__).resolve().parents[2]
PREFIX = 'merlin38813gui24447'
PROFILE = ROOT / 'analysis/merlin_vpn_38813gui24447'
EXTENSIONS = {'.py','.go','.c','.h','.sh','.json','.mjs','.txt'}


def digest(data): return hashlib.sha256(data).hexdigest()


def archive(reports, persistence, candidate_sha256):
    files, unavailable, generated = {}, [], {}
    def put(name, data, origin):
        assert not name.startswith('/') and '..' not in Path(name).parts and len(data) < 4*1024*1024
        if name in files: assert files[name][0] == data, name
        files[name] = (data, origin)
    wanted = {}
    for report in reports:
        for group in [report.get('source_sha256', {}), report.get('vm', {}).get('inputs', {})]:
            for name, expected in group.items():
                if Path(name).suffix in EXTENSIONS and 'shadow' not in name:
                    wanted.setdefault(name, set()).add(expected)
    for name, hashes in wanted.items():
        path = ROOT / name
        if path.is_file() and not path.is_symlink() and digest(path.read_bytes()) in hashes:
            data = path.read_bytes(); put(name, data, 'Observed source or generated input')
            hashes = hashes - {digest(data)}
        for expected in hashes: unavailable.append(dict(path=name, sha256=expected))
    for source in PROFILE.rglob('*'):
        if source.is_file() and not source.is_symlink() and source.suffix in EXTENSIONS:
            put(str(source.relative_to(ROOT)), source.read_bytes(), 'Namespaced controller/contract source')
    for name in ['regress_gui24447.py','rehydrate_gui24447.py','verify_gui24447_regression.py','archive_gui24447_runtime.py']:
        path = ROOT / 'analysis/merlin_vpn_38813' / name
        put(str(path.relative_to(ROOT)), path.read_bytes(), 'Reproduction and verification entry')
    for name in ['build/zig_download.json','build/linux_packages.json','build/merlin_system_sources.json','build/gui24447-factory-input.json',
                 'build/real_plugin_sources.json','build/fancyss_sources.json','build/extended_plugin_sources.json',
                 'sources/localmod/fancyss-LICENSE.txt']:
        put(name, (ROOT/name).read_bytes(), 'Fixed dependency/source contract')
    soak_job=ROOT/('build/'+PREFIX+'-native-soak/nested_job.sh')
    if soak_job.is_file():
        current=soak_job.read_text()
        assert current.count('COEXIST_SECONDS=3600 COEXIST_PROBE=0')==1
        for label,seconds,probe in [('probe',300,1),('smoke',300,0),('hour',3600,0)]:
            data=current.replace('COEXIST_SECONDS=3600 COEXIST_PROBE=0',
                'COEXIST_SECONDS='+str(seconds)+' COEXIST_PROBE='+str(probe)).encode()
            put('reconstructed/soak-'+label+'/nested_job.sh',data,'Known duration/probe variant; verified against sealed input hashes below')
            generated.setdefault(str(soak_job.relative_to(ROOT)),set()).add(digest(data))
            generated.setdefault('build/merlin_nested_job.sh',set()).add(digest(data))

    # The persistence controller is deterministic in case/phase/disk/initialize.
    # Its exec call is intercepted here; no compiler, VM or guest code executes.
    sys.path.insert(0, str(PROFILE))
    spec = importlib.util.spec_from_file_location('gui24447_persist_archive', PROFILE/'check_native_persist.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    path = ROOT / ('build/' + PREFIX + '-native-persist/derived_check.py')
    retained = path.read_bytes()
    rows = [persistence['foundation']['result']]
    for case in persistence['cases'].values(): rows.extend(x for x in case.values() if isinstance(x, dict) and 'report' in x)
    try:
        for row in rows:
            report = json.loads((ROOT/row['report']).read_text())
            phase = report['result']['phases'][0]
            case, boot = phase['case'], phase['boot']
            current = dict(case=case, boot=boot, initialize=case=='foundation')
            module.CURRENT=current;module.CUT=boot in {'cut','recover-cut','recover-db-cut'}
            module.DISK=ROOT/'build/interrupt-private'/('native-'+candidate_sha256[:12]+'-'+case+'.img')
            captured=[]
            module.builtins=types.SimpleNamespace(exec=lambda code, namespace:captured.append(path.read_bytes()))
            module.run_derived(None,{})
            assert len(captured)==1
            source = captured[0]
            name = str(path.relative_to(ROOT)); expected=report['vm']['inputs'][name]
            assert digest(source)==expected, ('Per-boot controller reconstruction mismatch',case,boot)
            key='reconstructed/persist-'+case+'-'+boot+'/'
            put(key+'derived_check.py',source,'Exact per-boot controller reconstructed and compared with sealed VM hash')
            phase_data=(json.dumps(current)+'\n').encode()
            expected_phase=report['vm']['inputs']['build/interrupt-phase.json']
            assert digest(phase_data)==expected_phase
            put(key+'interrupt-phase.json',phase_data,'Exact sealed phase input')
            generated.setdefault(name,set()).add(expected)
            generated.setdefault('build/interrupt-phase.json',set()).add(expected_phase)
    finally:
        path.write_bytes(retained)
    # Include reconstructed content as explicit variants for all matching VM
    # expectations, so each archived claim remains checkable by its exact hash.
    reconstructed={digest(data):data for name,(data,_) in files.items() if name.startswith('reconstructed/')}
    for row in unavailable:
        if row['sha256'] in generated.get(row['path'],set()):
            assert row['sha256'] in reconstructed
    unavailable=[row for row in unavailable if row['sha256'] not in generated.get(row['path'],set())]
    # Several sealed aliases use bytes also saved at a controller-private path.
    # Preserve those variants by content, without overwriting the shared template.
    by_hash={digest(data):data for data,_ in files.values()}
    remaining=[]
    for row in unavailable:
        if row['sha256'] in by_hash:
            put('variants/'+row['sha256']+'/'+row['path'],by_hash[row['sha256']],
                'Exact sealed alias recovered from its controller-private source')
        else: remaining.append(row)
    unavailable=remaining
    # Overrides of the shared guest dispatch are generated from archived Python
    # controllers/templates. Their exact hashes remain in each VM manifest.
    dispatch_aliases={'build/linux_real_plugins_job.sh','build/real_plugins_setup.sh','build/merlin_nested_job.sh'}
    assert not [x for x in unavailable if Path(x['path']).suffix in {'.py','.go','.c','.h','.sh','.mjs'}
                and x['path'] not in dispatch_aliases], unavailable
    members={name:dict(bytes=len(data),sha256=digest(data),origin=origin) for name,(data,origin) in sorted(files.items())}
    manifest=dict(schema=1,candidate_sha256=candidate_sha256,files=members,
        per_boot_controllers_reconstructed=len(rows),unarchived_generated_aliases_or_data=unavailable,
        note='Source/contract data only; shared dispatch overrides are reproducible from archived controllers/templates and bound by VM hashes. Tool binaries, firmware and plugin archives remain separate inputs')
    body=io.BytesIO()
    with tarfile.open(fileobj=body,mode='w',format=tarfile.USTAR_FORMAT) as tar:
        for name,(data,_) in sorted(files.items()):
            info=tarfile.TarInfo(name);info.mode=0o644;info.size=len(data)
            tar.addfile(info,io.BytesIO(data))
    target=ROOT/('output/'+PREFIX+'_runtime_sources.tar.gz')
    assert not target.exists()
    target.write_bytes(gzip.compress(body.getvalue(),mtime=0))
    with tarfile.open(target,'r:gz') as tar:
        assert set(tar.getnames())==set(members)
        for name,row in members.items(): assert digest(tar.extractfile(name).read())==row['sha256']
    manifest_path=ROOT/('output/'+PREFIX+'_runtime_sources.manifest.json')
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    return dict(path=str(target.relative_to(ROOT)),sha256=digest(target.read_bytes()),bytes=target.stat().st_size,
        manifest=str(manifest_path.relative_to(ROOT)),manifest_sha256=digest(manifest_path.read_bytes()),
        archived_files=len(files),reconstructed_persistence_boots=len(rows))
