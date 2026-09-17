"""Run migrations/bootstrap and the app in its native virtual environment."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time


class ConsoleLog:
    """Keep manual-run Python output on screen and in the external log."""
    def __init__(self, console, log):
        self.console, self.log = console, log
        self.encoding = 'utf-8'

    def write(self, value):
        self.log.write(value)
        if self.console is not None: self.console.write(value)
        return len(value)

    def flush(self):
        self.log.flush()
        if self.console is not None: self.console.flush()

    def isatty(self):
        return False

    def fileno(self):
        return self.log.fileno()


def main():
    settings=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    os.environ.update(settings['env'])
    os.chdir(settings['backend'])
    child_output = {}
    if '--check' not in sys.argv:
        log=Path(settings['log']);log.parent.mkdir(parents=True,exist_ok=True)
        # Log is on the host and never includes installer GitHub credentials.
        f=log.open('a',encoding='utf-8',buffering=1)
        if '--console' in sys.argv:
            sys.stdout = ConsoleLog(sys.stdout, f)
            sys.stderr = ConsoleLog(sys.stderr, f)
        else:
            os.dup2(f.fileno(),1);os.dup2(f.fileno(),2)
        # Windows console streams keep console-specific handles after dup2.
        # Rebind Python streams as well, and pass file handles to child processes.
            sys.stdout = f
            sys.stderr = f
        child_output = {'stdout': f, 'stderr': f}
    print('[START] MeDIAuto runner: '+sys.executable, flush=True)
    from gpu_check import check_gpu
    check_gpu()
    for _ in range(60):
        try:
            with socket.create_connection(('127.0.0.1',settings['db_port']),timeout=2):break
        except OSError:time.sleep(2)
    else:raise RuntimeError('PostgreSQL is not accepting connections.')
    subprocess.run([sys.executable,'-m','alembic','upgrade','head'],check=True,**child_output)
    subprocess.run([sys.executable,str(Path(__file__).resolve().with_name('bootstrap_admin.py')),'--strict-models','--strict-db'],check=True,**child_output)
    if '--check' in sys.argv:return
    # Running in-process lets systemd/Task Scheduler stop the actual server process.
    sys.path.insert(0,settings['backend'])
    print('[START] Loading app and starting HTTP server on '+settings['bind']+':'+str(settings['port']), flush=True)
    import uvicorn
    uvicorn.run('main:app',host=settings['bind'],port=settings['port'])


if __name__=='__main__':main()
