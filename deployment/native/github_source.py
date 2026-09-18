"""Create an editable Git checkout; never update or reset an existing checkout."""
import base64
import getpass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def git(args, target=None, env=None):
    command=['git']
    if target is not None:
        command += ['-c','safe.directory='+str(target.resolve()),'-C',str(target)]
    result=subprocess.run(command+args,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if result.returncode:
        # Authentication may be echoed by Git; never include raw error output.
        raise RuntimeError('Git operation failed: '+args[0]+'. Check GitHub access, branch and network. Existing files were preserved.')
    return result.stdout.strip()


# Ignore the path itself as well as children: a Windows directory link can be
# committed as a single Git object even when "directory/*" is ignored.
RUNTIME_PATHS = (
    'backend/cell_annotation', 'backend/.secrets.json', 'backend/uploads',
    'backend/tiles', 'backend/ai_results', 'backend/annotations',
    'backend/dicom_cache', 'backend/model',
)


def protect_runtime_storage(config, target):
    checkout = target.resolve()
    for name, value in config.get('paths', {}).items():
        path = Path(value).expanduser().resolve()
        if path == checkout or checkout in path.parents:
            raise ValueError('Storage path must be outside the Git checkout: '+name+
                             '. Choose an external folder; existing data was preserved.')
    tracked = git(['ls-files', '-z', '--', *RUNTIME_PATHS], target)
    if tracked:
        paths = tracked.split('\0')
        raise ValueError('Selected Git checkout tracks runtime data or a machine-specific link: '+
                         ', '.join(paths[:8])+'. Remove these paths from Git tracking and commit '+
                         'the fix on the source branch before retrying. The installer did not delete data or change the index.')
    # Local exclusion also protects old branches whose .gitignore only excludes
    # directory contents. It does not modify tracked source or the user's index.
    exclude = Path(git(['rev-parse', '--git-path', 'info/exclude'], target))
    if not exclude.is_absolute():
        exclude = target/exclude
    existing = exclude.read_text(encoding='utf-8') if exclude.exists() else ''
    rules = ['/'+path for path in RUNTIME_PATHS]
    missing = [rule for rule in rules if rule not in existing.splitlines()]
    if missing:
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open('a', encoding='utf-8') as stream:
            stream.write('\n# MeDIAuto: local runtime data and compatibility links\n'+'\n'.join(missing)+'\n')


def download(config, runtime, root):
    if not shutil.which('git'):
        raise RuntimeError('Git is required. Install Git and restart the installer.')
    repository=config['repository'];ref=config['ref']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):raise ValueError('Invalid repository name.')
    if not ref or ref.startswith('-'):raise ValueError('Select a Git branch or tag.')
    target=root/'application'
    marker=runtime/'source.json'
    if (target/'.git').is_dir():
        remote=git(['remote','get-url','origin'],target)
        if remote.rstrip('/').removesuffix('.git').lower() != ('https://github.com/'+repository).lower():
            raise ValueError('Existing checkout origin differs from the selected repository; files were preserved.')
        print('Reusing Git working tree without checkout, pull, reset or clean: '+str(target),flush=True)
    elif target.exists():
        raise ValueError('Source folder already exists without .git (possibly an older archive installation). Use a new installer folder; existing code was preserved.')
    else:
        username=input('GitHub username (blank for public repository): ').strip()
        env=os.environ.copy()
        env.update(GIT_TERMINAL_PROMPT='0',GIT_CONFIG_COUNT='2',GIT_CONFIG_KEY_0='credential.helper',GIT_CONFIG_VALUE_0='',GIT_CONFIG_KEY_1='http.followRedirects',GIT_CONFIG_VALUE_1='false')
        if username:
            token=getpass.getpass('GitHub personal access token (PAT): ')
            if not token:raise ValueError('A GitHub token is required.')
            env.update(GIT_CONFIG_COUNT='3',GIT_CONFIG_KEY_2='http.https://github.com/.extraheader',
                       GIT_CONFIG_VALUE_2='Authorization: Basic '+base64.b64encode((username+':'+token).encode()).decode())
            del token
        print('Cloning editable Git working tree...',flush=True)
        try:
            git(['clone','--branch',ref,'--','https://github.com/'+repository+'.git',str(target)],env=env)
        finally:
            env.clear()
    if not (target/'backend/main.py').is_file():raise ValueError('Selected checkout has no backend/main.py.')
    protect_runtime_storage(config, target)
    commit=git(['rev-parse','HEAD'],target)
    branch=git(['rev-parse','--abbrev-ref','HEAD'],target)
    marker.write_text(json.dumps({'repository':repository,'requested_ref':ref,'branch':branch,'commit':commit,'path':str(target),'mode':'git'},indent=2))
    print('Source branch: '+branch+'; commit: '+commit,flush=True)
    return target
