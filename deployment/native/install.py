"""Native PostgreSQL and Python application installer. Only this installation's files/services are managed."""
import argparse
import hashlib
import getpass
import ipaddress
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
WINDOWS = os.name == 'nt'
PG_URL = 'https://get.enterprisedb.com/postgresql/postgresql-18.6-3-windows-x64.exe'
PG_SHA = '3bb55a421849fa5749fe807e45b05a9a7758a16389591ee0a41b7fcabf724b90'
PATHS = {'models': '/models', 'slides': '/data/uploads', 'patches': '/data/cell_annotation',
         'results': '/data/ai_results', 'annotations': '/data/annotations', 'tiles': '/data/tiles',
         'dicom': '/data/dicom_cache', 'secrets': '/state', 'temp': '/tmp', 'logs': '/logs', 'cache': '/cache', 'app_config': '/app-config'}
RUNTIME = ROOT / '.runtime'


def run(args, **kwargs):
    # Do not put passwords in command arguments or error messages.
    result = subprocess.run([str(x) for x in args], **kwargs)
    if result.returncode:
        raise RuntimeError(f'{Path(str(args[0])).name} failed (exit {result.returncode}).')
    return result


def output(args):
    return run(args, capture_output=True, text=True).stdout.strip()


def write_private(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not WINDOWS: path.parent.chmod(0o700)
    # Open with restrictive permissions from the first byte, including on retries.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f: f.write(value)
    if not WINDOWS: path.chmod(0o600)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda: f.read(4 * 1024 * 1024), b''): h.update(data)
    return h.hexdigest()


def ask(label, default):
    return input(f'{label} [{default}]: ').strip().strip('"') or str(default)


def port(value):
    number = int(value)
    if not 1024 <= number <= 65535: raise ValueError('Port must be 1024..65535.')
    return number


def validate(config):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', config['repository']): raise ValueError('Use a GitHub owner/repository name.')
    if not re.fullmatch(r'[a-zA-Z0-9_]{4,30}', config['admin_id']): raise ValueError('Invalid app administrator ID.')
    if not re.fullmatch(r'mediauto_native_[a-z0-9_]+', config['project']): raise ValueError('Invalid installation project name.')
    for key in ('db_password', 'pg_password'):
        if not re.fullmatch(r'[0-9a-f]{48}', config[key]): raise ValueError('Keep the generated DB passwords unchanged.')
    if len(config['admin_password'].encode()) + 43 > 72: raise ValueError('Admin password is too long for this app version.')
    if config['app_port'] == config['db_port']: raise ValueError('App and DB ports must differ.')
    port(config['app_port']); port(config['db_port'])
    ipaddress.ip_address(config['bind'])
    paths = [Path(config['paths'][key]) for key in (*PATHS, 'database')]
    if 'data_root' in config: paths.append(Path(config['data_root'])/'config')
    for p in paths:
        if not p.is_absolute() or p == Path(p.anchor): raise ValueError('Use absolute, non-root directories.')
        if any(c in str(p) for c in '\r\n\x00'): raise ValueError('Invalid path.')
        # Windows service and systemd quoting must remain unambiguous.
        if any(c in str(p) for c in '"%'): raise ValueError('Paths must not contain quotes or %.')
    for i, a in enumerate(paths):
        for b in paths[i+1:]:
            if a == b or a in b.parents or b in a.parents:
                raise ValueError('Storage directories must be separate, without nesting.')


def storage_paths(base, model_path, slide_path=''):
    base = Path(base).expanduser().resolve()
    paths = {key: str(base/key) for key in (*PATHS, 'database')}
    paths['models'] = str(Path(model_path).expanduser().resolve())
    paths['slides'] = str(Path(slide_path).expanduser().resolve()) if slide_path.strip() else str(base/'slides')
    return paths


def restore_runtime():
    global RUNTIME
    locator = ROOT/'.install-location.json'
    if locator.exists():
        RUNTIME = Path(json.loads(locator.read_text(encoding='utf-8'))['data_root'])/'config'


