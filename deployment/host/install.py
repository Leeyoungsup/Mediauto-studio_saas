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
IMAGE = 'haribo1/mediautoai:3.3.2@sha256:d940813b3fc46763e5722517c5bd2b568279bf3e68741adad0f25280c89aac05'
PG_URL = 'https://get.enterprisedb.com/postgresql/postgresql-18.6-3-windows-x64.exe'
PG_SHA = '3bb55a421849fa5749fe807e45b05a9a7758a16389591ee0a41b7fcabf724b90'
PATHS = {'models': '/models', 'slides': '/data/uploads', 'patches': '/data/cell_annotation',
         'results': '/data/ai_results', 'annotations': '/data/annotations', 'tiles': '/data/tiles',
         'dicom': '/data/dicom_cache', 'secrets': '/state', 'temp': '/tmp'}
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
    if not re.fullmatch(r'mediauto_host_[a-z0-9_]+', config['project']): raise ValueError('Invalid installation project name.')
    for key in ('db_password', 'pg_password'):
        if not re.fullmatch(r'[0-9a-f]{48}', config[key]): raise ValueError('Keep the generated DB passwords unchanged.')
    if len(config['admin_password'].encode()) + 43 > 72: raise ValueError('Admin password is too long for this app version.')
    if config['app_port'] == config['db_port']: raise ValueError('App and DB ports must differ.')
    port(config['app_port']); port(config['db_port'])
    ipaddress.ip_address(config['bind'])
    paths = [Path(config['paths'][key]) for key in (*PATHS, 'database')]
    for p in paths:
        if not p.is_absolute() or p == Path(p.anchor): raise ValueError('Use absolute, non-root directories.')
        if any(c in str(p) for c in '\r\n\x00'): raise ValueError('Invalid path.')
        # Windows service and systemd quoting must remain unambiguous.
        if any(c in str(p) for c in '"%'): raise ValueError('Paths must not contain quotes or %.')
    for i, a in enumerate(paths):
        for b in paths[i+1:]:
            if a == b or a in b.parents or b in a.parents:
                raise ValueError('Storage directories must be separate, without nesting.')


def configure():
    saved = RUNTIME / 'settings.json'
    if saved.exists():
        config = json.loads(saved.read_text(encoding='utf-8'))
        validate(config)
        print('Resuming saved installation. Paths: .runtime/settings.json')
        return config
    default = 'C:/MeDIAutoData' if WINDOWS else '/srv/mediauto'
    base = Path(ask('Data root (local disk)', default)).expanduser().resolve()
    config = {'project': 'mediauto_host_' + secrets.token_hex(5), 'paths': {}}
    for key in (*PATHS, 'database'):
        config['paths'][key] = str(Path(ask(key + ' directory', base/key)).expanduser().resolve())
    config['app_port'] = port(ask('Web port', 18093))
    config['db_port'] = port(ask('Dedicated PostgreSQL port', 55432))
    config['bind'] = ask('Web bind (0.0.0.0 = LAN, 127.0.0.1 = this PC)', '0.0.0.0')
    config['admin_password'] = secrets.token_hex(12) + 'Aa!'
    config['db_password'] = secrets.token_hex(24)
    config['pg_password'] = secrets.token_hex(24)
    validate(config)
    write_private(saved, json.dumps(config, ensure_ascii=False, indent=2))
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
    source = ROOT/'models'
    if not source.is_dir() and not all((target/m['filename']).is_file() for m in manifest):
        source = Path(ask('Existing model source folder', target)).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    for model in manifest:
        dest = target/model['filename']
        if dest.exists():
            if sha(dest) != model['sha256']: raise ValueError('Model hash mismatch: '+str(dest))
        else:
            src = source/model['filename']
            if not src.is_file() or sha(src) != model['sha256']:
                raise ValueError('Missing or damaged model: '+str(src))
            tmp = dest.with_suffix(dest.suffix+'.copying')
            shutil.copyfile(src, tmp)
            if sha(tmp) != model['sha256']: raise ValueError('Model copy verification failed.')
            tmp.replace(dest)
    print('All model files verified.')


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


