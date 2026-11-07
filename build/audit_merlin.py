#!/usr/bin/env python3
"""Independent ELF audit of the selected program overlay (analysis venv)."""
import hashlib
import json
import sys
from pathlib import Path
from elftools.elf.elffile import ELFFile
from prepare_merlin import PIN, SOURCE, ROOT, verify


def facts(path):
    with path.open('rb') as f:
        e = ELFFile(f)
        assert e.elfclass == 32 and e.little_endian and e.header.e_machine == 'EM_ARM'
        for segment in e.iter_segments():
            h = segment.header
            if h.p_type == 'PT_LOAD':
                assert h.p_align > 0 and h.p_offset % h.p_align == h.p_vaddr % h.p_align, path
        dyn = e.get_section_by_name('.dynamic')
        return dict(flags=e.header.e_flags,
                    needed=[t.needed for t in dyn.iter_tags() if t.entry.d_tag == 'DT_NEEDED'],
                    rpath=[t.rpath for t in dyn.iter_tags() if t.entry.d_tag == 'DT_RPATH'],
                    code={name: hashlib.sha256(e.get_section_by_name(name).data()).hexdigest()
                          for name in ['.text','.rodata','.data'] if e.get_section_by_name(name)})


def audit(root):
    receipt = verify(root)
    rows = {}
    for kind, entries in [('programs',PIN['programs']),('libraries',PIN['libraries'])]:
        for name, entry in entries.items():
            p = root / ('usr/libexec/localmod/merlin/bin/' if kind == 'programs' else 'usr/lib/localmod/merlin/') / name
            original, current = facts(SOURCE / entry['path']), facts(p)
            assert all(original[key] == current[key] for key in ['flags','needed','code']), name
            if kind == 'programs':
                assert current['rpath'] == [PIN['rpath']], name
            else:
                assert hashlib.sha256(p.read_bytes()).hexdigest() == entry['sha256'], name
            rows[name] = current
    return rows


if __name__ == '__main__':
    rows = audit(ROOT / (sys.argv[1] if len(sys.argv)>1 else 'build/casefs/rootfs'))
    print(json.dumps(rows, indent=2))