def configure():
    global RUNTIME
    restore_runtime()
    saved = RUNTIME/'settings.json'
    if saved.exists():
        config = json.loads(saved.read_text(encoding='utf-8'))
        if 'data_root' not in config:
            raise ValueError('Legacy multi-path installation detected. Use a new installer folder; data migration is separate.')
        validate(config)
        print('Existing configuration retained:', saved)
        return config
    default = 'C:/MeDIAutoData' if WINDOWS else '/srv/mediauto'
    base = Path(ask('External data root', default)).expanduser().resolve()
    model_path = input('Model folder (existing weights): ').strip().strip('"')
    if not model_path: raise ValueError('A separate model folder is required.')
    slide_path = input(f'Slide folder (Enter = {base / "slides"}): ').strip().strip('"')
    config = {'project': 'mediauto_native_' + secrets.token_hex(5), 'data_root': str(base),
              'paths': storage_paths(base, model_path, slide_path)}
    config['app_port'] = port(ask('Web port', 18093))
    config['db_port'] = port(ask('Dedicated PostgreSQL port', 55432))
    config['bind'] = ask('Web bind (0.0.0.0 = LAN, 127.0.0.1 = this PC)', '0.0.0.0')
    config['admin_id'] = 'admin'
    config['admin_password'] = 'admin'
    config['repository'] = ask('GitHub repository', 'Leeyoungsup/Mediauto-studio_saas')
    config['ref'] = ask('GitHub branch/tag/commit', 'main')
    config['db_password'] = secrets.token_hex(24)
    config['pg_password'] = secrets.token_hex(24)
    validate(config)
    RUNTIME = base/'config'
    if RUNTIME.exists() and any(RUNTIME.iterdir()):
        raise ValueError('The selected root already contains configuration. Reuse its original installer or select a new root.')
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if WINDOWS:
        import csv
        sid = next(csv.reader([output(['whoami','/user','/fo','csv','/nh'])]))[1]
        run(['icacls', RUNTIME, '/inheritance:r', '/grant:r', '*'+sid+':(OI)(CI)F',
             '*S-1-5-18:(OI)(CI)F', '*S-1-5-32-544:(OI)(CI)F'], stdout=subprocess.DEVNULL)
    write_private(RUNTIME/'settings.json', json.dumps(config,ensure_ascii=False,indent=2))
    # Locator contains no passwords. All installation secrets stay under the external root.
    (ROOT/'.install-location.json').write_text(json.dumps({'data_root':str(base)}), encoding='utf-8')
    return config


def check_ports(config):
    # A completed installation may already own its ports. The marker binds it to these paths.
    identity = {k: config[k] for k in ('project', 'paths', 'db_port')}
    old = RUNTIME / 'identity.json'
    if old.exists() and json.loads(old.read_text()) != identity:
        raise ValueError('Existing storage/DB settings changed. Restore settings; migrate with backup/restore first.')
    if not old.exists():
        for number in (config['app_port'], config['db_port']):
            with socket.socket() as s:
                try: s.bind(('0.0.0.0', number))
                except OSError: raise ValueError(f'Port {number} is already in use. Change settings before retrying.')
        write_private(old, json.dumps(identity))


def models(config):
    manifest = json.loads((ROOT/'model-checksums.json').read_text())
    target = Path(config['paths']['models'])
    for model in manifest:
        path = target/model['filename']
        if not path.is_file() or sha(path) != model['sha256']:
            raise ValueError('Missing or damaged model in the selected model folder: '+str(path))
    print('All 11 model files verified in the selected folder.')


def psql(config, binary, sql, database='postgres'):
    env = dict(os.environ, PGPASSWORD=config['pg_password'], PGCONNECT_TIMEOUT='10')
    return run([binary,'-X','-w','-h','127.0.0.1','-p',config['db_port'],'-U','postgres',
                '-d',database,'-v','ON_ERROR_STOP=1'],input=sql,text=True,env=env,capture_output=True).stdout


