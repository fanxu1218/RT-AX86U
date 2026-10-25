#!/usr/bin/env python3
"""Carve UBI update images without running router code."""
import argparse
import collections
import hashlib
import json
import struct
import zlib
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('image', type=Path)
ap.add_argument('out', type=Path)
args = ap.parse_args()
d = args.image.read_bytes()
start = d.find(b'UBI#')
assert start >= 0
peb, payload = 131072, 4096
vols = collections.defaultdict(list)
counts = collections.Counter()
for o in range(start, len(d) - peb + 1, peb):
    ec, vid = d[o:o+64], d[o+2048:o+2112]
    assert ec[:4] == b'UBI#' and vid[:4] == b'UBI!'
    for label, header in [('ec', ec), ('vid', vid)]:
        valid = (zlib.crc32(header[:60]) ^ 0xffffffff) == struct.unpack_from('>I', header, 60)[0]
        counts[label + ('_valid' if valid else '_bad')] += 1
    v, l = struct.unpack_from('>II', vid, 8)
    size = struct.unpack_from('>I', vid, 20)[0]
    if vid[5] == 2:
        crc = struct.unpack_from('>I', vid, 32)[0]
        valid = (zlib.crc32(d[o+payload:o+payload+size]) ^ 0xffffffff) == crc
        counts['data_valid' if valid else 'data_bad'] += 1
    vols[v].append((l, o, vid[5], size))
args.out.mkdir(parents=True, exist_ok=True)
names = {}
for i in range(128):
    t = d[start+payload+i*172:start+payload+(i+1)*172]
    reserved, align, pad, typ, upd, length = struct.unpack_from('>IIIBBH', t)
    if reserved:
        names[i] = {'name': t[16:16+length].decode(), 'reserved': reserved, 'type': typ, 'flags': t[144]}
for v, a in vols.items():
    if v not in names:
        continue
    a.sort()
    raw = b''.join(d[o+payload:o+payload+(size if typ==2 else peb-payload)] for l,o,typ,size in a)
    (args.out / names[v]['name']).write_bytes(raw)
    names[v].update({'blocks': len(a), 'first_offset': hex(a[0][1]), 'payload_bytes': len(raw)})
    if v == 10:
        offset = 0
        boot = args.out / 'bootfiles'
        boot.mkdir(exist_ok=True)
        while offset + 16 <= len(raw):
            total, hdr, size, crc = struct.unpack_from('>IIII', raw, offset)
            if total == 0 or total > len(raw)-offset or not 8 <= hdr <= total:
                break
            name = raw[offset+16:offset+8+hdr].split(b'\0')[0].decode()
            assert '/' not in name
            (boot/name).write_bytes(raw[offset+8+hdr:offset+8+hdr+size])
            offset += total+4
trailer = struct.unpack('<5I', d[-20:])
report = {'filename': args.image.name, 'bytes': len(d), 'sha256': hashlib.sha256(d).hexdigest(),
          'md5': hashlib.md5(d).hexdigest(), 'start': start, 'volumes': names,
          'checks': counts, 'trailer': [hex(x) for x in trailer],
          'whole_crc_valid': (zlib.crc32(d[:-20]) ^ 0xffffffff) == trailer[0]}
(args.out/'layout.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
