"""Create clean Windows/Linux host-DB installers, including only verified model weights."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
FILES=('install.bat','bootstrap.ps1','bootstrap_admin.py','install.sh','install.py','model-checksums.json','container_runner.py','setup-nvidia-runtime.sh','Dockerfile.gpu','README.md')

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda:f.read(4*1024*1024),b''):h.update(data)
    return h.hexdigest()

def build(output):
    output.mkdir(parents=True,exist_ok=True)
    target=output/'MeDIAuto-3.3.2-host-db'
    target.mkdir(exist_ok=False)
    for name in FILES:
        source=ROOT/'deployment/host'/name
        if source.is_symlink():raise ValueError('Installer source must not be a symlink')
        shutil.copy2(source,target/name)
    # CMD launchers use CRLF; PowerShell and Python remain UTF-8.
    batch=target/'install.bat';batch.write_bytes(batch.read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'))
    (target/'models').mkdir()
    for item in json.loads((target/'model-checksums.json').read_text()):
        source=ROOT/'backend/model'/item['filename']
        if source.is_symlink() or digest(source)!=item['sha256']:raise ValueError('Source model checksum mismatch')
        shutil.copy2(source,target/'models'/item['filename'])
    files=sorted(p for p in target.rglob('*') if p.is_file())
    manifest=[{'path':p.relative_to(target).as_posix(),'sha256':digest(p)} for p in files]
    (target/'bundle-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files.append(target/'bundle-manifest.json')
    archives=[]
    for platform in ('linux-x64','windows-x64'):
        archive=output/(target.name+'-'+platform+('.zip' if platform.startswith('windows') else '.tar.gz'))
        if platform.startswith('windows'):
            with zipfile.ZipFile(archive,'w',zipfile.ZIP_STORED,allowZip64=True) as z:
                for path in files:z.write(path,arcname=target.name+'/'+path.relative_to(target).as_posix())
        else:
            with tarfile.open(archive,'w:gz',compresslevel=0) as z:
                for path in files:z.add(path,arcname=target.name+'/'+path.relative_to(target).as_posix(),recursive=False)
        archives.append(archive);print('Created',archive,flush=True)
    (output/'SHA256SUMS.txt').write_text(''.join(f'{digest(p)}  {p.name}\n' for p in archives))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'artifacts/local-deployment/host-db')
    build(parser.parse_args().output)
