"""Host PostgreSQL + Docker app installer. Only this installation's files/services are managed."""
import argparse
import hashlib
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
IMAGE = 'haribo1/mediautoai:3.3.2-gpu@sha256:0826b31f2a3fce2933d1994a0b10b90148d7fa991a792763ee4a44047c2de364'
PG_URL = 'https://get.enterprisedb.com/postgresql/postgresql-18.6-3-windows-x64.exe'
PG_SHA = '3bb55a421849fa5749fe807e45b05a9a7758a16389591ee0a41b7fcabf724b90'
PATHS = {'models': '/models', 'slides': '/data/uploads', 'patches': '/data/cell_annotation',
         'results': '/data/ai_results', 'annotations': '/data/annotations', 'tiles': '/data/tiles',
         'dicom': '/data/dicom_cache', 'secrets': '/state', 'temp': '/tmp', 'logs': '/logs', 'cache': '/cache', 'app_config': '/app-config'}
RUNTIME = ROOT / '.runtime'



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
    if not re.fullmatch(r'mediauto_host_[a-z0-9_]+', config['project']): raise ValueError('Invalid installation project name.')
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
    config = {'project': 'mediauto_host_' + secrets.token_hex(5), 'data_root': str(base),
              'paths': storage_paths(base, model_path, slide_path)}
    config['app_port'] = port(ask('Web port', 18093))
    config['db_port'] = port(ask('Dedicated PostgreSQL port', 55432))
    config['bind'] = ask('Web bind (0.0.0.0 = LAN, 127.0.0.1 = this PC)', '0.0.0.0')
    config['repository'] = ask('GitHub repository', 'Leeyoungsup/Mediauto-studio_saas')
    config['ref'] = ask('GitHub branch/tag', 'main')
    config['admin_password'] = 'admin1234!'
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


class PortConflict(RuntimeError):
    pass


def port_available(number):
    with socket.socket() as probe:
        if WINDOWS:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind(('0.0.0.0', number))
            return True
        except OSError:
            return False


def choose_replacement_port(config, key):
    other = 'app_port' if key == 'db_port' else 'db_port'
    suggested = config[key] + 1
    while suggested <= 65535 and (suggested == config[other] or not port_available(suggested)):
        suggested += 1
    if suggested > 65535: suggested = 55433 if key == 'db_port' else 18094
    while True:
        try:
            selected = port(ask('New PostgreSQL port' if key == 'db_port' else 'New web port', suggested))
        except ValueError as error:
            print(error, flush=True)
            continue
        if selected == config[other]:
            print('Web and PostgreSQL ports must differ.', flush=True)
            continue
        if not port_available(selected):
            print('Port '+str(selected)+' is unavailable. Choose another port.', flush=True)
            continue
        config[key] = selected
        write_private(RUNTIME/'settings.json', json.dumps(config, ensure_ascii=False, indent=2))
        identity = {k:config[k] for k in ('project','paths','db_port')}
        write_private(RUNTIME/'identity.json', json.dumps(identity))
        print('Saved '+key+' = '+str(selected)+'. Continuing installation.', flush=True)
        return


def check_ports(config):
    # A completed installation may already own its ports. The marker binds it to these paths.
    identity = {k: config[k] for k in ('project', 'paths', 'db_port')}
    old = RUNTIME / 'identity.json'
    if old.exists() and json.loads(old.read_text()) != identity:
        raise ValueError('Existing storage/DB settings changed. Restore settings; migrate with backup/restore first.')
    if not old.exists():
        for key in ('app_port', 'db_port'):
            if not port_available(config[key]):
                print('Port '+str(config[key])+' is already in use.', flush=True)
                choose_replacement_port(config, key)
        write_private(old, json.dumps({k:config[k] for k in ('project','paths','db_port')}))


def models(config):
    manifest = json.loads((ROOT/'model-checksums.json').read_text())
    target = Path(config['paths']['models'])
    for model in manifest:
        path = target/model['filename']
        if not path.is_file() or sha(path) != model['sha256']:
            raise ValueError('Missing or damaged model in the selected model folder: '+str(path))
    print('All 11 model files verified in the selected folder.')


