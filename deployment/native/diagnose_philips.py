"""Read-only Windows Philips DLL diagnostics; run with the Philips Python 3.7."""
import ctypes
import importlib
import os
from pathlib import Path
import platform
import struct
import sys
import traceback


def main():
    print('Python:', sys.version.replace('\n', ' '), flush=True)
    print('Executable:', sys.executable, flush=True)
    print('Architecture:', struct.calcsize('P') * 8, 'bit', platform.machine(), flush=True)
    if os.name != 'nt':
        print('This diagnostic targets Windows DLL loading.')
        return 1
    root = Path(sys.prefix)
    site = root/'Lib'/'site-packages'
    packages = ('pixelengine', 'softwarerendercontext', 'softwarerenderbackend',
                'eglrendercontext', 'gles2renderbackend', 'gles3renderbackend')
    dirs = [root, root/'Library'/'bin', root/'DLLs'] + [site/name for name in packages]
    os.environ['PATH'] = os.pathsep.join(str(path) for path in dirs if path.is_dir()) + os.pathsep + os.environ.get('PATH', '')
    handles = []
    if hasattr(os, 'add_dll_directory'):
        for directory in dirs:
            if directory.is_dir(): handles.append(os.add_dll_directory(str(directory)))
    print('\n--- Runtime DLLs ---', flush=True)
    for name in ('python37.dll', 'vcruntime140.dll', 'msvcp140.dll'):
        candidates = [path/name for path in dirs if (path/name).is_file()]
        target = str(candidates[0]) if candidates else name
        try:
            handles.append(ctypes.WinDLL(target))
            print('LOAD OK:', target, flush=True)
        except OSError as error:
            print('LOAD FAILED:', target, 'winerror=', error.winerror, str(error), flush=True)
    print('\n--- SDK files and dependencies ---', flush=True)
    # Load software render context before its dependent backend.
    for name in packages:
        directory = site/name
        print('\nPACKAGE:', name, 'DIRECTORY:', directory, flush=True)
        if not directory.is_dir():
            print('MISSING PACKAGE DIRECTORY', flush=True)
            continue
        print('FILES:', ', '.join(sorted(p.name for p in directory.iterdir() if p.is_file())), flush=True)
        for filename in ('pe_tbbmalloc.dll', 'pe_tbbmalloc_proxy.dll', 'libGLESv2.dll', 'libEGL.dll', name+'.dll', name+'.pyd'):
            path = directory/filename
            if not path.is_file():
                if filename in (name+'.dll', name+'.pyd'): print('MISSING:', path, flush=True)
                continue
            try:
                handles.append(ctypes.WinDLL(str(path)))
                print('LOAD OK:', filename, flush=True)
            except OSError as error:
                print('LOAD FAILED:', filename, 'winerror=', error.winerror, str(error), flush=True)
        try:
            module = importlib.import_module(name)
            print('IMPORT OK:', name, getattr(module,'__file__',''), flush=True)
        except Exception as error:
            print('IMPORT FAILED:', name, type(error).__name__, str(error), flush=True)
    print('\n--- OpenPhi Python dependencies ---', flush=True)
    for name in ('PIL.Image', 'numpy'):
        try:
            module = importlib.import_module(name)
            print('IMPORT OK:', name, getattr(module, '__file__', ''), flush=True)
        except Exception:
            print('IMPORT FAILED:', name, flush=True)
            traceback.print_exc(file=sys.stdout)
    try:
        from openphi import OpenPhi
        print('\nOpenPhi import OK:', OpenPhi.__module__, flush=True)
    except Exception as error:
        print('\nOpenPhi import FAILED:', type(error).__name__, str(error), flush=True)
        traceback.print_exc(file=sys.stdout)
    return 0


if __name__ == '__main__':
    sys.exit(main())
