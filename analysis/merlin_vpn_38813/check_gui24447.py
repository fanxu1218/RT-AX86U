#!/usr/bin/env python3
"""Verify the backport's data contract and refusal/preservation boundaries."""
import os
import stat
import tempfile
from pathlib import Path

from gui24447 import ROOT, apply, digest, payload


def main():
    pin, fixed = payload()
    original = (Path(__file__).parent / 'vendor/Lang_Hdr_38813.before.txt').read_bytes()
    assert digest(original) == pin['before_sha256']
    with tempfile.TemporaryDirectory(prefix='gui24447-check-') as temp:
        root = Path(temp); (root / 'www').mkdir()
        path = root / pin['path']
        neighbor = root / 'www/sentinel'; neighbor.write_bytes(b'preserve')
        path.write_bytes(original); path.chmod(0o640)
        assert apply(root) and path.read_bytes() == fixed
        assert stat.S_IMODE(path.stat().st_mode) == 0o640
        assert neighbor.read_bytes() == b'preserve'
        assert not apply(root)
        path.write_text('LANG_CN=unexpected\n'); path.chmod(0o640)
        try:
            apply(root)
            raise RuntimeError('Unexpected input accepted')
        except AssertionError:
            assert path.read_text() == 'LANG_CN=unexpected\n'
        path.unlink(); (root / 'outside').write_bytes(b'preserve outside')
        path.symlink_to(root / 'outside')
        try:
            apply(root)
            raise RuntimeError('Symbolic target accepted')
        except AssertionError:
            assert (root / 'outside').read_bytes() == b'preserve outside'
        path.unlink(); path.write_bytes(original)
        os.link(path, root / 'alias')
        try:
            apply(root)
            raise RuntimeError('Shared inode accepted')
        except AssertionError:
            assert (root / 'alias').read_bytes() == original
        path.unlink(); path.write_bytes(fixed); path.chmod(0o640)
        assert not apply(root) and stat.S_IMODE(path.stat().st_mode) == 0o640
    print('PASS 25 language keys/UTF-8, real P7 fixture replacement, mode/neighbor preservation, idempotence, unexpected-input/symlink/hardlink refusal; no device claim')


if __name__ == '__main__':
    main()
