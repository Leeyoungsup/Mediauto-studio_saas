import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('existing_database',Path(__file__).parent/'native/existing_database.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class ExistingDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.runtime=self.root/'config';self.runtime.mkdir()
        self.data=self.root/'database';self.data.mkdir();(self.data/'PG_VERSION').write_text('12')
        keys=self.root/'secrets';keys.mkdir();(keys/'.secrets.json').write_text('original-key')
        self.config={'project':'mediauto_native_new','data_root':str(self.root),'app_port':8095,'db_port':55500,
                     'paths':{'database':str(self.data),'secrets':str(keys)},'db_password':'a'*48,'pg_password':'b'*48}
        self.info={'project':'mediauto_native_old','service':'mediauto-native-old.service','port':55432,'pid':'123','data':self.data}
        self.backup=self.root/'backup';self.backup.mkdir()
        self.discover=patch.object(m,'discover',return_value=self.info).start()
        self.back=patch.object(m,'backup',return_value=self.backup).start()
        self.sql=patch.object(m,'sql').start();self.cmd=patch.object(m,'command').start()
        self.addCleanup(patch.stopall)
    def write(self,path,text):path.write_text(text)
    def test_cancel_and_invalid_confirmation_never_mutate(self):
        for answers in (['0'],['2','yes'],['1','no']):
            with patch('builtins.input',side_effect=answers),self.assertRaises(ValueError):
                m.handle(self.config,self.runtime,self.write)
            self.back.assert_not_called();self.sql.assert_not_called();self.cmd.assert_not_called()
            self.assertTrue((self.data/'PG_VERSION').is_file())
    def test_recovery_backs_up_and_preserves_cluster(self):
        with patch('builtins.input',side_effect=['1','yes']):m.handle(self.config,self.runtime,self.write)
        self.back.assert_called_once();self.sql.assert_called_once();self.cmd.assert_not_called()
        self.assertTrue((self.data/'PG_VERSION').is_file())
        saved=json.loads((self.runtime/'settings.json').read_text())
        self.assertEqual(saved['project'],'mediauto_native_old');self.assertEqual(saved['db_port'],55432)
        self.assertEqual((self.root/'secrets/.secrets.json').read_text(),'original-key')
    def test_backup_failure_prevents_reset(self):
        self.back.side_effect=OSError('disk full')
        with patch('builtins.input',side_effect=['2','RESET mediauto-native-old.service']),self.assertRaises(OSError):
            m.handle(self.config,self.runtime,self.write)
        self.cmd.assert_not_called();self.sql.assert_not_called();self.assertTrue(self.data.exists())
    def test_reset_archives_only_database_after_confirmation(self):
        (self.runtime/'app.json').write_text('{}')
        with patch('builtins.input',side_effect=['2','RESET mediauto-native-old.service']),patch.object(m,'output',return_value='0'):
            m.handle(self.config,self.runtime,self.write)
        self.assertFalse(self.data.exists());self.assertTrue((self.backup/'database-before-reset/PG_VERSION').is_file())
        self.assertTrue((self.root/'secrets/.secrets.json').is_file())
        self.cmd.assert_called_once_with(['systemctl','stop','mediauto-native-old.service'])
        self.sql.assert_not_called();self.assertFalse((self.runtime/'app.json').exists())
    def test_missing_keys_blocks_recovery(self):
        (self.root/'secrets/.secrets.json').unlink()
        with patch('builtins.input',side_effect=['1','yes']),self.assertRaisesRegex(ValueError,'secrets'):
            m.handle(self.config,self.runtime,self.write)
        self.back.assert_not_called();self.sql.assert_not_called()
    def test_verified_install_keeps_credentials_without_backup_or_mutation(self):
        self.config.update(project=self.info['project'],db_port=self.info['port'])
        (self.runtime/'db-initialization.json').write_text(json.dumps({'project':self.config['project'],'database':str(self.data)}))
        with patch('builtins.input',return_value=''):m.handle(self.config,self.runtime,self.write)
        self.back.assert_not_called();self.sql.assert_not_called();self.cmd.assert_not_called()
    def test_changed_cluster_after_backup_blocks_mutation(self):
        self.discover.side_effect=[self.info,dict(self.info,pid='456')]
        with patch('builtins.input',side_effect=['1','yes']),self.assertRaisesRegex(ValueError,'changed'):
            m.handle(self.config,self.runtime,self.write)
        self.sql.assert_not_called();self.cmd.assert_not_called()

class DiscoveryTests(unittest.TestCase):
    def test_service_pid_path_and_database_ownership_are_checked(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);data=root/'database';data.mkdir()
            (data/'PG_VERSION').write_text('12')
            (data/'postmaster.pid').write_text('123\n'+str(data)+'\n0\n55432\n/var/run/postgresql\n')
            unit=root/'mediauto-native-abc123.service'
            unit.write_text('ExecStart="/usr/lib/postgresql/12/bin/postgres" -D "'+str(data)+'"\n')
            for other_count in ('0','1'):
                with self.subTest(other_databases=other_count),patch.object(Path,'glob',return_value=[unit]),patch.object(m,'output',side_effect=['active','123']),patch.object(m,'sql',side_effect=[str(data),'1',other_count]):
                    if other_count=='0':
                        result=m.discover(data);self.assertEqual(result['project'],'mediauto_native_abc123')
                    else:
                        with self.assertRaisesRegex(ValueError,'other databases'):m.discover(data)
            with patch.object(Path,'glob',return_value=[unit]),patch.object(m,'output',side_effect=['active','999']),patch.object(m,'sql') as query:
                with self.assertRaisesRegex(ValueError,'PID'):m.discover(data)
                query.assert_not_called()

    def test_gui_does_not_automatically_answer_destructive_prompts(self):
        import sys
        from unittest.mock import patch
        with patch.object(sys,'path',[str(Path(__file__).parent/'installer')]+sys.path):
            from gui_contract import supplied_answer
            for prompt in ('Existing DB / 기존 DB:', 'DB reset confirmation / DB 초기화 확인:', 'Recover existing DB credentials / DB 인증정보 복구? [y/N]:'):
                self.assertIsNone(supplied_answer(prompt,{'token':'secret','data_root':'/data'}))
