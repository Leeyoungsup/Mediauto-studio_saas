"""Rebuildable SQLite spatial index beside a canonical assistance JSON file.

Original one-based label IDs and double-precision patch boundary checks are
preserved. A warm lookup reads metadata and only the requested spatial range.
"""
from contextlib import closing
import fcntl
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile

VERSION = 1


def signature(path):
    stat = path.stat()
    return [stat.st_size, stat.st_mtime_ns, stat.st_ino]


def index_path(source):
    return Path(source).with_suffix('.spatial.sqlite3')


def _connect(path):
    return sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)


def _query(source, patch):
    target = index_path(source)
    if not target.exists() or not source.exists():
        return None
    try:
        with closing(_connect(target)) as db:
            stored = dict(db.execute('SELECT key, value FROM metadata'))
            if json.loads(stored['version']) != VERSION or json.loads(stored['source']) != signature(source):
                return None
            meta = json.loads(stored['payload'])
            rows = []
            if patch is not None:
                x, y = float(patch['int_x']), float(patch['int_y'])
                w, h = float(patch['int_w']), float(patch['int_h'])
                if not all(math.isfinite(v) for v in (x, y, w, h)) or w <= 0 or h <= 0:
                    return meta, rows
                # RTree bounds are rounded outward; exact double checks below
                # preserve the original half-open center-in-patch selection.
                rows = [(idx, json.loads(label)) for idx, label in db.execute('''
                    SELECT l.id, l.payload FROM positions r JOIN labels l ON l.id=r.id
                    WHERE r.max_x >= ? AND r.min_x <= ? AND r.max_y >= ? AND r.min_y <= ?
                      AND l.cx >= ? AND l.cx < ? AND l.cy >= ? AND l.cy < ? ORDER BY l.id
                ''', (x, x+w, y, y+h, x, x+w, y, y+h))]
            if json.loads(stored['source']) != signature(source):
                return None
            return meta, rows
    except (OSError, sqlite3.DatabaseError, KeyError, ValueError, TypeError):
        return None


def _build(source, payload, expected):
    target = index_path(source)
    descriptor, name = tempfile.mkstemp(prefix=target.name+'.', suffix='.tmp', dir=target.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        with closing(sqlite3.connect(temporary)) as db:
            db.executescript('''
                CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE labels(id INTEGER PRIMARY KEY, cx REAL, cy REAL, payload TEXT NOT NULL);
                CREATE VIRTUAL TABLE positions USING rtree(id, min_x, max_x, min_y, max_y);
            ''')
            meta = {k:v for k,v in payload.items() if k != 'labels'}
            meta['total_labels'] = len(payload.get('labels', []))
            db.executemany('INSERT INTO metadata VALUES (?,?)', [(k,json.dumps(v)) for k,v in
                {'version':VERSION,'source':expected,'payload':meta}.items()])
            batch = []
            def flush():
                db.executemany('INSERT INTO labels VALUES (?,?,?,?)', batch)
                db.executemany('INSERT INTO positions VALUES (?,?,?,?,?)',
                    ((idx,x,x,y,y) for idx,x,y,_ in batch))
                batch.clear()
            for idx,label in enumerate(payload.get('labels', []), start=1):
                if not isinstance(label, (list,tuple)) or len(label) < 8:
                    continue
                x,y = float(label[4]),float(label[5])
                if not math.isfinite(x) or not math.isfinite(y):
                    continue
                batch.append((idx,x,y,json.dumps(label,separators=(',',':'))))
                if len(batch) >= 4096:
                    flush()
            flush()
            db.commit()
        if signature(source) != expected:
            return False
        os.replace(temporary, target)
        return True
    finally:
        temporary.unlink(missing_ok=True)


def read(source, loader, patch=None):
    """Return (full metadata, [(original label number, compact label), ...]).

    The loader validates/normalizes legacy JSON once. Atomic replacement and a
    per-source process lock prevent partially built or duplicate indexes.
    """
    source = Path(source)
    cached = _query(source, patch)
    if cached is not None:
        return cached
    if not source.exists():
        return {}, []
    with source.with_suffix('.spatial.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        cached = _query(source, patch)
        if cached is not None:
            return cached
        for _ in range(3):
            if not source.exists():
                return {}, []
            before = signature(source)
            payload = loader()
            if not payload:
                return {}, []
            # Normalization may rewrite the canonical JSON; reread the stable
            # generation rather than attach older labels to a newer file.
            if not source.exists():
                return {}, []
            if signature(source) != before:
                continue
            if _build(source,payload,before):
                cached = _query(source,patch)
                if cached is not None:
                    return cached
        raise RuntimeError('Assistance result changed while building its spatial index; retry the request')


def prepare(source, payload, expected):
    """Index an already-read generation without rereading its JSON."""
    source = Path(source)
    with source.with_suffix('.spatial.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not source.exists() or signature(source) != expected:
            return False
        if _query(source, None) is not None:
            return True
        return _build(source, payload, expected)
