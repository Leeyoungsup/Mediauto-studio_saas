"""Prepare local development alongside Docker using the SAME checkout and data."""
import importlib.util
from pathlib import Path
import sys


def prepare(config, source, root, runtime):
    spec=importlib.util.spec_from_file_location('mediauto_local_environment',Path(root)/'local_environment.py')
    native=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    native.ROOT=Path(root)
    native.RUNTIME=Path(runtime)
    local_config=dict(config,admin_id=config.get('admin_id','admin'))
    python=native.prepare_application(local_config,Path(source))
    # Environment/bootstrap checks only; this never starts the HTTP server.
    native.run([python,Path(root)/'runner.py',Path(runtime)/'app.json','--check'])
    native.prepare_manual_launch(local_config,Path(source))
    workspace=Path(root)/'MeDIAuto-local.code-workspace'
    # Keep developer edits on repeated installations.
    if not workspace.exists():
        import json
        workspace.write_text(json.dumps({
            'folders':[{'path':str(Path(source).resolve())}],
            'settings':{'python.defaultInterpreterPath':str(python)},
            'launch':{'version':'0.2.0','configurations':[{
                'name':'MeDIAuto local server','type':'debugpy','request':'launch',
                'program':str(Path(root)/'runner.py'),
                'args':[str(Path(runtime)/'app.json'),'--console'],
                'python':str(python),'console':'integratedTerminal','justMyCode':False
            }]}
        },ensure_ascii=False,indent=2),encoding='utf-8')
    else:
        # Migrate only the old installer-generated interpreter, not custom settings.
        import json
        try:
            data=json.loads(workspace.read_text(encoding='utf-8'))
            old=str(Path(root)/'venv'/('Scripts/python.exe' if native.WINDOWS else 'bin/python'))
            previous=str(data.get('settings',{}).get('python.defaultInterpreterPath',''))
            old_gpu=str(Path(root)/'envs/mediauto-gpu'/('python.exe' if native.WINDOWS else 'bin/python'))
            if previous in (old,old_gpu):
                data['settings']['python.defaultInterpreterPath']=str(python)
                for item in data.get('launch',{}).get('configurations',[]):
                    if item.get('python')==previous:item['python']=str(python)
                workspace.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        except (ValueError,AttributeError):
            pass
    import os
    if os.name != 'nt' and os.environ.get('SUDO_USER'):
        import pwd
        user=pwd.getpwnam(os.environ['SUDO_USER'])
        os.chown(workspace,user.pw_uid,user.pw_gid)
    print('Local development ready: '+str(workspace),flush=True)
    return python