def ensure_windows_postgres_service(config, prefix):
    """Recover a missing service only for this install's already initialized DB."""
    import ntpath
    data = Path(config['paths']['database'])
    service = config['project'].replace('_', '-')
    pg_ctl = prefix/'bin'/'pg_ctl.exe'
    marker = RUNTIME/'db-initialization.json'
    expected = {'project':config['project'], 'database':str(data)}
    if not marker.exists() or json.loads(marker.read_text()) != expected:
        raise ValueError('Cannot register PostgreSQL service without matching installation ownership.')
    if not pg_ctl.is_file() or not all((data/name).is_file() for name in ('PG_VERSION', 'postgresql.conf', 'pg_hba.conf')):
        raise ValueError('PostgreSQL files are incomplete; inspect the PostgreSQL installation log.')
    query = "$ErrorActionPreference='Stop'; ConvertTo-Json -Compress -InputObject @(Get-CimInstance Win32_Service | Select-Object Name,PathName)"
    services = json.loads(output(['powershell','-NoProfile','-Command',query]))
    if isinstance(services, dict): services = [services]
    norm = lambda path: ntpath.normcase(ntpath.normpath(path))
    matches = []
    for entry in services:
        command = entry.get('PathName') or ''
        directory = re.search(r'(?:^|\s)-D\s+(?:"([^"]+)"|(\S+))', command)
        database = norm(next(part for part in directory.groups() if part)) if directory else None
        executable = re.match(r'^\s*(?:"([^"]+)"|(\S+))', command)
        program = norm(next(part for part in executable.groups() if part)) if executable else None
        if entry['Name'].lower() == service.lower():
            if database != norm(str(data)) or program != norm(str(pg_ctl)):
                raise ValueError('Service name belongs to a different PostgreSQL installation: '+service)
        if database == norm(str(data)):
            if program != norm(str(pg_ctl)):
                raise ValueError('This DB service uses a different PostgreSQL executable: '+entry['Name'])
            matches.append(entry['Name'])
    if len(matches) > 1:
        raise ValueError('Multiple services reference this DB; resolve duplicate registrations before continuing.')
    if matches:
        actual_service = matches[0]
        if not re.fullmatch(r'[A-Za-z0-9_-]+', actual_service):
            raise ValueError('Unsupported PostgreSQL service name: '+actual_service)
        print('Reusing verified PostgreSQL service: '+actual_service)
        return actual_service
    status = subprocess.run([str(pg_ctl), 'status', '-D', str(data)], capture_output=True, text=True)
    if status.returncode != 3:
        raise RuntimeError('Missing service but DB is running or status is uncertain; inspect PostgreSQL before retrying.')
    print('Registering missing PostgreSQL service: '+service, flush=True)
    run(['icacls',prefix,'/grant','*S-1-5-20:(OI)(CI)RX','/T'], stdout=subprocess.DEVNULL)
    run(['icacls',data,'/grant','*S-1-5-20:(OI)(CI)M','/T'], stdout=subprocess.DEVNULL)
    run([pg_ctl,'register','-N',service,'-D',data,'-S','auto','-U',r'NT AUTHORITY\NetworkService'])
    # Verify that the registered service is now visible to Windows.
    services = json.loads(output(['powershell','-NoProfile','-Command',query]))
    if isinstance(services, dict): services = [services]
    if not any(entry['Name'].lower() == service.lower() for entry in services):
        raise RuntimeError('PostgreSQL service registration did not create the expected service: '+service)
    return service


