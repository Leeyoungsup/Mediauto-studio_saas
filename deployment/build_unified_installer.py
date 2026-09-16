"""Package a clean two-mode GPU installer with no models, credentials or operational data."""
import hashlib
from pathlib import Path
import tarfile
import zipfile
import io

ROOT=Path(__file__).resolve().parents[1]
TOP=('install.bat','select.ps1','install.sh','setup-nvidia-runtime.sh','README.md')
DOCKER=('install.bat','bootstrap.ps1','bootstrap_admin.py','install.sh','install.py','container_runner.py','setup-nvidia-runtime.sh','model-checksums.json')
NATIVE=('install.bat','bootstrap.ps1','bootstrap_admin.py','install.sh','install.py','github_source.py','runner.py','gpu_check.py','register-task.ps1','model-checksums.json')

def build():
    out=ROOT/'artifacts/local-deployment/unified';out.mkdir(parents=True,exist_ok=True)
    entries={name:ROOT/'deployment/installer'/name for name in TOP}
    entries.update({'docker/'+name:ROOT/'deployment/host'/name for name in DOCKER})
    entries.update({'native/'+name:ROOT/'deployment/native'/name for name in NATIVE})
    payloads={name:p.read_bytes() for name,p in entries.items()}
    for name in payloads:
        if name.endswith('.bat'):payloads[name]=payloads[name].replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
    files=[]
    for kind in ('windows-x64.zip','linux-x64.tar.gz'):
        path=out/('MeDIAuto-GPU-installer-'+kind)
        if kind.endswith('.zip'):
            with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
                for name,data in payloads.items():z.writestr('MeDIAuto-GPU-installer/'+name,data)
        else:
            with tarfile.open(path,'w:gz') as z:
                for name,data in payloads.items():
                    info=tarfile.TarInfo('MeDIAuto-GPU-installer/'+name);info.size=len(data);info.mode=0o755 if name.endswith('.sh') else 0o644
                    z.addfile(info,io.BytesIO(data))
        files.append(path);print(path)
    (out/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in files))

if __name__=='__main__':build()
