"""Regression coverage for the Python-3.8-before-Conda installer failure."""
import ast
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'native'))
import bootstrap_python as bootstrap
import conda_setup


class BootstrapTests(unittest.TestCase):
    def test_bootstrap_sources_parse_on_python38(self):
        for name in ('bootstrap_python.py','conda_setup.py'):
            ast.parse((ROOT/'native'/name).read_text(), feature_version=(3,8))

    def test_new_environment_is_created_without_changing_base(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);prefix=root/'envs/mediauto-installer';python=prefix/'bin/python'
            calls=[]
            def invoke(args, **kw):
                calls.append((args,kw))
                if 'create' in args:
                    python.parent.mkdir(parents=True);python.touch()
            with patch.object(conda_setup,'ensure_conda',return_value=root/'conda'),patch.object(conda_setup,'named_prefix',return_value=prefix),patch.object(conda_setup,'invoke',side_effect=invoke),patch.dict(os.environ,{},clear=True):
                self.assertEqual(bootstrap.prepare(root),python)
                self.assertEqual(os.environ['CONDA_EXE'],str(root/'conda'))
            self.assertEqual(calls[0][0][1:5],['create','--yes','--name','mediauto-installer'])
            self.assertIn('python=3.12',calls[0][0]);self.assertNotIn('base',calls[0][0])
            self.assertEqual(len(calls),2)

    def test_existing_installer_python_is_reused_without_package_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);prefix=root/'env';python=prefix/'bin/python';python.parent.mkdir(parents=True);python.touch()
            with patch.object(conda_setup,'ensure_conda',return_value=root/'conda'),patch.object(conda_setup,'named_prefix',return_value=prefix),patch.object(conda_setup,'invoke') as invoke,patch.dict(os.environ,{},clear=True):
                self.assertEqual(bootstrap.prepare(root),python)
            self.assertEqual(invoke.call_count,1);self.assertIn('run',invoke.call_args.args[0])

    def test_registered_broken_bootstrap_environment_is_repaired(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);prefix=root/'env';python=prefix/'bin/python';python.parent.mkdir(parents=True);python.touch()
            (prefix/'conda-meta').mkdir();(prefix/'conda-meta/history').touch()
            fail=subprocess.CalledProcessError(1,['python','-c','probe'])
            with patch.object(conda_setup,'ensure_conda',return_value=root/'conda'),patch.object(conda_setup,'named_prefix',return_value=prefix),patch.object(conda_setup,'invoke',side_effect=[fail,None,None]) as invoke,patch.dict(os.environ,{},clear=True):
                bootstrap.prepare(root)
            self.assertEqual(invoke.call_args_list[1].args[0][1],'install')
            self.assertIn('mediauto-installer',invoke.call_args_list[1].args[0])

    def test_unmanaged_directory_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);prefix=root/'env';prefix.mkdir();keep=prefix/'keep.txt';keep.write_text('preserve')
            with patch.object(conda_setup,'ensure_conda',return_value=root/'conda'),patch.object(conda_setup,'named_prefix',return_value=prefix),patch.object(conda_setup,'invoke') as invoke,patch.dict(os.environ,{},clear=True):
                with self.assertRaisesRegex(RuntimeError,'preserved'):bootstrap.prepare(root)
            self.assertEqual(keep.read_text(),'preserve');invoke.assert_not_called()

    def test_failed_conda_preparation_never_launches_installer(self):
        with patch.object(bootstrap.os,'geteuid',return_value=0),patch.object(bootstrap,'restore_invoking_user'),patch.object(bootstrap,'prepare',side_effect=RuntimeError('download failed')),patch.object(bootstrap.os,'execve') as execute:
            with self.assertRaisesRegex(RuntimeError,'download failed'):bootstrap.main([str(ROOT/'native/install.py')])
            execute.assert_not_called()

    def test_reexec_preserves_gui_input_but_removes_python_path_injection(self):
        payload='{"token":"test-only-PAT"}\n'
        stream=io.StringIO(payload)
        with patch('sys.stdin',stream),patch.object(bootstrap.os,'geteuid',return_value=0),patch.object(bootstrap,'restore_invoking_user'),patch.object(bootstrap,'prepare',return_value=Path('/verified/bin/python')),patch.object(bootstrap.os,'execve') as execute,patch.dict(os.environ,{'PYTHONPATH':'old-path','PYTHONHOME':'old-home'},clear=True):
            bootstrap.main([str(ROOT/'installer/gui_worker.py')])
        self.assertEqual(stream.tell(),0)
        program,args,env=execute.call_args.args
        self.assertEqual(program,'/verified/bin/python');self.assertIn(str(ROOT/'installer/gui_worker.py'),args)
        self.assertNotIn('test-only-PAT',str(args));self.assertNotIn('PYTHONPATH',env);self.assertNotIn('PYTHONHOME',env)

    def test_pkexec_restores_user_for_conda_ownership(self):
        account=types.SimpleNamespace(pw_name='installer-user',pw_uid=1234,pw_gid=1234)
        with patch.dict(os.environ,{'PKEXEC_UID':'1234'},clear=True),patch.object(bootstrap.os,'geteuid',return_value=0),patch.object(bootstrap.pwd,'getpwuid',return_value=account):
            bootstrap.restore_invoking_user()
            self.assertEqual(os.environ['SUDO_USER'],'installer-user')

    def test_native_and_docker_cli_enter_bootstrap(self):
        # Mock system prerequisite commands and run the actual shell dispatch.
        for mode in ('native','host'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);binpath=root/'bin';binpath.mkdir()
                for name in ('apt-get','systemctl','nvidia-smi','docker'):
                    f=binpath/name;f.write_text('#!/bin/sh\necho nvidia\n');f.chmod(0o755)
                for name in ('setup-nvidia-driver.sh','setup-nvidia-runtime.sh'):(root/name).write_text('exit 0\n')
                capture=root/'capture.py';capture.write_text('import sys; print("BOOTSTRAP_DISPATCH",sys.argv[1:])')
                shell=(ROOT/mode/'install.sh').read_text()
                begin=shell.index('if [[ $EUID -ne 0 ]]');end=shell.index('\nfi',begin)+3
                shell=shell[:begin]+shell[end:]
                shell=shell.replace('[[ -d /run/systemd/system ]]','true')
                shell=shell.replace('"$PWD/bootstrap_python.py"','"'+str(capture)+'"')
                script=root/'install.sh';script.write_text(shell)
                result=subprocess.run(['bash',str(script)],env=dict(os.environ,PATH=str(binpath)+':'+os.environ['PATH']),capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr);self.assertIn('BOOTSTRAP_DISPATCH',result.stdout)
                self.assertIn(str(root/'install.py'),result.stdout)