def database(config, subnet):
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
                     'serviceaccount':r'NT AUTHORITY\NetworkService',
                     'enable-components':'server,commandlinetools','enable_acledit':'1'}
            write_private(options, ''.join(f'{k}={v}\n' for k,v in lines.items()))
            try: run([installer,'--optionfile',options])
            finally: options.unlink(missing_ok=True)
        if not (data/'PG_VERSION').exists(): raise ValueError('PostgreSQL installation incomplete; inspect installer logs before retrying.')
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
            f'host mediauto mediauto {"samenet" if WINDOWS else subnet} scram-sha-256']
    (data/'pg_hba.conf').write_text('\n'.join(hba)+'\n',encoding='utf-8')
    extra = f"\n# MeDIAuto managed settings\nlisten_addresses = '*'\nport = {config['db_port']}\npassword_encryption = 'scram-sha-256'\n"
    configfile = data/'postgresql.conf'
    original = configfile.read_text(encoding='utf-8').split('\n# MeDIAuto managed settings')[0]
    configfile.write_text(original+extra,encoding='utf-8')
    if WINDOWS:
        run(['powershell','-NoProfile','-Command',f"Restart-Service -Name '{service}' -ErrorAction Stop"])
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
           'MODEL_DIR':'/models','UPLOAD_DIR':'/data/uploads','TILES_DIR':'/data/tiles',
           'AI_RESULTS_DIR':'/data/ai_results','ANNOTATIONS_DIR':'/data/annotations','DICOM_CACHE_DIR':'/data/dicom_cache',
           'TMPDIR':'/tmp','MEDIAUTO_BOOTSTRAP_ADMIN_ID':'admin',
           'MEDIAUTO_BOOTSTRAP_ADMIN_PASSWORD':config['admin_password'],'MEDIAUTO_BOOTSTRAP_ADMIN_NAME':'Administrator',
           'TILE_CACHE_QUOTA_BYTES':'107374182400'}
    write_private(RUNTIME/'app.env',''.join(f'{k}={v}\n' for k,v in env.items()))
    volumes = [{'type':'bind','source':str(Path(config['paths'][k])).replace('\\','/'),'target':v,
                'read_only':k=='models','bind':{'create_host_path':False}} for k,v in PATHS.items()]
    doc = {'name':config['project'],'services':{'app':{'image':IMAGE,'restart':'unless-stopped','init':True,'shm_size':'1gb',
           'env_file':['app.env'],
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
    if args.action != 'install':
        run(['docker','compose','-f',RUNTIME/'compose.json', *({'start':['up','-d','--wait','--wait-timeout','900'], 'stop':['stop'],'status':['ps']}[args.action])]);return
    if not WINDOWS and os.geteuid() != 0: raise ValueError('Run bash install.sh; native service installation requires sudo.')
    if platform.machine().lower() not in ('amd64','x86_64'): raise ValueError('This release requires an x86-64 PC.')
    manifest = ROOT/'bundle-manifest.json'
    if manifest.exists():
        for entry in json.loads(manifest.read_text()):
            path = ROOT/entry['path']
            if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()) or sha(path) != entry['sha256']:
                raise ValueError('Installer bundle checksum mismatch: '+entry['path'])
    config=configure();check_ports(config)
    models(config)
    for key in PATHS:
        Path(config['paths'][key]).mkdir(parents=True,exist_ok=True)
    run(['docker','info'],stdout=subprocess.DEVNULL)
    if output(['docker','info','--format','{{.OSType}}']) != 'linux': raise ValueError('Switch Docker Desktop to Linux containers.')
    name,subnet=network(config)
    database(config,subnet)
    cmd=compose(config,name)
    run(cmd+['config','--quiet']);run(cmd+['pull']);run(cmd+['up','-d','--no-build','--wait','--wait-timeout','900'])
    if WINDOWS and config['bind']=='0.0.0.0':
        rule=config['project']+'-web'
        run(['powershell','-NoProfile','-Command',f"Get-NetFirewallRule -Name '{rule}' -ErrorAction SilentlyContinue | Remove-NetFirewallRule; New-NetFirewallRule -Name '{rule}' -DisplayName 'MeDIAuto Web' -Direction Inbound -Action Allow -Protocol TCP -LocalPort {config['app_port']} -RemoteAddress LocalSubnet | Out-Null"])
    write_private(RUNTIME/'ADMIN_LOGIN.txt',f"URL: http://localhost:{config['app_port']}\nID: admin\nPassword: {config['admin_password']}\n")
    write_private(RUNTIME/'installed.json',json.dumps({'image':IMAGE,'version':'3.3.2'}))
    print(f"Ready: http://localhost:{config['app_port']}\nLogin: .runtime/ADMIN_LOGIN.txt\nLAN access: use this server's IP address instead of localhost.")


if __name__=='__main__':
    try: main()
    except (ValueError,RuntimeError,OSError) as e:
        print('INSTALL FAILED:',e,file=sys.stderr);sys.exit(1)
