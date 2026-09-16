"""Provide the second, ABI-specific Philips Python environment on native PCs."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request

RELEASE = '25.3.1-0'
INSTALLERS = {
    'windows': ('Windows-x86_64.exe', 'b7706a307b005fc397b70a244de19129100906928abccd5592580eb8296fb240'),
    'linux': ('Linux-x86_64.sh', '376b160ed8130820db0ab0f3826ac1fc85923647f75c1b8231166e3d559ab768'),
}


def invoke(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''): value.update(chunk)
    return value.hexdigest()


def find_conda(root, windows):
    relative = 'Scripts/conda.exe' if windows else 'bin/conda'
    candidates = [os.environ.get('CONDA_EXE'), shutil.which('conda.exe' if windows else 'conda'), str(root/'programs/miniforge3'/relative)]
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


def prepare(root, config, windows):
    root = Path(root)
    cache = Path(config['paths']['cache'])/'conda'
    cache.mkdir(parents=True, exist_ok=True)
    conda = find_conda(root, windows)
    if conda is None:
        suffix, expected = INSTALLERS['windows' if windows else 'linux']
        name = 'Miniforge3-' + RELEASE + '-' + suffix
        installer = cache/name
        if not installer.exists() or digest(installer) != expected:
            print('Downloading Conda (Miniforge)...', flush=True)
            temporary = installer.with_suffix(installer.suffix+'.partial')
            urllib.request.urlretrieve('https://github.com/conda-forge/miniforge/releases/download/'+RELEASE+'/'+name, temporary)
            if digest(temporary) != expected:
                temporary.unlink()
                raise RuntimeError('Miniforge installer checksum mismatch.')
            temporary.replace(installer)
        prefix = root/'programs/miniforge3'
        if prefix.exists() and any(prefix.iterdir()):
            raise RuntimeError('Incomplete Miniforge installation: '+str(prefix))
        prefix.parent.mkdir(parents=True, exist_ok=True)
        print('Installing Conda (Miniforge)...', flush=True)
        if windows:
            invoke([installer, '/InstallationType=JustMe', '/RegisterPython=0', '/AddToPath=0', '/S', '/D='+str(prefix)])
        else:
            invoke(['bash', installer, '-b', '-p', prefix])
        conda = find_conda(root, windows)
        if conda is None: raise RuntimeError('Conda installation did not produce a working executable.')
    minor = 7 if windows else 8
    name = 'philips-sdk-py3'+str(minor)
    prefix = root/'envs'/name
    python = prefix/('python.exe' if windows else 'bin/python')
    env = os.environ.copy()
    env.update(CONDA_PKGS_DIRS=str(cache/'pkgs'), CONDA_ENVS_PATH=str(root/'envs'))
    if not python.is_file():
        if prefix.exists() and any(prefix.iterdir()):
            raise RuntimeError('Incomplete Philips environment: '+str(prefix))
        print('Creating second environment: '+name, flush=True)
        invoke([conda, 'create', '--yes', '--prefix', prefix, '--override-channels', '--channel', 'conda-forge',
                'python=3.'+str(minor), 'pip', 'numpy<2', 'pillow>=8,<11'], env=env)
    probe = 'import sys,struct,numpy,PIL; assert sys.version_info[:2] == (3, %d) and struct.calcsize("P") == 8; print(sys.executable)' % minor
    invoke([conda, 'run', '--prefix', prefix, 'python', '-c', probe], env=env)
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
    command = [conda,'run','--no-capture-output','--prefix',prefix,'python',bootstrap]
    fingerprint = digest(manifest_path)
    if state.get('installed_manifest_sha256') != fingerprint or state.get('python') != str(python):
        print('Installing bundled Philips SDK into the second environment...', flush=True)
        invoke(command+['--sdk-source',sdk], env=env)
    invoke(command+['--check-only'], env=env)
    state.update(installed_manifest_sha256=fingerprint, python=str(python))
    state_path.write_text(json.dumps(state), encoding='utf-8')
    return dict(settings, MEDIAUTO_ENABLE_PHILIPS='1')
