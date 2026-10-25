#!/usr/bin/env python3
"""Read-only integrity/structure check for this Broadcom UBI firmware.

Uses the Python standard library. Does not execute anything from the image.
Offsets are positions in the update file, not the router's physical flash map.
"""
import argparse
import collections
import hashlib
import json
import struct
import zlib
from pathlib import Path


def raw_crc(data):
    return zlib.crc32(data) ^ 0xFFFFFFFF


def inspect(path):
    data = path.read_bytes()
    start, peb, io, payload_offset = 0x100000, 0x20000, 0x800, 0x1000
    end = len(data) - 20
    assert (end - start) % peb == 0, "Unexpected image length"
    trailer = struct.unpack("<5I", data[-20:])
    counts = collections.Counter()
    volumes = collections.defaultdict(list)
    for offset in range(start, end, peb):
        ec = data[offset:offset + 64]
        vid = data[offset + io:offset + io + 64]
        assert ec[:4] == b"UBI#", f"Invalid EC magic at {offset:#x}"
        assert vid[:4] == b"UBI!", f"Invalid VID magic at {offset:#x}"
        counts["ec_valid" if raw_crc(ec[:60]) == struct.unpack_from(">I", ec, 60)[0] else "ec_bad"] += 1
        counts["vid_valid" if raw_crc(vid[:60]) == struct.unpack_from(">I", vid, 60)[0] else "vid_bad"] += 1
        volume, logical = struct.unpack_from(">II", vid, 8)
        size = struct.unpack_from(">I", vid, 20)[0]
        if vid[5] == 2:
            expected = struct.unpack_from(">I", vid, 32)[0]
            actual = raw_crc(data[offset + payload_offset:offset + payload_offset + size])
            counts["static_data_valid" if actual == expected else "static_data_bad"] += 1
        volumes[volume].append((logical, offset, vid[5], size))

    volume_names = {}
    table_start = start + payload_offset
    for index in range(128):
        record = data[table_start + index * 172:table_start + (index + 1) * 172]
        reserved, _, _, volume_type, _, name_len = struct.unpack_from(">IIIBBH", record)
        if reserved:
            volume_names[index] = {
                "name": record[16:16 + name_len].decode("ascii"),
                "reserved_pebs": reserved,
                "type": "static" if volume_type == 2 else "dynamic",
            }

    rootfs = b"".join(data[offset + payload_offset:offset + peb]
                      for _, offset, _, _ in sorted(volumes[0]))
    node_counts = collections.Counter()
    position = 0
    while True:
        position = rootfs.find(b"\x31\x18\x10\x06", position)
        if position < 0:
            break
        if position + 24 <= len(rootfs):
            length = struct.unpack_from("<I", rootfs, position + 16)[0]
            node_type = rootfs[position + 20]
            same_leb = position // 126976 == (position + length - 1) // 126976
            if 24 <= length <= 126976 and node_type <= 13 and position + length <= len(rootfs) and same_leb:
                expected = struct.unpack_from("<I", rootfs, position + 4)[0]
                actual = raw_crc(rootfs[position + 8:position + length])
                node_counts["valid" if actual == expected else "bad"] += 1
        position += 4

    return {
        "filename": path.name,
        "bytes": len(data),
        "md5": hashlib.md5(data).hexdigest(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "published_md5_match": hashlib.md5(data).hexdigest() == "ace03b30acc5bf4abf8266b5a91ed03d",
        "broadcom_trailer": {
            "stored_crc": hex(trailer[0]),
            "calculated_crc": hex(raw_crc(data[:-20])),
            "valid": raw_crc(data[:-20]) == trailer[0],
            "version_raw": hex(trailer[1]),
            "chip_id_raw": hex(trailer[2]),
            "flash_type_raw": hex(trailer[3]),
            "flags_raw": hex(trailer[4]),
        },
        "ubi_start": hex(start),
        "ubi_end_exclusive": hex(end),
        "peb_bytes": peb,
        "leb_bytes": 126976,
        "min_io_bytes": io,
        "ubi_checks": dict(counts),
        "ubifs_node_checks": dict(node_counts),
        "volumes": {
            str(number): dict(volume_names.get(number, {"name": "UBI layout"}),
                              blocks=len(blocks),
                              first_file_offset=hex(min(item[1] for item in blocks)),
                              last_file_offset=hex(max(item[1] for item in blocks)))
            for number, blocks in volumes.items()
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware", type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.firmware), indent=2, ensure_ascii=False))
