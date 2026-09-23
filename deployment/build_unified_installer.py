"""Package a clean two-mode GPU installer with no models, credentials or operational data."""
import hashlib
from pathlib import Path
import tarfile
import zipfile
import io
import json
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
TOP=('gui.py','gui_worker.py','gui_contract.py','setup-gui.bat','setup-gui.sh','GUI_GUIDE.ko.md','install.bat','select.ps1','install.sh','setup-nvidia-runtime.sh','README.md')
DOCKER=('setup-nvidia-driver.ps1','setup-nvidia-driver.sh','local_setup.py','start-local.bat','start-local.sh','github_source.py','Dockerfile.source','Dockerfile.source.dockerignore','launch.ps1','start.bat','stop.bat','start.sh','stop.sh','install.bat','bootstrap.ps1','bootstrap_admin.py','install.sh','install.py','container_runner.py','setup-nvidia-runtime.sh','model-checksums.json')
NATIVE=('setup-nvidia-driver.ps1','setup-nvidia-driver.sh','install.bat','bootstrap.ps1','bootstrap_admin.py','install.sh','install.py','github_source.py','conda_setup.py','diagnose_philips.py','runner.py','launch.py','run-local.ps1','start.bat','start.sh','gpu_check.py','model-checksums.json')

LOCAL_SHARED={'run-local.ps1':'run-local.ps1','local_environment.py':'install.py','conda_setup.py':'conda_setup.py','runner.py':'runner.py','gpu_check.py':'gpu_check.py','local_launch.py':'launch.py','diagnose_philips.py':'diagnose_philips.py'}

def windows_vendor_payloads():
    manifest_path=ROOT/'deployment/native/openslide-windows.json'
    manifest=json.loads(manifest_path.read_text())
    path=ROOT/'artifacts/local-deployment/vendor'/manifest['filename']
    if not path.exists():
        path.parent.mkdir(parents=True,exist_ok=True)
        urllib.request.urlretrieve(manifest['url'],path)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=manifest['sha256']:
        raise ValueError('OpenSlide Windows wheel checksum mismatch')
    return {'vendor/'+path.name:path.read_bytes(),'vendor/openslide-windows.json':manifest_path.read_bytes()}


def sdk_payloads(windows):
    sdk_name = ('philips-pathologysdk-2.0-L1-windows10-py37-research' if windows
                else 'philips-pathologysdk-2.0-L1-ubuntu20_04_py38_research')
    sources = {sdk_name:ROOT/'backend/Philips_SDK'/sdk_name,
               'support/scripts/openphi-master':ROOT/'backend/scripts/openphi-master',
               'support/philips_bridge':ROOT/'backend/philips_bridge'}
    result = {}
    for destination, source in sources.items():
        if not source.is_dir():raise ValueError('SDK source missing: '+str(source))
        for path in sorted(source.rglob('*')):
            relative=path.relative_to(source)
            if any(part in ('__pycache__','.git','build','dist') or part.endswith('.egg-info') for part in relative.parts):continue
            if path.suffix=='.pyc' or not path.is_file():continue
            if path.is_symlink():raise ValueError('Unexpected SDK symlink: '+str(path))
            result[destination+'/'+relative.as_posix()]=path.read_bytes()
    result['support/scripts/bootstrap_philips.py']=(ROOT/'backend/scripts/bootstrap_philips.py').read_bytes()
    manifest={'platform':'windows' if windows else 'linux','sdk_directory':sdk_name,
              'files':[{'path':name,'sha256':hashlib.sha256(data).hexdigest()} for name,data in sorted(result.items())]}
    result['manifest.json']=json.dumps(manifest,indent=2).encode()
    return {'Philips_SDK/'+name:data for name,data in result.items()}


def build():
    out=ROOT/'artifacts/local-deployment/unified';out.mkdir(parents=True,exist_ok=True)
    entries={name:ROOT/'deployment/installer'/name for name in TOP}
    entries['PATH_CONFIGURATION.ko.md']=ROOT/'deployment/PATH_CONFIGURATION.ko.md'
    entries.update({'docker/'+name:ROOT/'deployment/host'/name for name in DOCKER})
    entries.update({'native/'+name:ROOT/'deployment/native'/name for name in NATIVE})
    entries.update({'docker/'+target:ROOT/'deployment/native'/source for target,source in LOCAL_SHARED.items()})
    payloads={name:p.read_bytes() for name,p in entries.items()}
    for name in payloads:
        if name.endswith('.bat'):payloads[name]=payloads[name].replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
    files=[]
    for kind in ('windows-x64.zip','linux-x64.tar.gz'):
        package = dict(payloads, **sdk_payloads(kind.startswith('windows')))
        if kind.startswith('windows'):package.update(windows_vendor_payloads())
        path=out/('MeDIAuto-GPU-installer-'+kind)
        if kind.endswith('.zip'):
            with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
                for name,data in package.items():z.writestr('MeDIAuto-GPU-installer/'+name,data)
        else:
            with tarfile.open(path,'w:gz') as z:
                for name,data in package.items():
                    info=tarfile.TarInfo('MeDIAuto-GPU-installer/'+name);info.size=len(data);info.mode=0o755 if name.endswith('.sh') else 0o644
                    z.addfile(info,io.BytesIO(data))
        files.append(path);print(path)
    (out/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in files))

if __name__=='__main__':build()