def network(config):
    name = config['project'] + '_network'
    r = subprocess.run(['docker','network','inspect',name], capture_output=True,text=True)
    if r.returncode:
        run(['docker','network','create','--label','mediauto.installer='+config['project'],name])
    info = json.loads(output(['docker','network','inspect',name]))[0]
    if info.get('Labels',{}).get('mediauto.installer') != config['project']:
        raise ValueError('Network belongs to another installation.')
    return name, info['IPAM']['Config'][0]['Subnet']


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
    status = subprocess.run([str(pg_ctl), 'status', '-D', str(data)], capture_output=True)
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


def prepare_windows_postgres(config):
    """Extract binaries and initialize only this install's explicitly owned DB.

    Avoid EDB's machine-wide installer/upgrade discovery of older clusters.
    """
    data = Path(config['paths']['database'])
    prefix = ROOT/'programs'/'postgresql'
    claim_database(config)
    required = ('psql.exe', 'pg_ctl.exe', 'postgres.exe', 'initdb.exe')
    extract_log = RUNTIME/'postgresql-extract.log'
    if not all((prefix/'bin'/name).is_file() for name in required):
        installer = RUNTIME/'postgresql-installer.exe'
        if not installer.exists() or sha(installer) != PG_SHA:
            print('Downloading PostgreSQL Windows installer...', flush=True)
            temporary = installer.with_suffix('.exe.partial')
            try:
                download_with_system_trust(PG_URL, temporary)
                if sha(temporary) != PG_SHA:
                    raise ValueError('PostgreSQL installer checksum mismatch.')
                temporary.replace(installer)
            finally:
                temporary.unlink(missing_ok=True)
        if sha(installer) != PG_SHA:
            raise ValueError('PostgreSQL installer checksum mismatch.')
        print('Extracting PostgreSQL binaries (no existing DB upgrade)...', flush=True)
        print('PostgreSQL extraction log: '+str(extract_log), flush=True)
        run([installer, '--mode','unattended','--unattendedmodeui','none',
             '--extract-only','1','--prefix',prefix,'--debugtrace',extract_log])
        if not all((prefix/'bin'/name).is_file() for name in required):
            raise RuntimeError('PostgreSQL binary extraction incomplete. Check '+str(extract_log))
        # Extract-only does not rely on the installer to configure Windows runtimes.
        runtime = prefix/'installer'/'vcredist_x64.exe'
        if runtime.is_file():
            result = subprocess.run([str(runtime),'/install','/quiet','/norestart'])
            if result.returncode == 3010:
                raise RuntimeError('PostgreSQL VC runtime requires a Windows restart; reboot and rerun install.bat.')
            if result.returncode not in (0, 1638):
                raise RuntimeError('PostgreSQL VC runtime failed (exit '+str(result.returncode)+').')
    # Validate binaries even on a retry after an interrupted installer.
    run([prefix/'bin'/'postgres.exe','--version'])
    if not (data/'PG_VERSION').is_file():
        if data.exists() and any(data.iterdir()):
            raise ValueError('DB initialization is incomplete in a nonempty folder; files were preserved: '+str(data))
        data.mkdir(parents=True, exist_ok=True)
        password_file = RUNTIME/'postgresql-init-password.txt'
        init_log = RUNTIME/'postgresql-initdb.log'
        write_private(password_file, config['pg_password']+'\n')
        print('Initializing PostgreSQL database: '+str(data), flush=True)
        try:
            # initdb itself obtains a restricted Windows token before creating the DB.
            with init_log.open('w', encoding='utf-8') as stream:
                result = subprocess.run([str(prefix/'bin'/'initdb.exe'),'-D',str(data),'-U','postgres',
                                         '--auth-local=scram-sha-256','--auth-host=scram-sha-256',
                                         '--encoding=UTF8','--locale=C','--pwfile',str(password_file)],
                                        stdout=stream, stderr=subprocess.STDOUT)
            if result.returncode:
                raise RuntimeError('PostgreSQL DB initialization failed; see '+str(init_log))
        finally:
            password_file.unlink(missing_ok=True)
    for name in ('PG_VERSION','postgresql.conf','pg_hba.conf','global/pg_control'):
        if not (data/name).is_file():
            raise RuntimeError('PostgreSQL DB file missing: '+str(data/name)+'; see '+str(RUNTIME/'postgresql-initdb.log'))
    service = ensure_windows_postgres_service(config, prefix)
    return prefix/'bin'/'psql.exe', service


