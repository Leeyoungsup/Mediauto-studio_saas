import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

s=importlib.util.spec_from_file_location('host_install',Path(__file__).parent/'host/install.py')
h=importlib.util.module_from_spec(s);s.loader.exec_module(h)

class HostTests(unittest.TestCase):
    def config(self,root):
        return {'data_root':str(root),'project':'mediauto_host_test','app_port':18099,'db_port':55439,'bind':'127.0.0.1',
                'admin_password':'a'*24+'Aa!','db_password':'b'*48,'pg_password':'c'*48,
                'paths':{k:str(root/k) for k in (*h.PATHS,'database')}}

    def test_external_mounts_and_separate_database(self):
        with tempfile.TemporaryDirectory(prefix='mediauto space $ ') as d:
            root=Path(d);c=self.config(root)
            h.validate(c)
            with patch.object(h,'RUNTIME',root/'.runtime'):
                h.compose(c,'external-network')
            doc=json.loads((root/'.runtime/compose.json').read_text())
            self.assertEqual(set(doc['services']),{'app'})
            app=doc['services']['app']
            self.assertEqual(app['restart'],'no')
            self.assertEqual(app['image'],c['project']+':local')
            self.assertEqual(app['build']['context'],str(h.ROOT/'application'))
            self.assertTrue(app['build']['dockerfile'].endswith('Dockerfile.source'))
            mounts=doc['services']['app']['volumes']
            self.assertEqual({m['target'] for m in mounts},set(h.PATHS.values()) | {'/installer/container_runner.py', '/installer/bootstrap_admin.py'})
            self.assertTrue(all(m['type']=='bind' for m in mounts))
            self.assertTrue(next(m for m in mounts if m['target']=='/models')['read_only'])
            self.assertIn('host.docker.internal:55439', (root/'.runtime/app.env').read_text())
            self.assertNotIn(c['db_password'],(root/'.runtime/compose.json').read_text())
            self.assertEqual((root/'.runtime/app.env').stat().st_mode & 0o777,0o600)

    def test_blank_slide_path_uses_root_subfolder(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'data';models=Path(d)/'models'
            paths=h.storage_paths(root,models,'   ')
            self.assertEqual(paths['slides'],str(root/'slides'))
            self.assertEqual(paths['logs'],str(root/'logs'))
            self.assertEqual(paths['database'],str(root/'database'))
            self.assertEqual(paths['models'],str(models))

    def test_custom_slide_path_stays_separate(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'data';slides=Path(d)/'wsi'
            paths=h.storage_paths(root,Path(d)/'models',str(slides))
            self.assertEqual(paths['slides'],str(slides))
            self.assertEqual(paths['results'],str(root/'results'))

    def test_nested_storage_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            c=self.config(Path(d));c['paths']['database']=c['paths']['slides']+'/db'
            with self.assertRaises(ValueError): h.validate(c)

    def test_existing_postgres_cluster_is_not_adopted(self):
        with tempfile.TemporaryDirectory() as d:
            c=self.config(Path(d));db=Path(c['paths']['database']);db.mkdir()
            (db/'PG_VERSION').write_text('18')
            with patch.object(h,'RUNTIME',Path(d)/'.runtime'):
                with self.assertRaisesRegex(ValueError,'Existing PostgreSQL'): h.claim_database(c)
                self.assertFalse((h.RUNTIME/'db-initialization.json').exists())

    def test_own_database_initialization_can_resume(self):
        with tempfile.TemporaryDirectory() as d:
            c=self.config(Path(d));db=Path(c['paths']['database'])
            with patch.object(h,'RUNTIME',Path(d)/'.runtime'):
                h.claim_database(c)
                db.mkdir();(db/'PG_VERSION').write_text('18')
                h.claim_database(c)

    def test_windows_keeps_desktop_host_dns(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c=self.config(root)
            c['paths']={k:'D:/MeDIAuto Data/'+k for k in (*h.PATHS,'database')}
            with patch.object(h,'RUNTIME',root/'.runtime'), patch.object(h,'WINDOWS',True):
                h.compose(c,'desktop-network')
            app=json.loads((root/'.runtime/compose.json').read_text())['services']['app']
            self.assertNotIn('extra_hosts',app)
            self.assertEqual(app['volumes'][0]['source'],'D:/MeDIAuto Data/models')

    def test_unsafe_service_name_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            c=self.config(Path(d));c['project']="bad'; Stop-Service postgres"
            with self.assertRaises(ValueError): h.validate(c)

    def test_existing_identity_prevents_silent_database_switch(self):
        with tempfile.TemporaryDirectory() as d:
            c=self.config(Path(d))
            with patch.object(h,'RUNTIME',Path(d)/'.runtime'):
                identity={k:c[k] for k in ('project','paths','db_port')}
                h.write_private(h.RUNTIME/'identity.json',json.dumps(identity))
                h.check_ports(c)
                c['paths']['database'] += '-other'
                with self.assertRaisesRegex(ValueError,'changed'): h.check_ports(c)

    def test_resume_preserves_password_and_paths_without_prompts(self):
        with tempfile.TemporaryDirectory() as d:
            c=self.config(Path(d))
            with patch.object(h,'RUNTIME',Path(d)/'.runtime'):
                h.write_private(h.RUNTIME/'settings.json',json.dumps(c))
                with patch('builtins.input',side_effect=AssertionError('must not prompt')):
                    self.assertEqual(h.configure(),c)

if __name__=='__main__': unittest.main()