def database(config):
    data = Path(config['paths']['database'])
    service = config['project'].replace('_','-')
    claim_database(config)
    if WINDOWS:
        prefix = ROOT/'programs'/'postgresql'
        binary = prefix/'bin'/'psql.exe'
        if not binary.exists():
            if data.exists() and any(data.iterdir()):
                raise ValueError('DB data already exists but PostgreSQL binaries are missing; restore the installation first.')
            installer = RUNTIME/'postgresql-installer.exe'
            if not installer.exists() or sha(installer) != PG_SHA:
                print('Downloading PostgreSQL Windows installer...')
                urllib.request.urlretrieve(PG_URL, installer)
            if sha(installer) != PG_SHA: raise ValueError('PostgreSQL installer checksum mismatch.')
            options = RUNTIME/'postgresql-options.txt'
            lines = {'mode':'unattended','unattendedmodeui':'none','prefix':str(prefix),
                     'datadir':str(data),'serverport':config['db_port'],'servicename':service,
                     'superaccount':'postgres','superpassword':config['pg_password'],
                     'serviceaccount':r'NT AUTHORITY\NetworkService','servicepassword':'',
                     'enable-components':'server,commandlinetools','enable_acledit':'1'}
            write_private(options, ''.join(f'{k}={v}\n' for k,v in lines.items()))
            print('Installing PostgreSQL (this step may be quiet)...', flush=True)
            try: run([installer,'--optionfile',options])
            finally: options.unlink(missing_ok=True)
        if not (data/'PG_VERSION').exists(): raise ValueError('PostgreSQL installation incomplete; inspect installer logs before retrying.')
        service = ensure_windows_postgres_service(config, prefix)
    else:
        binaries = sorted(Path('/usr/lib/postgresql').glob('*/bin/initdb'), key=lambda p:int(p.parents[1].name))
        if not binaries: raise ValueError('PostgreSQL server package is missing.')
        version = int((data/'PG_VERSION').read_text().strip()) if (data/'PG_VERSION').exists() else int(binaries[-1].parents[1].name)
        bindir = Path(f'/usr/lib/postgresql/{version}/bin')
        binary = bindir/'psql'
        if not binary.exists(): raise ValueError('Install PostgreSQL '+str(version)+' before resuming this cluster.')
        if not (data/'PG_VERSION').exists():
            if data.exists() and any(data.iterdir()): raise ValueError('Refusing to initialize a nonempty database directory.')
            data.mkdir(parents=True,exist_ok=True)
            run(['chown','postgres:postgres',data]); data.chmod(0o700)
            # Allow the dedicated PostgreSQL OS account to traverse selected parent folders.
            for parent in data.parents:
                if parent != Path('/'): run(['setfacl','-m','u:postgres:--x',parent])
            fd, filename = tempfile.mkstemp(prefix='mediauto-initdb-')
            pw = Path(filename)
            with os.fdopen(fd, 'w') as f: f.write(config['pg_password'])
            run(['chown','postgres:postgres',pw])
            try:
                run(['runuser','-u','postgres','--',bindir/'initdb','-D',data,'-U','postgres',
                     '--auth-local=peer','--auth-host=scram-sha-256','--encoding=UTF8','--locale=C.UTF-8','--pwfile',pw])
            finally: pw.unlink(missing_ok=True)
        unit = (f'[Unit]\nDescription=MeDIAuto host PostgreSQL\nAfter=network.target\n\n'
                f'[Service]\nType=simple\nUser=postgres\nGroup=postgres\n'
                f'ExecStart="{bindir}/postgres" -D "{data}"\nRestart=on-failure\n'
                'KillSignal=SIGINT\nTimeoutStopSec=120\n\n[Install]\nWantedBy=multi-user.target\n')
        Path('/etc/systemd/system',service+'.service').write_text(unit)
    # This is a dedicated cluster, so its access policy is owned entirely by this installer.
    hba = ['local all postgres peer'] if not WINDOWS else []
    hba += ['host all all 127.0.0.1/32 scram-sha-256','host all all ::1/128 scram-sha-256',
            'host mediauto mediauto 127.0.0.1/32 scram-sha-256']
    (data/'pg_hba.conf').write_text('\n'.join(hba)+'\n',encoding='utf-8')
    extra = f"\n# MeDIAuto managed settings\nlisten_addresses = '127.0.0.1'\nport = {config['db_port']}\npassword_encryption = 'scram-sha-256'\nlogging_collector = on\nlog_directory = 'log'\nlog_filename = 'postgresql-%Y-%m-%d.log'\n"
    configfile = data/'postgresql.conf'
    original = configfile.read_text(encoding='utf-8').split('\n# MeDIAuto managed settings')[0]
    configfile.write_text(original+extra,encoding='utf-8')
    if WINDOWS:
        run(['powershell','-NoProfile','-Command',f"Restart-Service -Name '{service}' -ErrorAction Stop"])
    else:
        run(['systemctl','daemon-reload']); run(['systemctl','enable',service]); run(['systemctl','restart',service])
    for _ in range(30):
        try: psql(config,binary,'SELECT 1;'); break
        except RuntimeError: time.sleep(2)
    else: raise RuntimeError('Native PostgreSQL did not become ready. Check its service logs.')
    # Use a non-superuser application role. Passwords are random hexadecimal, SQL-safe.
    password = config['db_password']
    psql(config,binary, "SELECT 'CREATE ROLE mediauto LOGIN' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='mediauto')\\gexec\n"
          +f"ALTER ROLE mediauto PASSWORD '{password}';\n"
          +"SELECT 'CREATE DATABASE mediauto OWNER mediauto' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='mediauto')\\gexec\n")
    print('Native PostgreSQL is ready; application role has no superuser privileges.')


