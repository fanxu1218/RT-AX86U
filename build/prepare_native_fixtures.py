#!/usr/bin/env python3
"""Prepare synthetic native-runtime inputs from pinned 24437 factory defaults."""
import struct
import subprocess
from pathlib import Path
from elftools.elf.elffile import ELFFile

root = Path(__file__).resolve().parent.parent
library = root / 'build/casefs/official_rootfs/usr/lib/libshared.so'
data = library.read_bytes()
with library.open('rb') as stream:
    elf = ELFFile(stream)
    assert elf.elfclass == 32 and elf.little_endian and elf['e_machine'] == 'EM_ARM'
    def offset(address):
        return next(address - s['p_vaddr'] + s['p_offset'] for s in elf.iter_segments()
                    if s['p_type'] == 'PT_LOAD' and s['p_vaddr'] <= address < s['p_vaddr'] + s['p_filesz'])
    def string(address):
        start = offset(address)
        return data[start:data.index(0, start)]
    symbol = elf.get_section_by_name('.dynsym').get_symbol_by_name('router_defaults')[0]
    assert symbol['st_size'] % 20 == 0  # ARM32 nvram_tuple from the pinned GPL header.
    base = offset(symbol['st_value'])
    defaults = bytearray()
    count = 0
    for position in range(base, base + symbol['st_size'], 20):
        key, value = struct.unpack_from('<II', data, position)
        if not key:
            break
        defaults += string(key) + b'\0' + (string(value) if value else b'') + b'\0'
        count += 1
    assert count > 1000
(root / 'build/native_defaults.bin').write_bytes(defaults)
# Public synthetic fixture account only; no router or host account is read.
password = subprocess.check_output(['openssl', 'passwd', '-6', '-salt', 'localfixture', '-stdin'],
                                   input=b'local-test-password\n')
assert password.startswith(b'$6$localfixture$')
(root / 'build/native_shadow_hash.txt').write_bytes(password)
print('Prepared', count, 'pinned factory defaults and one synthetic shadow entry')
