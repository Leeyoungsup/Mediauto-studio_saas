import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).parent

class WindowsPostgresInitTests(unittest.TestCase):
    def test_new_install_and_binary_only_retry(self):
        for mode in ('native','host'):
            for have_binaries in (False,True):
                spec=importlib.util.spec_from_file_location('init_'+mode,ROOT/mode/'install.py')
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                with tempfile.TemporaryDirectory() as directory:
                    root=Path(directory);runtime=root/'config';runtime.mkdir();data=root/'new-data'
                    old=root/'old-data';old.mkdir();(old/'keep').write_text('old DB')
                    prefix=root/'programs/postgresql';binary=prefix/'bin'
                    names=('psql.exe','pg_ctl.exe','postgres.exe','initdb.exe')
                    def binaries():
                        binary.mkdir(parents=True,exist_ok=True)
                        for name in names:(binary/name).touch()
                    if have_binaries:binaries()
                    installer=runtime/'postgresql-installer.exe';installer.write_bytes(b'fixture')
                    config={'project':'mediauto_native_test','paths':{'database':str(data)},'pg_password':'test-secret'}
                    def run(args,**kwargs):
                        if str(args[0]).endswith('postgresql-installer.exe'):
                            self.assertIn('--extract-only',args);self.assertNotIn('--datadir',args)
                            self.assertEqual(args[args.index('--mode')+1],'unattended');binaries()
                    def init(args,**kwargs):
                        self.assertEqual(Path(args[0]).name,'initdb.exe')
                        self.assertEqual(args[args.index('-D')+1],str(data))
                        self.assertNotIn('test-secret',' '.join(args))
                        self.assertEqual(Path(args[args.index('--pwfile')+1]).read_text(),'test-secret\n')
                        (data/'global').mkdir(parents=True)
                        for name in ('PG_VERSION','postgresql.conf','pg_hba.conf','global/pg_control'):(data/name).write_text('18')
                        return subprocess.CompletedProcess(args,0)
                    with patch.object(module,'ROOT',root),patch.object(module,'RUNTIME',runtime),patch.object(module,'PG_SHA',module.sha(installer)),patch.object(module,'run',side_effect=run) as runner,patch.object(module.subprocess,'run',side_effect=init) as init_runner,patch.object(module,'ensure_windows_postgres_service',return_value='verified-service'):
                        result=module.prepare_windows_postgres(config)
                        self.assertEqual(result,(binary/'psql.exe','verified-service'))
                        self.assertEqual(init_runner.call_count,1)
                        self.assertFalse((runtime/'postgresql-init-password.txt').exists())
                        runner.reset_mock();init_runner.reset_mock()
                        module.prepare_windows_postgres(config)
                        init_runner.assert_not_called()
                        self.assertEqual(runner.call_count,1) # version check, no reinstallation
                        (data/'PG_VERSION').unlink()
                        with self.assertRaisesRegex(ValueError,'nonempty folder'):module.prepare_windows_postgres(config)
                        init_runner.assert_not_called()
                    self.assertEqual((old/'keep').read_text(),'old DB')

    def test_failed_initialization_removes_password_file(self):
        spec=importlib.util.spec_from_file_location('init_failure',ROOT/'native/install.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);runtime=root/'config';runtime.mkdir();binary=root/'programs/postgresql/bin';binary.mkdir(parents=True)
            for name in ('psql.exe','pg_ctl.exe','postgres.exe','initdb.exe'):(binary/name).touch()
            config={'project':'mediauto_native_test','paths':{'database':str(root/'data')},'pg_password':'secret'}
            with patch.object(module,'ROOT',root),patch.object(module,'RUNTIME',runtime),patch.object(module,'run'),patch.object(module.subprocess,'run',return_value=subprocess.CompletedProcess([],1)):
                with self.assertRaisesRegex(RuntimeError,'postgresql-initdb.log'):module.prepare_windows_postgres(config)
            self.assertFalse((runtime/'postgresql-init-password.txt').exists())

if __name__=='__main__':unittest.main()