def check_windows_db_listener(config):
    """Refuse a foreign listener even when a previous attempt wrote identity.json."""
    import ntpath
    number = port(config['db_port'])
    query = ("$ErrorActionPreference='Stop'; $ids=@(Get-NetTCPConnection -State Listen | "
             "Where-Object {$_.LocalPort -eq " + str(number) + "} | Select-Object -ExpandProperty OwningProcess -Unique); "
             "ConvertTo-Json -Compress -InputObject @(foreach ($owner in $ids) { "
             "Get-CimInstance Win32_Process -Filter ('ProcessId=' + $owner) | Select-Object ProcessId,ExecutablePath,CommandLine })")
    listeners = json.loads(output(['powershell','-NoProfile','-Command',query]))
    if isinstance(listeners, dict): listeners = [listeners]
    norm = lambda value: ntpath.normcase(ntpath.normpath(value))
    for entry in listeners:
        command = entry.get('CommandLine') or ''
        match = re.search(r'(?:^|\s)-D\s+(?:"([^"]+)"|(\S+))', command)
        data = next((part for part in match.groups() if part), '') if match else ''
        executable = entry.get('ExecutablePath') or ''
        if (norm(data) != norm(config['paths']['database']) or
                norm(executable) != norm(str(ROOT/'programs/postgresql/bin/postgres.exe'))):
            raise PortConflict('PostgreSQL port '+str(number)+' is occupied by another process: PID '+str(entry.get('ProcessId'))+
                               ', executable='+executable+', database='+data+
                               '. Stop the previous DB service if no longer needed, or choose a different DB port. No process was stopped.')


def restart_windows_postgres(config, service):
    check_windows_db_listener(config)
    try:
        run(['powershell','-NoProfile','-Command',f"Restart-Service -Name '{service}' -ErrorAction Stop"])
    except RuntimeError as error:
        print('PostgreSQL service failed to start. Windows service status:', flush=True)
        subprocess.run(['sc.exe','query',service])
        logdir = Path(config['paths']['database'])/'log'
        logs = sorted(logdir.glob('*.log'), key=lambda p:p.stat().st_mtime, reverse=True) if logdir.exists() else []
        if logs:
            print('Latest PostgreSQL log: '+str(logs[0]), flush=True)
            # Logging may use the Windows locale; never fail diagnostics on decoding.
            text = logs[0].read_bytes().decode('utf-8', errors='replace')
            print('\n'.join(text.splitlines()[-30:]), flush=True)
        else:
            print('No PostgreSQL server log was created. Check Windows Event Viewer for service '+service, flush=True)
        raise RuntimeError('PostgreSQL service startup failed; see the service error code and log above.') from error


def database(config, subnet):
    data = Path(config['paths']['database'])
    service = config['project'].replace('_','-')
    claim_database(config)
    if WINDOWS:
        binary, service = prepare_windows_postgres(config)
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
    if WINDOWS:
        while True:
            try:
                check_windows_db_listener(config)
                break
            except PortConflict as error:
                print(error, flush=True)
                choose_replacement_port(config, 'db_port')
    # This is a dedicated cluster, so its access policy is owned entirely by this installer.
    hba = ['local all postgres peer'] if not WINDOWS else []
    hba += ['host all all 127.0.0.1/32 scram-sha-256','host all all ::1/128 scram-sha-256',
            f'host mediauto mediauto {"samenet" if WINDOWS else subnet} scram-sha-256']
    (data/'pg_hba.conf').write_text('\n'.join(hba)+'\n',encoding='utf-8')
    extra = f"\n# MeDIAuto managed settings\nlisten_addresses = '*'\nport = {config['db_port']}\npassword_encryption = 'scram-sha-256'\nlogging_collector = on\nlog_directory = 'log'\nlog_filename = 'postgresql-%Y-%m-%d.log'\n"
    configfile = data/'postgresql.conf'
    original = configfile.read_text(encoding='utf-8').split('\n# MeDIAuto managed settings')[0]
    configfile.write_text(original+extra,encoding='utf-8')
    if WINDOWS:
        restart_windows_postgres(config, service)
        # Scope host DB access to local interfaces/subnets, never an Internet-wide DB rule.
        firewall = f"Get-NetFirewallRule -Name '{service}' -ErrorAction SilentlyContinue | Remove-NetFirewallRule; New-NetFirewallRule -Name '{service}' -DisplayName 'MeDIAuto PostgreSQL' -Direction Inbound -Action Allow -Protocol TCP -LocalPort {config['db_port']} -RemoteAddress LocalSubnet | Out-Null"
        run(['powershell','-NoProfile','-Command',firewall])
    else:
        run(['systemctl','daemon-reload']); run(['systemctl','enable',service]); run(['systemctl','restart',service])
        if shutil.which('ufw') and 'Status: active' in output(['ufw','status']):
            run(['ufw','allow','from',subnet,'to','any','port',config['db_port'],'proto','tcp'])
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


