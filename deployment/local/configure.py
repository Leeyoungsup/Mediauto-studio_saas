"""Verify a clean bundle and generate credentials on the destination machine only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets


def verify(root):
    manifest = json.loads((root / 'bundle-manifest.json').read_text(encoding='utf-8'))
    for item in manifest['files']:
        path = root / item['path']
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('Invalid bundle path: ' + item['path'])
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
                digest.update(block)
        if digest.hexdigest() != item['sha256']:
            raise ValueError('Bundle checksum mismatch: ' + item['path'])
    print('Bundle integrity verified:', len(manifest['files']), 'files', flush=True)


def configure(root, mode):
    env = root / '.deploy.env'
    if env.exists():
        values = dict(line.split('=', 1) for line in env.read_text().splitlines() if '=' in line)
        if values.get('MEDIAUTO_DEVICE') != mode:
            raise ValueError('Existing device mode differs. Reuse the original mode or consult LOCAL_INSTALL.md.')
        print('Existing installation credentials retained.')
        return
    # Keep generated ASCII password + the app's 43-character pepper within bcrypt's 72-byte limit.
    password = secrets.token_hex(12) + 'Aa!'
    values = {
        'COMPOSE_PROJECT_NAME': 'mediauto_' + secrets.token_hex(5),
        'POSTGRES_PASSWORD': secrets.token_hex(24),
        'ADMIN_PASSWORD': password,
        'MEDIAUTO_DEVICE': mode,
        'TORCH_INDEX_URL': 'https://download.pytorch.org/whl/' + ('cu128' if mode == 'gpu' else 'cpu'),
        'MEDIAUTO_BIND': '127.0.0.1',
        'MEDIAUTO_PORT': '8092',
        'TILE_CACHE_QUOTA_BYTES': '107374182400',
    }
    with env.open('x', encoding='utf-8') as file:
        file.write(''.join(f'{key}={value}\n' for key, value in values.items()))
    env.chmod(0o600)
    credentials = root / 'ADMIN_LOGIN.txt'
    with credentials.open('x', encoding='utf-8') as file:
        file.write('URL: http://localhost:8092\nID: admin\nPassword: ' + password + '\nChange this password after signing in.\n')
    credentials.chmod(0o600)
    print('New credentials created in ADMIN_LOGIN.txt (not printed to console).')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['cpu', 'gpu'], default='cpu')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    verify(root)
    if not args.verify_only:
        configure(root, args.mode)
