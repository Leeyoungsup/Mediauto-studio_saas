"""Build clean, platform-specific source + model bundles from current worktree files."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOP = {'README.md', 'CHANGELOG.md', 'version.json'}
BACKEND_FILES = {'backend/main.py', 'backend/requirements.txt', 'backend/alembic.ini', 'backend/model_manifest.json'}
SCRIPTS = {'bootstrap_runtime.py', 'bootstrap_philips.py'}
DEPLOY_FILES = {'Dockerfile', 'entrypoint.sh', 'compose.yml', 'compose.gpu.yml', 'configure.py', 'manage.sh', 'manage.ps1', 'LOCAL_INSTALL.md'}


def allowed(name):
    path = Path(name)
    if path.is_absolute() or '..' in path.parts or '__pycache__' in path.parts:
        return False
    if name in TOP or name in BACKEND_FILES:
        return True
    if name.startswith(('backend/app/', 'backend/ai/', 'backend/philips_bridge/', 'backend/alembic/')):
        return path.suffix in {'.py', '.mako', '.yaml'}
    if name.startswith('frontend/'):
        return path.suffix in {'.html', '.js', '.css', '.png', '.ico', '.svg', '.mp4', '.mjs'}
    if name.startswith('backend/scripts/') and path.name in SCRIPTS:
        return True
    if name.startswith('backend/scripts/openphi-master/'):
        return name.split('openphi-master/')[1] in {'setup.py','README.md','LICENSE','openphi/__init__.py','openphi/openphi.py'}
    return name.startswith('deployment/local/') and path.name in DEPLOY_FILES


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def stage(output):
    version = json.loads((ROOT/'version.json').read_text())['version']
    target = output / f'MeDIAuto-{version}'
    target.mkdir(parents=True, exist_ok=False)
    # Read working copies, so authorized changes need not be committed to be included.
    tracked = subprocess.check_output(['git','ls-files','-z'], cwd=ROOT).decode().split('\0')
    files = {name for name in tracked if name and allowed(name)}
    files.update(path.relative_to(ROOT).as_posix() for path in (ROOT/'deployment/local').iterdir()
                 if path.is_file() and path.name in DEPLOY_FILES)
    for name in sorted(files):
        source = ROOT/name
        if source.is_symlink():
            raise ValueError('Symlink is not allowed in bundle: '+name)
        dest = target/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source,dest)
    shutil.copy2(ROOT/'deployment/local/dockerignore', target/'.dockerignore')
    shutil.copy2(ROOT/'deployment/local/LOCAL_INSTALL.md', target/'LOCAL_INSTALL.md')
    models = json.loads((ROOT/'backend/model_manifest.json').read_text())['models']
    (target/'models').mkdir()
    count = 0
    for model in models:
        source = ROOT/'backend/model'/model['filename']
        if not source.is_file():
            if model.get('required',True): raise FileNotFoundError(source)
            continue
        if source.is_symlink(): raise ValueError('Model symlink is not allowed')
        shutil.copy2(source,target/'models'/model['filename'])
        count += 1
    for filename,action in [('setup','setup'),('start-local','start'),('stop-local','stop')]:
        shell = '#!/usr/bin/env bash\nset -euo pipefail\ncd "$(dirname "${BASH_SOURCE[0]}")"\nexec bash deployment/local/manage.sh '+action+' "$@"\n'
        (target/(filename+'.sh')).write_text(shell)
        (target/(filename+'.sh')).chmod(0o755)
        args = ' -Device %1' if action == 'setup' else ''
        # setup has a cpu default; only forward a device argument if present.
        batch = '@echo off\r\nsetlocal\r\ncd /d "%~dp0"\r\n'
        if action == 'setup':
            batch += 'set "DEVICE=cpu"\r\nif not "%~1"=="" set "DEVICE=%~1"\r\n'
            args = ' -Device "%DEVICE%"'
        batch += 'powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deployment\\local\\manage.ps1" -Action '+action+args+'\r\nset "RESULT=%ERRORLEVEL%"\r\nif not "%RESULT%"=="0" pause\r\nexit /b %RESULT%\r\n'
        (target/(filename+'.bat')).write_bytes(batch.encode('ascii'))
    entries = [{'path':p.relative_to(target).as_posix(),'size':p.stat().st_size,'sha256':digest(p)}
               for p in sorted(target.rglob('*')) if p.is_file()]
    manifest = {'version':version,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                'model_count':count,'files':entries}
    (target/'bundle-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print('Staged',target,'models:',count,'files:',len(entries),flush=True)
    return target


def archive(target, output):
    manifest = json.loads((target/'bundle-manifest.json').read_text())
    files = [target/item['path'] for item in manifest['files']] + [target/'bundle-manifest.json']
    linux = output/(target.name+'-linux-x64.tar.gz')
    windows = output/(target.name+'-windows-x64.zip')
    with tarfile.open(linux,'w:gz',compresslevel=1) as out:
        for path in files: out.add(path,arcname=target.name+'/'+path.relative_to(target).as_posix(),recursive=False)
    print('Created',linux,flush=True)
    with zipfile.ZipFile(windows,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as out:
        for path in files: out.write(path,arcname=target.name+'/'+path.relative_to(target).as_posix())
    print('Created',windows,flush=True)
    (output/'SHA256SUMS.txt').write_text(''.join(f'{digest(path)}  {path.name}\n' for path in (linux,windows)))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/local-deployment')
    parser.add_argument('--stage-only',action='store_true')
    parser.add_argument('--archive-stage',type=Path)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    target=args.archive_stage or stage(args.output)
    if not args.stage_only: archive(target,args.output)
