"""Assemble the requested three installers plus four illustrated PDF guides.

Run after capture_release_gui.py and build_installation_guides.py.
Set MAKENSIS/NSISDIR when using a locally extracted NSIS toolchain.
This builds artifacts only; it never installs the app, changes drivers or publishes.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from build_gui_installer import build as build_gui

ROOT=Path(__file__).resolve().parents[1]
REVISION='2026-10-07-r18'
OUT=ROOT/'artifacts/local-deployment/final'/REVISION
INSTALLERS=('MeDIAuto-Setup-windows-x64.exe','MeDIAuto-Setup-linux-x64.run','MeDIAuto-Setup-linux-x64-cli.tar.gz')


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): h.update(block)
    return h.hexdigest()


def validate_members(names):
    names=list(names)
    for name in names:
        path=Path(name)
        if path.is_absolute() or '..' in path.parts:raise ValueError('Unsafe package path: '+name)
        if any(part in ('.git','.runtime','__pycache__','postgres_data','uploads','ai_results','tiles','.env','.secrets.json','ADMIN_LOGIN.txt','.install-location.json') for part in path.parts):
            raise ValueError('Unexpected runtime/secret file: '+name)
    for suffix in ('/gui.py','/native/install.py','/docker/install.py','/native/bootstrap_python.py','/docker/bootstrap_python.py','/START-HERE.txt','/Philips_SDK/manifest.json'):
        if not any(name.endswith(suffix) for name in names):raise ValueError('Missing package entry '+suffix)
    return len(names)


def verify(output):
    cli=output/INSTALLERS[2]
    with tarfile.open(cli) as archive:
        count=validate_members(archive.getnames())
        if any(not m.isfile() for m in archive.getmembers()):raise ValueError('Expected regular files only')
        for pdf in (output/'guides').glob('*.pdf'):
            if archive.extractfile('MeDIAuto-GPU-installer/guides/'+pdf.name).read()!=pdf.read_bytes():
                raise ValueError('Bundled PDF differs from standalone guide: '+pdf.name)
        if archive.extractfile('MeDIAuto-GPU-installer/START-HERE.txt').read()!=(output/'START-HERE.txt').read_bytes():
            raise ValueError('Bundled and standalone instructions differ')
        shell=archive.extractfile('MeDIAuto-GPU-installer/install.sh').read()
        if b'570.26' not in shell or b'Internet' not in shell:raise ValueError('Missing CLI requirements')
    run=(output/INSTALLERS[1]).read_bytes()
    header,payload=run.split(b'__MEDIAUTO_ARCHIVE_BELOW__\n',1)
    if payload!=cli.read_bytes():raise ValueError('GUI and CLI Linux payloads differ')
    if hashlib.sha256(payload).hexdigest().encode() not in header:raise ValueError('Self-extractor hash mismatch')
    subprocess.run(['bash','-n'],input=header,check=True)
    with (output/INSTALLERS[0]).open('rb') as stream:
        if stream.read(2)!=b'MZ':raise ValueError('Windows installer is not a PE executable')
    checks=json.loads((output/'guides/layout-validation.json').read_text())
    if len(checks)!=4 or any(c['overflow'] or c['brokenImages'] for c in checks):raise ValueError('Guide layout validation missing/failed')
    pdfs=list((output/'guides').glob('*.pdf'))
    if len(pdfs)!=4:raise ValueError('Expected four guides')
    for pdf in pdfs:
        info=subprocess.check_output(['pdfinfo',str(pdf)],text=True)
        expected_pages=10 if 'Windows' in pdf.name else 12
        actual_pages=int(next(line.split(':',1)[1] for line in info.splitlines() if line.startswith('Pages:')))
        if actual_pages!=expected_pages:raise ValueError('Unexpected PDF pagination: '+pdf.name)
        text=subprocess.check_output(['pdftotext',str(pdf),'-'],text=True)
        required=('570.65' if 'Windows' in pdf.name else '570.26', 'admin1234!', '18093')
        if any(token not in text for token in required):raise ValueError('Missing PDF requirements: '+pdf.name)
    return {'linux_payload_files':count,'linux_gui_cli_payload_identical':True,
            'self_extractor_sha256_verified':True,'windows_pe_header_verified':True,
            'pdf_documents':len(pdfs),'layout_checks':checks}


def seal(output, checks):
    manifest={'application_baseline':json.loads((ROOT/'version.json').read_text())['version'],
              'installer_revision':REVISION,'build_source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'application_delivery':'Online clone of chosen branch/tag; default main. Not embedded or commit-pinned.',
              'driver_floor':{'windows':'570.65','linux':'570.26'},'cuda_runtime':'12.8',
              'internet_required_for_setup_and_updates':True,'models_included':False,
              'windows_native_e2e_verified':False,'package_checks':checks,
              'files':[{'path':p.relative_to(output).as_posix(),'bytes':p.stat().st_size,'sha256':digest(p)}
                       for p in sorted(output.rglob('*')) if p.is_file() and p.name not in ('release-manifest.json','SHA256SUMS.txt')]}
    sources=[ROOT/'deployment/build_final_release.py',ROOT/'deployment/build_gui_installer.py',ROOT/'deployment/build_unified_installer.py',ROOT/'deployment/build_installation_guides.py',ROOT/'deployment/installer/gui.py',ROOT/'deployment/installer/install.sh',ROOT/'deployment/native/bootstrap_python.py',ROOT/'deployment/native/conda_setup.py',ROOT/'deployment/native/install.sh',ROOT/'deployment/host/install.sh']
    manifest['build_source_files']={p.relative_to(ROOT).as_posix():digest(p) for p in sources}
    (output/'release-manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    files=[p for p in sorted(output.rglob('*')) if p.is_file() and p.name!='SHA256SUMS.txt']
    (output/'SHA256SUMS.txt').write_text(''.join(digest(p)+'  '+p.relative_to(output).as_posix()+'\n' for p in files))


def build(output=OUT):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    readme=(ROOT/'deployment/release-guide/START-HERE.txt').read_bytes()
    if len(list((output/'guides').glob('*.pdf')))!=4:raise RuntimeError('Build the four PDF guides before packaging.')
    extras={'START-HERE.txt':readme}
    for pdf in sorted((output/'guides').glob('*.pdf')):extras['guides/'+pdf.name]=pdf.read_bytes()
    with tempfile.TemporaryDirectory(prefix='mediauto-final-build-') as folder:
        stage=Path(folder);packages=stage/'payload';gui=stage/'gui'
        build_gui(gui, packages, extras=extras, exclude=('README.md','GUI_GUIDE.ko.md','install.bat','select.ps1'))
        with zipfile.ZipFile(packages/'MeDIAuto-GPU-installer-windows-x64.zip') as archive:
            validate_members(archive.namelist())
            if archive.testzip() is not None:raise ValueError('Windows payload ZIP integrity failed')
        for name in INSTALLERS[:2]:shutil.copy2(gui/name,output/name)
        shutil.copy2(packages/'MeDIAuto-GPU-installer-linux-x64.tar.gz',output/INSTALLERS[2])
    (output/'START-HERE.txt').write_bytes(readme)
    (output/'VALIDATION.txt').write_text('''Build validation — 2026-10-07-r18
Three customer-facing installers: Windows GUI EXE, Linux GUI RUN, Linux CLI TAR.GZ.
No standalone Windows CLI package is shipped.
Windows: NSIS compilation, source payload whitelist/integrity and PE header checked.
Linux: GUI/CLI payload equality, embedded SHA-256 and launcher shell syntax checked.
Linux Python 3.8 bootstrap regression tested with an actual Python 3.8 interpreter.
Conda creation/reuse/repair and GUI stdin preservation tested with isolated fixtures.
No clean Ubuntu 20.04 full installation was performed.
Four illustrated PDFs: browser layout/images and PDF parser checked.
Screenshots: real shared Tk GUI/SDK dialog on Linux; real frontend login rendering;
CLI startup output rendered for documentation. No simulated install success screens.
Models, application source checkout, accounts and operational data are not bundled.

Limits: No clean Windows installation or Windows-native screenshot was performed.
No host driver changes, reboot, GPU AI run or production DB installation were attempted.
Online setup downloads the selected branch/tag and packages; target-PC end-to-end
qualification is still required. The EXE is unsigned.
See test-results.txt for the automated regression test results for this revision.
''',encoding='utf-8')
    checks=verify(output);seal(output,checks)
    print('FINAL RELEASE:',output)
    for p in sorted(output.iterdir()):
        if p.is_file():print(p.name,p.stat().st_size)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=OUT);parser.add_argument('--verify-only',action='store_true')
    args=parser.parse_args()
    if args.verify_only:
        checks=verify(args.output);seal(args.output,checks);print('Verification passed; manifest and checksums refreshed.')
    else:build(args.output)
