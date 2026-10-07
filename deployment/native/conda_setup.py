"""Provide the second, ABI-specific Philips Python environment on native PCs."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request

RELEASE = 'py312_26.7.1-1'
INSTALLERS = {
    'windows': ('Windows-x86_64.exe', '8ae918681b0830314d85207f7a244352762b543bb83d53e0fcf77fbf270f8331'),
    'linux': ('Linux-x86_64.sh', 'b27f60ab63e77eeab50a5417c989120f767e863df32400190d4c7262369f8695'),
}



def download_with_system_trust(url, destination):
    """Keep TLS validation; retry certificate failures with Windows trust."""
    import ssl
    import urllib.error
    try:
        urllib.request.urlretrieve(url, destination)
        return
    except (urllib.error.URLError, ssl.SSLCertVerificationError) as exc:
        reason = getattr(exc, 'reason', exc)
        if os.name != 'nt' or not isinstance(reason, ssl.SSLCertVerificationError):
            raise
    print('Python certificate verification failed; retrying with Windows certificate validation...', flush=True)
    env = dict(os.environ, MEDIAUTO_DOWNLOAD_URL=url, MEDIAUTO_DOWNLOAD_FILE=str(Path(destination).resolve()))
    # Values travel as environment variables, never interpolated PowerShell code.
    script = (
        "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; "
        "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; "
        "try { Invoke-WebRequest -UseBasicParsing -Uri $env:MEDIAUTO_DOWNLOAD_URL "
        "-OutFile $env:MEDIAUTO_DOWNLOAD_FILE -TimeoutSec 600 -ErrorAction Stop; exit 0 } "
        "catch { [Console]::Error.WriteLine('Windows HTTPS download failed: '+$_.Exception.Message); exit 1 }"
    )
    result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
                            env=env, timeout=660)
    if result.returncode:
        raise RuntimeError('HTTPS certificate/download validation failed in Python and Windows. '
                           'Check Windows date/time, trusted root certificates and any company HTTPS proxy. '
                           'Certificate verification was not disabled.')


def invoke(args, **kwargs):
    command=[str(a) for a in args]
    if os.name!='nt' and os.environ.get('SUDO_USER') and Path(command[0]).name=='conda':
        command=['runuser','-u',os.environ['SUDO_USER'],'--']+command
    return subprocess.run(command, check=True, **kwargs)


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''): value.update(chunk)
    return value.hexdigest()


def find_conda(root, windows):
    relative = 'Scripts/conda.exe' if windows else 'bin/conda'
    candidates = [os.environ.get('CONDA_EXE'), shutil.which('conda.exe' if windows else 'conda'), str(root/'programs/miniconda3'/relative), str(root/'programs/miniforge3'/relative)]
    homes = [Path.home()]
    if os.environ.get('SUDO_USER') and not windows:
        import pwd
        homes.append(Path(pwd.getpwnam(os.environ['SUDO_USER']).pw_dir))
    for home in homes:
        for distribution in ('miniforge3', 'miniconda3', 'anaconda3'):
            candidates.append(str(home/distribution/relative))
    if windows:
        for home in (Path(os.environ.get('ProgramData', 'C:/ProgramData')), Path(os.environ.get('LOCALAPPDATA', str(Path.home())))):
            for distribution in ('miniforge3', 'miniconda3', 'anaconda3'):
                candidates.append(str(home/distribution/relative))
    for candidate in dict.fromkeys(candidates):
        if not candidate or not Path(candidate).is_file(): continue
        try:
            result = invoke([candidate, '--version'], capture_output=True, text=True)
            if result.stdout.strip().startswith('conda '): return Path(candidate)
        except (OSError, subprocess.CalledProcessError): pass
    return None


def named_prefix(conda, name):
    """Resolve only directories Conda searches for `activate NAME`."""
    info=json.loads(invoke([conda,'info','--json'],capture_output=True,text=True).stdout)
    directories=[Path(p) for p in info['envs_dirs']]
    for directory in directories:
        prefix=directory/name
        if (prefix/'conda-meta/history').is_file():return prefix
    return directories[0]/name


def initialize_shell(conda, windows):
    command=[conda,'init','cmd.exe' if windows else 'bash']
    if not windows and os.environ.get('SUDO_USER'):
        command=['runuser','-u',os.environ['SUDO_USER'],'--']+command
    invoke(command)


def ensure_linux_compatibility(conda, prefix, env):
    compatibility = prefix/'lib'
    if not all((compatibility/name).exists() for name in ('libcrypto.so.1.1','libtinyxml.so','libjpeg.so.8')):
        invoke([conda, 'install', '--yes', '--prefix', prefix, '--override-channels', '--channel', 'conda-forge',
                'python=3.8', 'openssl=1.1', 'tinyxml=2.6.2', 'libjpeg-turbo', 'libpng', 'libcurl', 'lcms2'], env=env)
    alias = compatibility/'libtinyxml.so.2.6.2'
    if not alias.exists():
        if not (compatibility/'libtinyxml.so').is_file(): raise RuntimeError('TinyXML compatibility library is missing.')
        alias.symlink_to('libtinyxml.so')


def ensure_conda(root, cache, windows):
    root = Path(root)
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    if not windows and os.environ.get('SUDO_USER'):
        import pwd
        user=pwd.getpwnam(os.environ['SUDO_USER'])
        for parent in (cache.parent,cache):os.chown(parent,user.pw_uid,user.pw_gid)
    conda = find_conda(root, windows)
    if conda is None:
        suffix, expected = INSTALLERS['windows' if windows else 'linux']
        name = 'Miniconda3-' + RELEASE + '-' + suffix
        installer = cache/name
        if not installer.exists() or digest(installer) != expected:
            print('Downloading Conda (official Miniconda)...', flush=True)
            temporary = installer.with_suffix(installer.suffix+'.partial')
            download_with_system_trust('https://repo.anaconda.com/miniconda/'+name, temporary)
            if digest(temporary) != expected:
                temporary.unlink()
                raise RuntimeError('Miniconda installer checksum mismatch.')
            temporary.replace(installer)
        prefix = root/'programs/miniconda3'
        if prefix.exists() and any(prefix.iterdir()):
            raise RuntimeError('Incomplete Miniconda installation: '+str(prefix))
        prefix.parent.mkdir(parents=True, exist_ok=True)
        print('Installing Conda (official Miniconda)...', flush=True)
        if windows:
            invoke([installer, '/InstallationType=JustMe', '/RegisterPython=0', '/AddToPath=0', '/S', '/D='+str(prefix)])
        else:
            command=['bash', installer, '-b', '-p', prefix]
            if os.environ.get('SUDO_USER'):
                import pwd
                user=pwd.getpwnam(os.environ['SUDO_USER'])
                os.chown(prefix.parent,user.pw_uid,user.pw_gid)
                command=['runuser','-u',os.environ['SUDO_USER'],'--']+command
            invoke(command)
        conda = find_conda(root, windows)
        if conda is None: raise RuntimeError('Conda installation did not produce a working executable.')
    return conda


def prepare(root, config, windows):
    root = Path(root)
    cache = Path(config['paths']['cache'])/'conda'
    conda = ensure_conda(root, cache, windows)
    minor = 7 if windows else 8
    name = 'philips-sdk-py3'+str(minor)
    initialize_shell(conda, windows)
    prefix = named_prefix(conda, name)
    python = prefix/('python.exe' if windows else 'bin/python')
    env = os.environ.copy()
    env.update(CONDA_PKGS_DIRS=str(cache/'pkgs'))
    if not python.is_file():
        if prefix.exists() and any(prefix.iterdir()):
            raise RuntimeError('Incomplete Philips environment: '+str(prefix))
        print('Creating second environment: '+name, flush=True)
        dependencies = ['python=3.'+str(minor), 'pip', 'numpy<2']
        if not windows:
            dependencies += ['pillow>=8,<11', 'openssl=1.1', 'tinyxml=2.6.2', 'libjpeg-turbo', 'libpng', 'libcurl', 'lcms2']
        invoke([conda, 'create', '--yes', '--name', name, '--override-channels', '--channel', 'conda-forge']+dependencies, env=env)
    prefix = named_prefix(conda, name)
    python = prefix/('python.exe' if windows else 'bin/python')
    if not windows: ensure_linux_compatibility(conda, prefix, env)
    if windows:
        # Always run pip through Conda so Python 3.7 can find OpenSSL DLLs.
        command = [conda, 'run', '--no-capture-output', '--name', name, 'python']
        pillow_probe = 'import ssl,PIL; from PIL import Image; assert PIL.__version__ == "9.5.0"; Image.new("RGB", (1, 1)).tobytes()'
        try:
            invoke(command+['-c', pillow_probe], env=env)
        except subprocess.CalledProcessError:
            print('Installing verified-compatible Windows Pillow 9.5.0 wheel...', flush=True)
            invoke(command+['-m','pip','install','--only-binary=:all:','--no-deps',
                            '--no-cache-dir','--force-reinstall','Pillow==9.5.0'], env=env)
            invoke(command+['-c', pillow_probe], env=env)
    # Import the compiled imaging extension, not just PIL's package metadata.
    probe = 'import sys,struct,numpy; from PIL import Image; assert sys.version_info[:2] == (3, %d) and struct.calcsize("P") == 8; Image.new("RGB", (1, 1)).tobytes(); print(sys.executable)' % minor
    invoke([conda, 'run', '--name', name, 'python', '-c', probe], env=env)
    print('Philips Python environment ready: '+str(python), flush=True)
    return {'PHILIPS_PYTHON':str(python), 'PHILIPS_CONDA_ENV':name}


def install_sdk(root, config, windows, settings):
    """Install the SDK shipped beside native/, then validate the actual bridge."""
    root = Path(root)
    bundle = root/'Philips_SDK' if (root/'Philips_SDK').is_dir() else root.parent/'Philips_SDK'
    manifest_path = bundle/'manifest.json'
    if not manifest_path.is_file():
        raise RuntimeError('Bundled Philips SDK is missing. Extract the complete installer archive, including Philips_SDK.')
    import json
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    expected_platform = 'windows' if windows else 'linux'
    if manifest['platform'] != expected_platform:
        raise RuntimeError('Philips SDK bundle does not match this operating system.')
    for entry in manifest['files']:
        path = bundle/entry['path']
        if path.is_symlink() or not path.resolve().is_relative_to(bundle.resolve()) or not path.is_file() or digest(path) != entry['sha256']:
            raise RuntimeError('Philips SDK checksum mismatch: '+entry['path'])
    sdk = bundle/manifest['sdk_directory']
    acceptance = sdk/'EULA Research.license.txt'
    state_path = Path(config['data_root'])/'config'/'philips-sdk.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    license_hash = digest(acceptance)
    if state.get('accepted_license_sha256') != license_hash:
        print('Philips SDK license: '+str(acceptance), flush=True)
        if input('Have you reviewed and accepted this SDK license? [y/N]: ').strip().lower() not in ('y','yes'):
            raise RuntimeError('Philips SDK installation requires acceptance of the bundled license.')
        state['accepted_license_sha256'] = license_hash
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state), encoding='utf-8')
    python = Path(settings['PHILIPS_PYTHON'])
    prefix = python.parent if windows else python.parent.parent
    conda = find_conda(root, windows)
    if conda is None: raise RuntimeError('Conda is unavailable for the Philips SDK installation.')
    env = os.environ.copy()
    env.update(settings)
    env.update(MEDIAUTO_ACCEPT_PHILIPS_EULA='1', CONDA_PKGS_DIRS=str(Path(config['paths']['cache'])/'conda/pkgs'),
               TMPDIR=config['paths']['temp'], TEMP=config['paths']['temp'], TMP=config['paths']['temp'],
               PIP_CACHE_DIR=str(Path(config['paths']['cache'])/'pip'))
    bootstrap = bundle/'support/scripts/bootstrap_philips.py'
    command = [conda,'run','--no-capture-output','--name',settings['PHILIPS_CONDA_ENV'],'python',bootstrap]
    fingerprint = digest(manifest_path)
    if state.get('installed_manifest_sha256') != fingerprint or state.get('python') != str(python):
        print('Installing bundled Philips SDK into the second environment...', flush=True)
        invoke(command+['--sdk-source',sdk], env=env)
    invoke(command+['--check-only'], env=env)
    state.update(installed_manifest_sha256=fingerprint, python=str(python))
    state_path.write_text(json.dumps(state), encoding='utf-8')
    return dict(settings, MEDIAUTO_ENABLE_PHILIPS='1')


def prepare_main(root, config, windows):
    """Create the GPU application Conda environment after Conda is provisioned."""
    root=Path(root)
    conda=find_conda(root,windows)
    if conda is None:raise RuntimeError('Conda was not provisioned.')
    name='medicus-saas'
    prefix=named_prefix(conda,name)
    python=prefix/('python.exe' if windows else 'bin/python')
    env=os.environ.copy()
    env['CONDA_PKGS_DIRS']=str(Path(config['paths']['cache'])/'conda/pkgs')
    if not python.is_file():
        if prefix.exists() and any(prefix.iterdir()):raise RuntimeError('Incomplete GPU Conda environment: '+str(prefix))
        invoke([conda,'create','--yes','--name',name,'--override-channels','--channel','conda-forge','python=3.12','pip'],env=env)
    if not windows:
        probe = ('import ctypes,sys; from pathlib import Path; '
                 'p=Path(sys.prefix)/"lib/libstdc++.so.6"; '
                 'assert b"CXXABI_1.3.15" in p.read_bytes(); '
                 'ctypes.CDLL(str(p), mode=ctypes.RTLD_GLOBAL)')
        runtime_check=[conda,'run','--no-capture-output','--name',name,'python','-c',probe]
        try:
            invoke(runtime_check, env=env, capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError):
            print('Preparing compatible Conda C++ runtime...', flush=True)
            invoke([conda,'install','--yes','--name',name,'--override-channels','--channel','conda-forge',
                    'libstdcxx-ng>=14','libgcc-ng>=14'],env=env)
            invoke(runtime_check, env=env, capture_output=True, text=True)
    prefix=named_prefix(conda,name)
    python=prefix/('python.exe' if windows else 'bin/python')
    command=[str(conda),'run','--no-capture-output','--name',name,'python']
    invoke(command+['-c','import sys,ssl,struct; assert sys.version_info[:2] == (3,12) and struct.calcsize("P")==8'],env=env)
    return python,command
