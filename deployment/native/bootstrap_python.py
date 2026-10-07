"""Linux installer bootstrap compatible with system Python 3.8.

Prepare Conda and a dedicated installer environment before loading any installer
code that requires Python 3.10+. Never read stdin: the GUI JSON/PAT pipe must reach
gui_worker.py untouched. Application and Philips environments are prepared later.
"""
import os
from pathlib import Path
import pwd
import subprocess
import sys

# Works both in a packaged docker/ directory and the development host/ tree.
try:
    import conda_setup
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'native'))
    import conda_setup

ENV_NAME = 'mediauto-installer'
PROBE = ('import sys,ssl,sqlite3,venv,struct; '
         'assert sys.version_info >= (3,10) and struct.calcsize("P")==8; '
         'print(sys.executable)')


def restore_invoking_user():
    """pkexec clears sudo metadata; Conda must still run as the desktop user."""
    if os.geteuid() == 0 and os.environ.get('PKEXEC_UID'):
        account = pwd.getpwuid(int(os.environ['PKEXEC_UID']))
        if account.pw_uid:
            os.environ.update(SUDO_USER=account.pw_name, SUDO_UID=str(account.pw_uid),
                              SUDO_GID=str(account.pw_gid))


def prepare(root):
    root = Path(root)
    cache = root / 'programs' / 'bootstrap-cache'
    print('[bootstrap] Preparing Conda and installer Python automatically...', flush=True)
    conda = conda_setup.ensure_conda(root, cache, False)
    print('[bootstrap] Using Conda: ' + str(conda), flush=True)
    # Ensure all subsequent installers reuse the same distribution, including
    # nonstandard locations passed by the CLI or discovered after pkexec.
    os.environ['CONDA_EXE'] = str(conda)
    env = os.environ.copy()
    env['CONDA_PKGS_DIRS'] = str(cache / 'pkgs')
    prefix = conda_setup.named_prefix(conda, ENV_NAME)
    python = prefix / 'bin/python'
    command = [conda, 'run', '--no-capture-output', '--name', ENV_NAME, 'python']
    ready = False
    if python.is_file():
        try:
            conda_setup.invoke(command + ['-c', PROBE], env=env, capture_output=True, text=True)
            ready = True
        except (OSError, subprocess.CalledProcessError):
            pass
    if not ready:
        # Repair only a registered installer environment; don't overwrite an
        # unrelated directory, or change the user's base Python.
        registered = (prefix / 'conda-meta/history').is_file()
        if prefix.exists() and any(prefix.iterdir()) and not registered:
            raise RuntimeError('Unmanaged/incomplete installer environment preserved: ' + str(prefix))
        action = 'install' if registered else 'create'
        print('[bootstrap] ' + ('Repairing' if registered else 'Creating') +
              ' isolated Python 3.12 environment: ' + ENV_NAME, flush=True)
        conda_setup.invoke([conda, action, '--yes', '--name', ENV_NAME,
                            '--override-channels', '--channel', 'conda-forge',
                            'python=3.12', 'pip'], env=env)
        prefix = conda_setup.named_prefix(conda, ENV_NAME)
        python = prefix / 'bin/python'
        conda_setup.invoke(command + ['-c', PROBE], env=env, capture_output=True, text=True)
    if not python.is_file():
        raise RuntimeError('Installer environment has no Python executable: ' + str(python))
    print('[bootstrap] Installer Python ready: ' + str(python), flush=True)
    return python


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        raise ValueError('Usage: bootstrap_python.py INSTALLER.py [arguments]')
    if os.geteuid() != 0:
        raise RuntimeError('Launch install.sh or the GUI to authorize installation.')
    restore_invoking_user()
    root = Path(__file__).resolve().parent
    target = Path(args[0]).resolve()
    if not target.is_file():
        raise RuntimeError('Installer entry point missing: ' + str(target))
    python = prepare(root)
    env = os.environ.copy()
    env.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
    # A parent Python/Conda activation must not inject incompatible stdlib paths.
    env.pop('PYTHONHOME', None)
    env.pop('PYTHONPATH', None)
    os.execve(str(python), [str(python), '-X', 'utf8', '-u', str(target)] + args[1:], env)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print('BOOTSTRAP FAILED: ' + str(exc), file=sys.stderr)
        sys.exit(1)
