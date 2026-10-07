"""Bounded metadata reads for assistance cache freshness checks.

This is not a full integrity check of the labels array. The normal result loader
still validates that data. Legacy layouts use an isolated stdlib-only process so
large JSON decoding cannot hold the web process's GIL.
"""
import json
from pathlib import Path
import subprocess
import sys

WINDOW = 64 * 1024
KEYS = ('annotation_ai', 'source_ai_postprocess', 'assistance_confidence_threshold')


def _summary(payload):
    if not isinstance(payload, dict):
        raise ValueError('Assistance cache must be an object')
    result = {key: payload.get(key) for key in KEYS}
    result['labels'] = [] if isinstance(payload.get('labels'), list) else None
    return result


def _prefix_metadata(head):
    decoder = json.JSONDecoder()
    pos = 0

    def whitespace():
        nonlocal pos
        while pos < len(head) and head[pos].isspace():
            pos += 1

    whitespace()
    if head[pos:pos + 1] != '{':
        return None
    pos += 1
    result = {}
    while pos < len(head):
        whitespace()
        key, pos = decoder.raw_decode(head, pos)
        if not isinstance(key, str):
            return None
        whitespace()
        if head[pos:pos + 1] != ':':
            return None
        pos += 1
        whitespace()
        if key == 'labels':
            if head[pos:pos + 1] == '[' and all(key in result for key in KEYS):
                result['labels'] = []
                return result
            return None
        value, pos = decoder.raw_decode(head, pos)
        if key in KEYS:
            result[key] = value
        whitespace()
        if head[pos:pos + 1] != ',':
            return None
        pos += 1
    return None


def read_assistance_metadata(path):
    path = Path(path)
    with path.open('rb') as stream:
        size = stream.seek(0, 2)
        stream.seek(0)
        head = stream.read(WINDOW)
        if size <= WINDOW:
            return _summary(json.loads(head))
        stream.seek(max(0, size - 128))
        tail = stream.read(128)
    try:
        result = _prefix_metadata(head.decode('utf-8', errors='ignore'))
    except (ValueError, TypeError, RecursionError):
        result = None
    # The application writer places labels last. Other layouts go through the
    # compatibility path rather than accidentally marking an old cache stale.
    if result is not None and b''.join(tail.split()).endswith(b']}'):
        return result
    try:
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), str(path.resolve())],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120,
            check=True,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise ValueError('Unable to inspect assistance cache metadata') from exc
    return json.loads(completed.stdout)


if __name__ == '__main__':
    with open(sys.argv[1], encoding='utf-8') as stream:
        payload = json.load(stream)
    print(json.dumps(_summary(payload), separators=(',', ':')))
