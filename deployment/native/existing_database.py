"""Explicit, backed-up recovery/reset of a verified Linux MeDIAuto cluster."""
import datetime
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess


def command(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def output(args):
    return command(args, capture_output=True, text=True).stdout.strip()


def discover(data):
    data = Path(data).resolve()
    if data.is_symlink() or not (data/'PG_VERSION').is_file():
        raise ValueError('Existing folder is not a verified PostgreSQL cluster; preserved.')
    matches=[]
    for unit in Path('/etc/systemd/system').glob('mediauto-*.service'):
        if unit.is_symlink():
            continue
        text=unit.read_text()
        match=re.search(r'^ExecStart="(/usr/lib/postgresql/(\d+)/bin/postgres)" -D "([^"\n]+)"$',text,re.M)
        if match and Path(match[3]).resolve()==data:
            if not re.fullmatch(r'mediauto-(native|host)-[a-z0-9]+',unit.stem):
                continue
            matches.append((unit,match))
    if len(matches)!=1:
        raise ValueError('Cannot uniquely identify the existing MeDIAuto service. Database preserved.')
    unit,match=matches[0]
    if output(['systemctl','is-active',unit.name])!='active':
        raise ValueError('Existing DB service must be running for verified backup/recovery. Database preserved.')
    lines=(data/'postmaster.pid').read_text().splitlines()
    if len(lines)<5 or output(['systemctl','show',unit.name,'-p','MainPID','--value'])!=lines[0]:
        raise ValueError('Service PID and database PID differ. Database preserved.')
    if Path(lines[1]).resolve()!=data or not lines[4].startswith('/'):
        raise ValueError('Unexpected PostgreSQL data/socket directory.')
    if (data/'PG_VERSION').read_text().strip()!=match[2]:
        raise ValueError('PostgreSQL binary and cluster versions differ.')
    info={'service':unit.name,'project':unit.stem.replace('-','_'), 'data':data,
          'bin':Path(match[1]).parent,'port':int(lines[3]),'socket':lines[4], 'pid':lines[0]}
    if Path(sql(info,'SHOW data_directory')).resolve()!=data:
        raise ValueError('Connected to a different database cluster.')
    if sql(info,"SELECT count(*) FROM pg_database WHERE datname='mediauto'")!='1':
        raise ValueError('Existing service has no mediauto database; preserved.')
    if sql(info,"SELECT count(*) FROM pg_database WHERE NOT datistemplate AND datname NOT IN ('postgres','mediauto')")!='0':
        raise ValueError('Cluster contains other databases; automatic recovery/reset is disabled.')
    return info


def connection(info):
    return ['-h',info['socket'],'-p',str(info['port']),'-U','postgres','-w']


def pg_env():
    env={k:v for k,v in os.environ.items() if not k.startswith('PG')}
    env['PGCONNECT_TIMEOUT']='10'
    return env


def sql(info,text):
    result=command(['runuser','-u','postgres','--',info['bin']/'psql','-X','-A','-t',
                    *connection(info),'-d','postgres','-v','ON_ERROR_STOP=1'],
                   input=text,text=True,capture_output=True,env=pg_env())
    return result.stdout.strip()


def backup(info,config,runtime):
    base=Path(config['data_root'])
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder=base/'recovery-backups'/stamp
    folder.mkdir(parents=True,mode=0o700)
    folder.chmod(0o700)
    shutil.copytree(runtime,folder/'config',symlinks=True)
    keys=Path(config['paths']['secrets'])
    if keys.exists():shutil.copytree(keys,folder/'secrets',symlinks=True)
    shutil.copy2(Path('/etc/systemd/system')/info['service'],folder/info['service'])
    for name in ('postgresql.conf','postgresql.auto.conf','pg_hba.conf'):
        if (info['data']/name).is_file():shutil.copy2(info['data']/name,folder/name)
    partial=folder/'cluster.sql.partial'
    fd=os.open(partial,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:
        command(['runuser','-u','postgres','--',info['bin']/'pg_dumpall',*connection(info)],
                stdout=stream,env=pg_env())
        stream.flush();os.fsync(stream.fileno())
    if partial.stat().st_size==0:raise ValueError('Empty backup; recovery stopped.')
    partial.rename(folder/'cluster.sql')
    print('Backup complete (private): '+str(folder),flush=True)
    return folder


def handle(config,runtime,write_private,windows=False):
    """Return before ordinary install; no mutations before explicit selection."""
    runtime=Path(runtime);data=Path(config['paths']['database'])
    if not data.exists() or not any(data.iterdir()):return
    if data.is_symlink():raise ValueError('Symlinked database directory preserved; recovery requires a direct path.')
    marker=runtime/'db-initialization.json'
    owned=marker.is_file() and json.loads(marker.read_text())=={'project':config['project'],'database':str(data)}
    print('Existing MeDIAuto database detected: '+str(data),flush=True)
    # Windows service discovery/backup uses a different authentication model.
    # Preserve its existing verified path; never silently adopt or reset it.
    if windows:
        if owned:return
        raise ValueError('Existing Windows DB has no matching ownership record. Preserved; restore its original settings.')
    choice=input('Existing DB / 기존 DB: 1=유지·복구 Keep/recover (default), 2=백업 후 DB 초기화 Reset DB after backup, 0=취소 Cancel: ').strip() or '1'
    if choice=='0':raise ValueError('Cancelled; existing database preserved.')
    if choice not in ('1','2'):raise ValueError('Choose 1, 2 or 0; existing database preserved.')
    if choice=='1' and owned:
        # Keep the existing installer's supported restart/resume path, including
        # a stopped service. No adoption or destructive action takes place here.
        print('Verified existing installation retained.',flush=True)
        return
    info=discover(data)
    if config['project'].split('_')[1] != info['project'].split('_')[1]:
        raise ValueError('Existing database belongs to a different installation mode; use its original mode.')
    if owned and config['project']!=info['project']:
        raise ValueError('Ownership record and running service differ; database preserved.')
    print('Service: '+info['service']+' / PostgreSQL port: '+str(info['port']),flush=True)
    reset=choice=='2'
    if reset:
        token='RESET '+info['service']
        print('DB accounts, annotations and analysis records will start empty. Models, slides, keys and result files are retained.\nDB 계정·주석·분석 기록을 초기화합니다. 모델·슬라이드·키·결과 파일은 유지합니다.\nType exactly: '+token,flush=True)
        if input('DB reset confirmation / DB 초기화 확인 — type '+token+': ').strip()!=token:
            raise ValueError('Reset confirmation did not match; nothing changed.')
    else:
        print('Recovery preserves data and synchronizes DB login passwords with these installer settings.',flush=True)
        if input('Recover existing DB credentials / DB 인증정보 복구? [y/N]: ').strip().lower() not in ('y','yes'):
            raise ValueError('Recovery cancelled; database preserved.')
        if not (Path(config['paths']['secrets'])/'.secrets.json').is_file():
            raise ValueError('Original secrets file is missing. Restore it before recovery; database preserved.')
    if int(config['app_port'])==info['port']:
        raise ValueError('Web port conflicts with existing DB port; choose a different web port first.')
    saved=backup(info,config,runtime)
    # Recheck the cluster after the potentially long dump.
    verified=discover(data)
    if any(verified[k]!=info[k] for k in ('pid','service','port','data')):
        raise ValueError('Database changed during backup; stopped before mutation.')
    if reset:
        # Stop only the verified unit, archive (never delete) the full cluster.
        command(['systemctl','stop',info['service']])
        if output(['systemctl','show',info['service'],'-p','MainPID','--value'])!='0':
            raise ValueError('Database service did not stop; cluster preserved.')
        try:
            data.rename(saved/'database-before-reset')
        except OSError:
            command(['systemctl','start',info['service']])
            raise
        config['db_password']=secrets.token_hex(24)
        config['pg_password']=secrets.token_hex(24)
    else:
        # Only random hex credentials from validated settings enter SQL; never argv/logs.
        for key in ('db_password','pg_password'):
            if not re.fullmatch('[0-9a-f]{48}',config[key]):raise ValueError('Invalid generated credentials.')
        sql(info,"BEGIN; SET password_encryption='scram-sha-256';\n"
            +"ALTER ROLE postgres PASSWORD '"+config['pg_password']+"';\n"
            +"ALTER ROLE mediauto PASSWORD '"+config['db_password']+"';\nCOMMIT;")
    config['project']=info['project'];config['db_port']=info['port']
    write_private(runtime/'settings.json',json.dumps(config,ensure_ascii=False,indent=2))
    write_private(runtime/'identity.json',json.dumps({k:config[k] for k in ('project','paths','db_port')}))
    write_private(marker,json.dumps({'project':config['project'],'database':str(data)}))
    if reset and (runtime/'app.json').exists():
        (runtime/'app.json').unlink()  # already backed up; rebuilt after setup
    print('Database selection applied; continuing installation. Backup: '+str(saved),flush=True)