def claim_database(config):
    """Never adopt or reconfigure a pre-existing PostgreSQL cluster accidentally."""
    data = Path(config['paths']['database'])
    marker = RUNTIME/'db-initialization.json'
    identity = {'project':config['project'], 'database':str(data)}
    if marker.exists():
        if json.loads(marker.read_text()) != identity:
            raise ValueError('PostgreSQL initialization belongs to another installation.')
    else:
        if data.exists() and any(data.iterdir()):
            raise ValueError('Select an empty DB directory. Existing PostgreSQL data will not be modified.')
        write_private(marker,json.dumps(identity))


def prepare_application(config, source):
    RUNTIME.mkdir(parents=True,exist_ok=True)
    envdir=ROOT/'venv'
    python=envdir/('Scripts/python.exe' if WINDOWS else 'bin/python')
    if not python.exists():run([sys.executable,'-m','venv',envdir])
    run([python,'-m','pip','install','--upgrade','pip'])
    requirements=(source/'backend/requirements.txt').read_text(encoding='utf-8')
    if WINDOWS:
        # Modern bindings locate the bundled Windows DLLs without machine-wide PATH changes.
        requirements='\n'.join(line for line in requirements.splitlines() if not line.startswith(('openslide-python','pyvips')))
        requirements+='\nopenslide-python>=1.4.3,<2\nopenslide-bin\npyvips[binary]>=3.1,<4\n'
    native_requirements=RUNTIME/'requirements-native.txt'
    native_requirements.write_text(requirements,encoding='utf-8')
    run([python,'-m','pip','install','--upgrade','torch==2.11.0+cu128','torchvision==0.26.0+cu128','--index-url','https://download.pytorch.org/whl/cu128'])
    run([python,'-m','pip','install','-r',native_requirements])
    run([python,'-m','pip','check'])
    run([python,'-c','import openslide, pyvips, torch; assert pyvips.type_find("VipsOperation", "tiffsave"); print("Native OpenSlide/libvips/PyTorch imports passed")'])
    backend=source/'backend'
    for link,dest,isdir in [(backend/'.secrets.json',Path(config['paths']['secrets'])/'.secrets.json',False),
                             (backend/'cell_annotation',Path(config['paths']['patches']),True)]:
        if link.is_symlink():
            if link.resolve()!=dest.resolve():raise ValueError('Existing storage link points elsewhere: '+str(link))
        elif link.exists():raise ValueError('Refusing to replace existing application data: '+str(link))
        else:link.symlink_to(dest,target_is_directory=isdir)
    env={'POSTGRES_URI':f"postgresql+asyncpg://mediauto:{config['db_password']}@127.0.0.1:{config['db_port']}/mediauto",
         'MODEL_DIR':config['paths']['models'],'UPLOAD_DIR':config['paths']['slides'],'TILES_DIR':config['paths']['tiles'],
         'AI_RESULTS_DIR':config['paths']['results'],'ANNOTATIONS_DIR':config['paths']['annotations'],'DICOM_CACHE_DIR':config['paths']['dicom'],
         'YOLO_CONFIG_DIR':str(Path(config['paths']['app_config'])/'ultralytics'),'MPLCONFIGDIR':str(Path(config['paths']['cache'])/'matplotlib'),'TORCH_HOME':str(Path(config['paths']['cache'])/'torch'),'HF_HOME':str(Path(config['paths']['cache'])/'huggingface'),
         'XDG_CACHE_HOME':config['paths']['cache'],'XDG_CONFIG_HOME':config['paths']['app_config'],
         'TMPDIR':config['paths']['temp'],'TEMP':config['paths']['temp'],'TMP':config['paths']['temp'],
         'MEDIAUTO_BOOTSTRAP_ADMIN_ID':config['admin_id'],'MEDIAUTO_BOOTSTRAP_ADMIN_PASSWORD':config['admin_password'],
         'MEDIAUTO_BOOTSTRAP_ADMIN_NAME':'Administrator','TILE_CACHE_QUOTA_BYTES':'107374182400','PYTHONUNBUFFERED':'1'}
    from conda_setup import prepare as prepare_philips_environment, install_sdk
    philips = prepare_philips_environment(ROOT, config, WINDOWS)
    env.update(install_sdk(ROOT, config, WINDOWS, philips))
    app={'backend':str(backend),'env':env,'bind':config['bind'],'port':config['app_port'],'db_port':config['db_port'],
         'log':str(Path(config['paths']['logs'])/'app.log')}
    write_private(RUNTIME/'app.json',json.dumps(app,ensure_ascii=False,indent=2))
    Path(config['paths']['logs']).mkdir(parents=True,exist_ok=True)
    return python


