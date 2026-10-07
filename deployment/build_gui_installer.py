"""Build an NSIS Windows exe and Linux self-extracting GUI installer.

Requires makensis (or MAKENSIS env path); no application/models/data are embedded.
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile
from build_unified_installer import build as build_payload

ROOT=Path(__file__).resolve().parents[1]

def build(output=None, packages=None, extras=None, exclude=()):
    packages=Path(packages) if packages is not None else ROOT/'artifacts/local-deployment/unified'
    build_payload(packages, extras=extras, exclude=exclude)
    output=Path(output) if output is not None else ROOT/'artifacts/local-deployment/gui/2026-09-22-r16'
    output.mkdir(parents=True,exist_ok=True)
    compiler=os.environ.get('MAKENSIS') or shutil.which('makensis')
    if not compiler:raise RuntimeError('Install NSIS or set MAKENSIS to makensis.')
    exe=output/'MeDIAuto-Setup-windows-x64.exe'
    with tempfile.TemporaryDirectory(prefix='mediauto-gui-build-') as directory:
        temp=Path(directory)
        with zipfile.ZipFile(packages/'MeDIAuto-GPU-installer-windows-x64.zip') as z:z.extractall(temp)
        payload=temp/'MeDIAuto-GPU-installer'
        script=r'''
Unicode True
!include "MUI2.nsh"
!include "x64.nsh"
Name "MeDIAuto AI GPU Setup"
OutFile "@EXE@"
InstallDir "C:\MeDIAutoAI\MeDIAuto-GPU-installer"
RequestExecutionLevel admin
SetCompressor /SOLID lzma
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "MeDIAuto AI GPU Setup"
!define MUI_WELCOMEPAGE_TEXT "Internet access and administrator permission are required. NVIDIA GPU with Windows driver 570.65 or newer is required (CUDA 12.8 runtime). Model weights must be supplied separately.$\r$\n$\r$\nThis setup opens the graphical installer. A driver update may require a manual restart. Start the app manually after installation."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_LANGUAGE "English"
Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "An x86-64 Windows PC is required."
    Abort
  ${EndIf}
FunctionEnd
Section "Installer"
  SetOutPath "$INSTDIR"
  File /r "@PAYLOAD@/*"
  CreateShortcut "$DESKTOP\MeDIAuto Installer.lnk" "$INSTDIR\setup-gui.bat" "" "$INSTDIR\setup-gui.bat" 0 SW_SHOWNORMAL
  DetailPrint "Preparing Python and opening the graphical installer..."
  ExecWait '"$WINDIR\Sysnative\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\native\bootstrap.ps1" -Gui' $0
  ${If} $0 != 0
    MessageBox MB_ICONEXCLAMATION "Installer bootstrap did not complete. Reopen setup-gui.bat after resolving the displayed error."
    SetErrorLevel $0
    Abort
  ${EndIf}
SectionEnd
'''.replace('@EXE@',str(exe)).replace('@PAYLOAD@',str(payload))
        nsi=temp/'installer.nsi';nsi.write_text(script)
        subprocess.run([compiler,'-V2',str(nsi)],check=True)
    archive=packages/'MeDIAuto-GPU-installer-linux-x64.tar.gz'
    run=output/'MeDIAuto-Setup-linux-x64.run'
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    header='''#!/usr/bin/env bash
set -euo pipefail
if [[ "$(uname -m)" != x86_64 ]]; then echo 'x86-64 Linux is required.' >&2; exit 1; fi
if [[ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then echo 'A graphical desktop is required. For SSH use the CLI tar.gz installer.' >&2; exit 1; fi
payload=$(mktemp)
trap 'rm -f "$payload"' EXIT
line=$(awk '/^__MEDIAUTO_ARCHIVE_BELOW__$/ {print NR+1; exit}' "$0")
tail -n +"$line" "$0" > "$payload"
printf '%s  %s\\n' '@HASH@' "$payload" | sha256sum --check --status
# Fixed user-owned extraction directory; existing application/.git and data are not in this archive.
tar -xzf "$payload" -C "$HOME"
bash "$HOME/MeDIAuto-GPU-installer/setup-gui.sh"
exit $?
__MEDIAUTO_ARCHIVE_BELOW__
'''.replace('@HASH@',digest)
    with run.open('wb') as stream:stream.write(header.encode());stream.write(archive.read_bytes())
    run.chmod(0o755)
    shutil.copy2(ROOT/'deployment/installer/GUI_GUIDE.ko.md',output/'GUI_GUIDE.ko.md')
    files=[exe,run,output/'GUI_GUIDE.ko.md']
    (output/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in files))
    for p in files:print(p)

if __name__=='__main__':build()
