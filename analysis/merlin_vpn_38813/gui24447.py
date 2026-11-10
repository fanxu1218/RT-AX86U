#!/usr/bin/env python3
"""Backport only the verified ASUS language-name data fix to Merlin 388.13."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PIN = ROOT / 'build/asus24447_sources.json'
LANGUAGES = 'EN BR CN CZ DA DE ES FI FR HU IT JP KR MS NL NO PL RO RU SL SV TH TR TW UK'.split()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def payload():
    pin = json.loads(PIN.read_text())
    data = (ROOT / pin['source']).read_bytes()
    assert digest(data) == pin['after_sha256'], 'Language payload digest mismatch'
    lines = data.decode('utf-8').splitlines()
    pairs = [line.split('=', 1) for line in lines]
    assert all(len(pair) == 2 and pair[1] and '?' not in pair[1] for pair in pairs)
    assert [pair[0] for pair in pairs] == ['LANG_' + key for key in LANGUAGES]
    return pin, data


def apply(stage):
    """Refuse unexpected inputs; retain the target inode's modes/ownership."""
    pin, data = payload()
    stage = Path(stage)
    assert stage.is_dir() and not stage.is_symlink()
    assert (stage / 'www').is_dir() and not (stage / 'www').is_symlink()
    path = stage / pin['path']
    assert path.is_file() and not path.is_symlink()
    assert path.stat().st_nlink == 1, 'Language data must have its own inode'
    original = path.read_bytes()
    assert digest(original) in {pin['before_sha256'], pin['after_sha256']}, 'Unexpected Merlin language data'
    changed = original != data
    if changed:
        path.write_bytes(data)
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    args = parser.parse_args()
    print('Language data updated' if apply(args.stage) else 'Language data already current')


if __name__ == '__main__':
    main()
