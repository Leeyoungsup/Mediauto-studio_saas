"""Run existing installers, exchanging extra questions through anonymous pipes."""
import builtins
import getpass
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
from gui_contract import PREFIX, validate, supplied_answer, redact

def main():
    # The JSON pipe and Python logs must not depend on the Windows locale.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    os.environ['PYTHONIOENCODING']='utf-8'
    root=Path(__file__).resolve().parent
    values=json.loads(sys.stdin.readline())
    mode=values['mode'];folder=root/mode
    existing=(folder/'.install-location.json').is_file()
    validate(values,existing=existing)
    if os.name!='nt' and os.geteuid()!=0:raise RuntimeError('관리자 인증이 필요합니다.')
    if os.name!='nt' and os.environ.get('PKEXEC_UID'):
        import pwd
        account=pwd.getpwuid(int(os.environ['PKEXEC_UID']))
        os.environ.update(SUDO_USER=account.pw_name,SUDO_UID=str(account.pw_uid),SUDO_GID=str(account.pw_gid))
    def event(kind,**data):
        print(PREFIX+json.dumps(dict(kind=kind,**data),ensure_ascii=False),flush=True)
    def ask(prompt='',secret=False):
        answer=supplied_answer(prompt,values)
        if answer is not None:return answer
        event('prompt',text=prompt,secret=secret)
        line=sys.stdin.readline()
        if not line:raise RuntimeError('설치 창 연결이 종료되었습니다.')
        response=json.loads(line)
        if response.get('cancel'):raise RuntimeError('사용자가 추가 입력을 취소했습니다. 기존 데이터는 유지됩니다.')
        return response['answer']
    builtins.input=ask
    getpass.getpass=lambda prompt='Password: ',**kwargs:ask(prompt,True)
    os.environ['PYTHONUTF8']='1'
    os.environ['PYTHONUNBUFFERED']='1'
    event('phase',text='필수 프로그램 확인 및 설치')
    if os.name=='nt':
        command=['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(folder/'bootstrap.ps1'),'-PrepareOnly']
    else:command=['bash',str(folder/'install.sh'),'--prepare-only']
    subprocess.run(command,check=True,stdin=subprocess.DEVNULL)
    if os.name=='nt':
        git=Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Git/cmd'
        docker=Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Docker/Docker/resources/bin'
        os.environ['PATH']=os.pathsep.join([str(git),str(docker),os.environ.get('PATH','')])
    event('phase',text='GPU·DB·Conda 및 애플리케이션 설치')
    sys.path.insert(0,str(folder));sys.argv=[str(folder/'install.py')]
    try:runpy.run_path(str(folder/'install.py'),run_name='__main__')
    except SystemExit as exc:
        if exc.code not in (None,0):raise RuntimeError('설치가 중단되었습니다. 위 로그를 확인하세요.')
    event('done',text='설치 완료. 서버는 자동으로 시작하지 않았습니다.')

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('INSTALL FAILED: '+str(exc),flush=True)
        sys.exit(1)