def compose(config, name):
    env = {'POSTGRES_URI':f"postgresql+asyncpg://mediauto:{config['db_password']}@host.docker.internal:{config['db_port']}/mediauto",
           'MEDIAUTO_SECRETS_FILE':'/state/.secrets.json','CELL_ANNOTATION_DIR':'/data/cell_annotation',
           'MODEL_DIR':'/models','UPLOAD_DIR':'/data/uploads','TILES_DIR':'/data/tiles',
           'AI_RESULTS_DIR':'/data/ai_results','ANNOTATIONS_DIR':'/data/annotations','DICOM_CACHE_DIR':'/data/dicom_cache',
           'TMPDIR':'/tmp','YOLO_CONFIG_DIR':'/app-config/ultralytics','MPLCONFIGDIR':'/cache/matplotlib','TORCH_HOME':'/cache/torch','HF_HOME':'/cache/huggingface','XDG_CACHE_HOME':'/cache','XDG_CONFIG_HOME':'/app-config','MEDIAUTO_BOOTSTRAP_ADMIN_ID':'admin',
           'MEDIAUTO_BOOTSTRAP_ADMIN_PASSWORD':config['admin_password'],'MEDIAUTO_BOOTSTRAP_ADMIN_NAME':'Administrator',
           'TILE_CACHE_QUOTA_BYTES':'107374182400'}
    write_private(RUNTIME/'app.env',''.join(f'{k}={v}\n' for k,v in env.items()))
    volumes = [{'type':'bind','source':str(Path(config['paths'][k])).replace('\\','/'),'target':v,
                'read_only':k=='models','bind':{'create_host_path':False}} for k,v in PATHS.items()]
    volumes.append({'type':'bind','source':str((ROOT/'container_runner.py').resolve()).replace('\\','/'), 'target':'/installer/container_runner.py','read_only':True,'bind':{'create_host_path':False}})
    volumes.append({'type':'bind','source':str((ROOT/'bootstrap_admin.py').resolve()).replace('\\','/'), 'target':'/installer/bootstrap_admin.py','read_only':True,'bind':{'create_host_path':False}})
    doc = {'name':config['project'],'services':{'app':{'image':config['project']+':local','build':{'context':str(ROOT/'application'),'dockerfile':str(ROOT/'Dockerfile.source'),'args':{'BASE_IMAGE':IMAGE}},'restart':'no','init':True,'shm_size':'1gb',
           'env_file':['app.env'],'entrypoint':['python','/installer/container_runner.py'],
           'deploy':{'resources':{'reservations':{'devices':[{'driver':'nvidia','count':'all','capabilities':['gpu']}]}}},
           'logging':{'driver':'none'},
           'ports':[{'target':8092,'published':str(config['app_port']),'host_ip':config['bind'],'protocol':'tcp'}],
           'volumes':volumes,'networks':['hostdb'],
           'healthcheck':{'test':['CMD','python','-c',"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8092/api/health', timeout=5)"],
                          'interval':'10s','timeout':'6s','retries':60,'start_period':'120s'}}},
           'networks':{'hostdb':{'external':True,'name':name}}}
    if not WINDOWS: doc['services']['app']['extra_hosts'] = ['host.docker.internal:host-gateway']
    # JSON is valid Compose YAML. Escape literal dollars to prevent Compose interpolation in paths.
    write_private(RUNTIME/'compose.json',json.dumps(doc,ensure_ascii=False,indent=2).replace('$','$$'))
    return ['docker','compose','-f',RUNTIME/'compose.json']


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--action',choices=['install','start','stop','status'],default='install')
    args=parser.parse_args()
    restore_runtime()
    if args.action != 'install':
        run(['docker','compose','-f',RUNTIME/'compose.json', *({'start':['up','--build','--abort-on-container-exit'], 'stop':['stop'],'status':['ps']}[args.action])]);return
    if not WINDOWS and os.geteuid() != 0: raise ValueError('Run bash install.sh; native service installation requires sudo.')
    if platform.machine().lower() not in ('amd64','x86_64'): raise ValueError('This release requires an x86-64 PC.')
    manifest = ROOT/'bundle-manifest.json'
    if manifest.exists():
        for entry in json.loads(manifest.read_text()):
            path = ROOT/entry['path']
            if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()) or sha(path) != entry['sha256']:
                raise ValueError('Installer bundle checksum mismatch: '+entry['path'])
    config=configure();check_ports(config)
    if 'repository' not in config:
        config['repository']=ask('GitHub repository','Leeyoungsup/Mediauto-studio_saas')
        config['ref']=ask('GitHub branch/tag','main')
        write_private(RUNTIME/'settings.json',json.dumps(config,ensure_ascii=False,indent=2))
    from github_source import download
    source=download(config,RUNTIME,ROOT)
    try:
        run(['nvidia-smi','--query-gpu=name,driver_version','--format=csv,noheader'])
    except (RuntimeError,OSError):
        raise RuntimeError('NVIDIA GPU/driver is not ready. Resolve nvidia-smi errors before installing; CPU fallback is disabled.')
    models(config)
    for key in PATHS:
        Path(config['paths'][key]).mkdir(parents=True,exist_ok=True)
    run(['docker','info'],stdout=subprocess.DEVNULL)
    if output(['docker','info','--format','{{.OSType}}']) != 'linux': raise ValueError('Switch Docker Desktop to Linux containers.')
    name,subnet=network(config)
    database(config,subnet)
    cmd=compose(config,name)
    run(cmd+['config','--quiet'])
    # Existing containers keep their old restart policy until explicitly updated.
    containers=output(cmd+['ps','-a','-q','app']).splitlines()
    for container in containers:
        run(['docker','update','--restart=no',container])
    if containers:run(cmd+['stop','app'])
    from local_setup import prepare as prepare_local
    prepare_local(config,source,ROOT,RUNTIME)
    run(cmd+['build'])
    (ROOT/'.python-path').write_text(sys.executable,encoding='utf-8')
    if not WINDOWS and os.environ.get('SUDO_USER'):
        import pwd
        account=pwd.getpwnam(os.environ['SUDO_USER'])
        for directory,dirs,files in os.walk(source):
            os.chown(directory,account.pw_uid,account.pw_gid)
            for filename in files:
                path=Path(directory)/filename
                if not path.is_symlink():os.chown(path,account.pw_uid,account.pw_gid)
    if WINDOWS and config['bind']=='0.0.0.0':
        rule=config['project']+'-web'
        run(['powershell','-NoProfile','-Command',f"Get-NetFirewallRule -Name '{rule}' -ErrorAction SilentlyContinue | Remove-NetFirewallRule; New-NetFirewallRule -Name '{rule}' -DisplayName 'MeDIAuto Web' -Direction Inbound -Action Allow -Protocol TCP -LocalPort {config['app_port']} -RemoteAddress LocalSubnet | Out-Null"])
    write_private(RUNTIME/'ADMIN_LOGIN.txt',f"URL: http://localhost:{config['app_port']}\nID: admin\nPassword: {config['admin_password']}\n")
    write_private(RUNTIME/'installed.json',json.dumps({'image':config['project']+':local','base_image':IMAGE,'source':str(source),'execution':'manual'}))
    print(f"Installation complete. App has NOT been started. Docker: start.bat / bash start.sh. Local: start-local.bat / bash start-local.sh.\nURL after start: http://localhost:{config['app_port']}\nLogin: {RUNTIME}/ADMIN_LOGIN.txt\nLAN access: use this server's IP address instead of localhost.")


if __name__=='__main__':
    try: main()
    except KeyboardInterrupt:
        print('Stopped by user.');sys.exit(130)
    except subprocess.CalledProcessError as e:
        print('INSTALL FAILED: dependency command failed (exit '+str(e.returncode)+'). See output above.',file=sys.stderr);sys.exit(1)
    except (ValueError,RuntimeError,OSError) as e:
        print('INSTALL FAILED:',e,file=sys.stderr);sys.exit(1)