def register_application(config, python):
    service=config['project'].replace('_','-')
    if WINDOWS:
        run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',ROOT/'register-task.ps1',
             '-PythonExe',python,'-Runner',ROOT/'runner.py','-Settings',RUNTIME/'app.json',
             '-TaskName',service+'-app','-Port',config['app_port'],'-Bind',config['bind']])
    else:
        import pwd
        account=os.environ.get('SUDO_USER') or 'mediauto-app'
        if account=='root':account='mediauto-app'
        try:entry=pwd.getpwnam(account)
        except KeyError:
            run(['useradd','--system','--no-create-home','--shell','/usr/sbin/nologin',account]);entry=pwd.getpwnam(account)
        for key in PATHS:
            directory=Path(config['paths'][key])
            for parent in (directory,*directory.parents):
                if parent!=Path('/'):run(['setfacl','-m',f'u:{account}:r-x',parent])
            if key!='models':os.chown(directory,entry.pw_uid,entry.pw_gid);directory.chmod(0o700)
        for parent in (ROOT,*ROOT.parents,RUNTIME):
            if parent!=Path('/'):run(['setfacl','-m',f'u:{account}:r-x',parent])
        run(['setfacl','-m',f'u:{account}:r--',RUNTIME/'app.json'])
        keyfile=Path(config['paths']['secrets'])/'.secrets.json'
        if keyfile.exists():os.chown(keyfile,entry.pw_uid,entry.pw_gid);keyfile.chmod(0o600)
        os.chown(config['paths']['logs'],entry.pw_uid,entry.pw_gid)
        text=(f'[Unit]\nDescription=MeDIAuto native app\nAfter=network.target {service}.service\nRequires={service}.service\n\n'
              f'[Service]\nType=simple\nUser={account}\nUMask=0077\n'
              f'ExecStart="{python}" "{ROOT}/runner.py" "{RUNTIME}/app.json"\n'
              'Restart=on-failure\nRestartSec=10\nTimeoutStopSec=120\n\n[Install]\nWantedBy=multi-user.target\n')
        Path('/etc/systemd/system',service+'-app.service').write_text(text.replace('%','%%'))
        run(['systemctl','daemon-reload']);run(['systemctl','enable',service+'-app']);run(['systemctl','restart',service+'-app'])


def main():
    if sys.version_info<(3,10):raise ValueError('Python 3.10 or newer is required.')
    if not WINDOWS and os.geteuid()!=0:raise ValueError('Run bash install.sh (sudo is required).')
    if platform.machine().lower() not in ('amd64','x86_64'):raise ValueError('x86-64 required.')
    config=configure();check_ports(config)
    try: run(['nvidia-smi','--query-gpu=name,driver_version','--format=csv,noheader'])
    except (RuntimeError,OSError): raise RuntimeError('NVIDIA GPU/driver is not ready. Resolve nvidia-smi errors; CPU fallback is disabled.')
    from github_source import download
    source=download(config,RUNTIME,ROOT)
    models(config)
    for key in PATHS:Path(config['paths'][key]).mkdir(parents=True,exist_ok=True)
    database(config)
    python=prepare_application(config,source)
    run([python,ROOT/'runner.py',RUNTIME/'app.json','--check'])
    register_application(config,python)
    for _ in range(90):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{config['app_port']}/api/health",timeout=3) as r:
                if r.status==200:break
        except OSError:pass
        time.sleep(2)
    else:raise RuntimeError('App did not become healthy. Check the external logs/app.log file.')
    write_private(RUNTIME/'ADMIN_LOGIN.txt',f"URL: http://localhost:{config['app_port']}\nID: {config['admin_id']}\nPassword: {config['admin_password']}\n")
    print(f"Ready: http://localhost:{config['app_port']}\nCredentials: {RUNTIME}/ADMIN_LOGIN.txt\nSource commit: "+source.name)


if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,OSError) as e:
        print('INSTALL FAILED:',e,file=sys.stderr);sys.exit(1)
