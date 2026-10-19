"""Portable encrypted audit history; no key material is stored in the archive."""
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.repositories.operational_store import _json_safe

MAGIC = b'MEDIAUTO-AUDIT-1\n'
ITERATIONS = 600_000
RETENTION_YEARS = 3


def retain_until(date):
    try:
        return date.replace(year=date.year + RETENTION_YEARS)
    except ValueError:
        return date.replace(year=date.year + RETENTION_YEARS, day=28)


class AuditArchive:
    def __init__(self, passphrase):
        salt, nonce = os.urandom(16), os.urandom(12)
        key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                        iterations=ITERATIONS).derive(passphrase.encode('utf-8'))
        header = json.dumps({'version':1, 'cipher':'AES-256-GCM', 'kdf':'PBKDF2-SHA256',
                             'iterations':ITERATIONS, 'salt':salt.hex(), 'nonce':nonce.hex()},
                            sort_keys=True, separators=(',', ':')).encode() + b'\n'
        self.encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
        self.encryptor.authenticate_additional_data(MAGIC + header)
        fd, path = tempfile.mkstemp(prefix='mediauto-audit-', suffix='.audit.enc')
        self.path = Path(path)
        self.stream = os.fdopen(fd, 'wb')
        self.stream.write(MAGIC + header)
        self.count = 0
        self.digest = hashlib.sha256()
        self.latest = None
        self._write({'record_type':'policy', 'retention_years':RETENTION_YEARS,
                     'created_at':datetime.now(timezone.utc).isoformat()})

    def _write(self, value):
        encoded = (json.dumps(value, ensure_ascii=False, separators=(',', ':'),
                              allow_nan=False)+'\n').encode()
        self.stream.write(self.encryptor.update(encoded))

    def append(self, rows):
        for row in rows:
            safe = _json_safe(row)
            encoded = json.dumps(safe, ensure_ascii=False, sort_keys=True,
                                 separators=(',', ':'), allow_nan=False).encode()
            self.digest.update(encoded+b'\n')
            self._write({'record_type':'audit', 'record':safe})
            self.count += 1
            date = row.get('dt_created_at')
            if isinstance(date, str):
                date = datetime.fromisoformat(date)
            if date is not None:
                date = date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date
                self.latest = max(self.latest, date) if self.latest else date

    def finish(self):
        self._write({'record_type':'summary', 'record_count':self.count,
                     'records_sha256':self.digest.hexdigest(),
                     'retain_until':retain_until(self.latest).isoformat() if self.latest else None})
        self.stream.write(self.encryptor.finalize())
        self.stream.write(self.encryptor.tag)
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.stream.close()
        return self.path

    def cleanup(self):
        self.stream.close()
        self.path.unlink(missing_ok=True)


def decrypt_archive(source, destination, passphrase):
    """Publish plaintext only after GCM authentication and content checks succeed."""
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise ValueError('Destination already exists')
    with source.open('rb') as stream:
        if stream.readline(100) != MAGIC:
            raise ValueError('Unsupported audit archive')
        header = stream.readline(4096)
        meta = json.loads(header)
        if (meta.get('version') != 1 or meta.get('cipher') != 'AES-256-GCM'
                or meta.get('kdf') != 'PBKDF2-SHA256' or meta.get('iterations') != ITERATIONS):
            raise ValueError('Unsupported encryption parameters')
        key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=bytes.fromhex(meta['salt']),
                        iterations=ITERATIONS).derive(passphrase.encode('utf-8'))
        start = stream.tell()
        size = source.stat().st_size
        if size < start+16:
            raise ValueError('Truncated archive')
        stream.seek(-16, 2)
        tag = stream.read(16)
        decryptor = Cipher(algorithms.AES(key), modes.GCM(bytes.fromhex(meta['nonce']), tag)).decryptor()
        decryptor.authenticate_additional_data(MAGIC+header)
        stream.seek(start)
        fd, name = tempfile.mkstemp(prefix='.audit-restore-', dir=destination.parent)
        temporary = Path(name)
        try:
            with os.fdopen(fd, 'wb') as out:
                remaining = size-start-16
                while remaining:
                    chunk = stream.read(min(remaining, 1024*1024))
                    if not chunk:
                        raise ValueError('Truncated archive')
                    out.write(decryptor.update(chunk))
                    remaining -= len(chunk)
                out.write(decryptor.finalize())
            digest = hashlib.sha256()
            count, summary = 0, None
            with temporary.open(encoding='utf-8') as plaintext:
                for line in plaintext:
                    item = json.loads(line)
                    if item.get('record_type') == 'audit':
                        count += 1
                        digest.update(json.dumps(item['record'], ensure_ascii=False, sort_keys=True,
                                                 separators=(',', ':'), allow_nan=False).encode()+b'\n')
                    elif item.get('record_type') == 'summary':
                        summary = item
            if not summary or summary['record_count'] != count or summary['records_sha256'] != digest.hexdigest():
                raise ValueError('Audit archive content check failed')
            # link refuses to overwrite a destination created concurrently.
            os.link(temporary, destination)
            return summary
        finally:
            temporary.unlink(missing_ok=True)
