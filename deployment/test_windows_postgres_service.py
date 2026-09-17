import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent

class WindowsPostgresServiceTests(unittest.TestCase):
    def test_foreign_port_listener_is_not_restarted(self):
        for mode in ('host','native'):
            spec=importlib.util.spec_from_file_location('listener_'+mode,ROOT/mode/'install.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            config={'db_port':55432,'paths':{'database':'C:/new/data'}}
            own={'ProcessId':448,'ExecutablePath':'C:/new/programs/postgresql/bin/postgres.exe',
                 'CommandLine':'postgres.exe -D "C:/new/data"'}
            with patch.object(module,'ROOT',Path('C:/new')),patch.object(module,'output',return_value=json.dumps([own])):
                module.check_windows_db_listener(config)
            foreign=dict(own,CommandLine='postgres.exe -D "C:/old/data"')
            with patch.object(module,'ROOT',Path('C:/new')),patch.object(module,'output',return_value=json.dumps([foreign])),patch.object(module,'run') as run:
                with self.assertRaisesRegex(RuntimeError,'occupied.*448'):
                    module.restart_windows_postgres(config,'test-service')
                run.assert_not_called()

    def test_recovery_and_conflicts(self):
        for mode in ('host','native'):
            spec=importlib.util.spec_from_file_location('pg_'+mode,ROOT/mode/'install.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);data=root/'data';prefix=root/'postgres';runtime=root/'config'
                data.mkdir();(prefix/'bin').mkdir(parents=True);runtime.mkdir()
                for name in ('PG_VERSION','postgresql.conf','pg_hba.conf'):(data/name).write_text('18')
                (prefix/'bin/pg_ctl.exe').touch()
                config={'project':'mediauto_native_test','paths':{'database':str(data)}}
                marker=runtime/'db-initialization.json'
                marker.write_text(json.dumps({'project':config['project'],'database':str(data)}))
                service={'Name':'mediauto-native-test','PathName':f'"{prefix}/bin/pg_ctl.exe" runservice -N "mediauto-native-test" -D "{data}" -w'}
                with patch.object(module,'RUNTIME',runtime), patch.object(module,'run') as run, patch.object(module.subprocess,'run',return_value=subprocess.CompletedProcess([],3)) as status:
                    with patch.object(module,'output',side_effect=['[]',json.dumps([service])]):
                        module.ensure_windows_postgres_service(config,prefix)
                    self.assertEqual(sum('register' in call.args[0] for call in run.call_args_list),1)
                    run.reset_mock();status.reset_mock()
                    with patch.object(module,'output',return_value=json.dumps([service])):
                        module.ensure_windows_postgres_service(config,prefix)
                    run.assert_not_called();status.assert_not_called()
                    default_service = dict(service,Name='postgresql-x64-18')
                    with patch.object(module,'output',return_value=json.dumps([default_service])):
                        self.assertEqual(module.ensure_windows_postgres_service(config,prefix), 'postgresql-x64-18')
                    run.assert_not_called();status.assert_not_called()
                    with patch.object(module,'output',return_value=json.dumps([service,default_service])):
                        with self.assertRaisesRegex(ValueError,'Multiple services'):
                            module.ensure_windows_postgres_service(config,prefix)
                    run.assert_not_called()
                    for foreign in [dict(default_service,PathName=service['PathName'].replace(str(prefix),str(root/'foreign'))),dict(service,PathName=service['PathName'].replace(str(data),str(root/'other')))]:
                        with patch.object(module,'output',return_value=json.dumps([foreign])):
                            with self.assertRaises(ValueError):module.ensure_windows_postgres_service(config,prefix)
                        run.assert_not_called()
                    with patch.object(module,'output',return_value='[]'):
                        status.return_value=subprocess.CompletedProcess([],0)
                        with self.assertRaises(RuntimeError):module.ensure_windows_postgres_service(config,prefix)
                    run.assert_not_called()
                    marker.unlink()
                    with self.assertRaises(ValueError):module.ensure_windows_postgres_service(config,prefix)
                    run.assert_not_called()

if __name__=='__main__':unittest.main()
