"""Package only native installer code; application is fetched from GitHub and models are selected locally."""
import hashlib
from pathlib import Path
import tarfile
import zipfile
import io
from build_unified_installer import sdk_payloads, windows_vendor_payloads

ROOT=Path(__file__).resolve().parents[1]
FILES=('install.bat','bootstrap.ps1','bootstrap_admin.py','install.sh','install.py','github_source.py','conda_setup.py','diagnose_philips.py','runner.py','launch.py','start.bat','start.sh','gpu_check.py','model-checksums.json','README.md')

def build():
    output=ROOT/'artifacts/local-deployment/native';output.mkdir(parents=True,exist_ok=True)
    archives=[]
    for platform in ('windows-x64','linux-x64'):
        target=output/('MeDIAuto-native-installer-'+platform+('.zip' if platform.startswith('windows') else '.tar.gz'))
        sdk = sdk_payloads(platform.startswith('windows'))
        if platform.startswith('windows'):sdk.update(windows_vendor_payloads())
        if platform.startswith('windows'):
            with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
                for name in FILES:
                    data=(ROOT/'deployment/native'/name).read_bytes()
                    if name.endswith('.bat'):data=data.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
                    z.writestr('MeDIAuto-native-installer/'+name,data)
                for name,data in sdk.items():z.writestr('MeDIAuto-native-installer/'+name,data)
        else:
            with tarfile.open(target,'w:gz') as z:
                for name in FILES:z.add(ROOT/'deployment/native'/name,arcname='MeDIAuto-native-installer/'+name,recursive=False)
                for name,data in sdk.items():
                    info=tarfile.TarInfo('MeDIAuto-native-installer/'+name);info.size=len(data);info.mode=0o644
                    z.addfile(info,io.BytesIO(data))
        archives.append(target);print(target)
    (output/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in archives))

if __name__=='__main__':build()