class Python38ExecutionTest(unittest.TestCase):
    def test_real_python38_reexec_keeps_stdin_and_arguments(self):
        legacy=os.environ.get('MEDIAUTO_TEST_PYTHON38')
        if not legacy:self.skipTest('Set MEDIAUTO_TEST_PYTHON38 for actual Python 3.8 regression')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            shutil.copy2(ROOT/'native/bootstrap_python.py',root/'bootstrap_python.py')
            # No dependency download, sudo, or machine environment is modified.
            stub='''from pathlib import Path
import os,subprocess,sys
assert sys.version_info[:2] == (3,8), sys.version

def ensure_conda(root,cache,windows): return Path('/fixture/conda')
def named_prefix(conda,name): return Path(%r)
def invoke(args,**kw): return None
''' % str(Path(sys.executable).parent.parent)
            (root/'conda_setup.py').write_text(stub)
            target=root/'target.py';target.write_text('import sys; assert sys.version_info >= (3,10); print("PAYLOAD:",sys.stdin.read()); print("ARGS:",sys.argv[1:])')
            harness=root/'harness.py';harness.write_text('import bootstrap_python as b\nb.os.geteuid=lambda:0\nb.main()\n')
            result=subprocess.run([legacy,str(harness),str(target),'--gui-pipe-test'],input='test-private-input\n',capture_output=True,text=True,env=dict(os.environ,PYTHONPATH='',PYTHONHOME=''))
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PAYLOAD: test-private-input',result.stdout)
            self.assertIn('--gui-pipe-test',result.stdout)


if __name__=='__main__':unittest.main()
