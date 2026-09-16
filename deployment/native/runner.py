"""Run migrations/bootstrap and the app in its native virtual environment."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time


def main():
    settings=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    os.environ.update(settings['env'])
    os.chdir(settings['backend'])
    if '--check' not in sys.argv:
        log=Path(settings['log']);log.parent.mkdir(parents=True,exist_ok=True)
        # Log is on the host and never includes installer GitHub credentials.
        f=log.open('a',encoding='utf-8',buffering=1)
        os.dup2(f.fileno(),1);os.dup2(f.fileno(),2)
    from gpu_check import check_gpu
    check_gpu()
    for _ in range(60):
        try:
            with socket.create_connection(('127.0.0.1',settings['db_port']),timeout=2):break
        except OSError:time.sleep(2)
    else:raise RuntimeError('PostgreSQL is not accepting connections.')
    subprocess.run([sys.executable,'-m','alembic','upgrade','head'],check=True)
    subprocess.run([sys.executable,str(Path(__file__).resolve().with_name('bootstrap_admin.py')),'--strict-models','--strict-db'],check=True)
    if '--check' in sys.argv:return
    # Running in-process lets systemd/Task Scheduler stop the actual server process.
    sys.path.insert(0,settings['backend'])
    import uvicorn
    uvicorn.run('main:app',host=settings['bind'],port=settings['port'])


if __name__=='__main__':main()
