"""Verify historical frozen files without changing their recorded digests.

Only CRLF/LF differences are accepted. Content, whitespace, BOMs and final
newlines remain significant. In particular this does not regrade any answers.
"""
import hashlib
from pathlib import Path


def matches_frozen_hash(path, expected):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() == expected:
        return True
    try:
        raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        return False
    if b'\x00' in raw:
        return False
    lf = raw.replace(b'\r\n', b'\n')
    return expected in {
        hashlib.sha256(lf).hexdigest(),
        hashlib.sha256(lf.replace(b'\n', b'\r\n')).hexdigest(),
    }


def verify_frozen_hash(path, expected):
    if not matches_frozen_hash(path, expected):
        raise AssertionError(f'Frozen file content changed: {path}')
