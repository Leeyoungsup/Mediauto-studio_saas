import importlib.util
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch, AsyncMock

ROOT = Path(__file__).resolve().parent

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class InitialAdminTests(unittest.TestCase):
    def test_new_install_and_resume(self):
        for mode in ('host', 'native'):
            module = load('installer_' + mode, ROOT / mode / 'install.py')
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                answers = [str(root/'data'), str(root/'models'), '', '', '', '']
                if mode == 'native': answers += ['', '']
                with patch.object(module, 'ROOT', root), patch.object(module, 'RUNTIME', root/'runtime'), patch.object(module, 'WINDOWS', False):
                    with patch('builtins.input', side_effect=answers):
                        config = module.configure()
                    self.assertEqual(config['admin_password'], 'admin')
                    self.assertEqual(config.get('admin_id', 'admin'), 'admin')
                    self.assertNotEqual(config['db_password'], 'admin')
                    config['admin_password'] = 'ExistingPassword1!'
                    module.write_private(module.RUNTIME/'settings.json', __import__('json').dumps(config))
                    with patch('builtins.input', side_effect=AssertionError('must reuse settings')):
                        self.assertEqual(module.configure()['admin_password'], 'ExistingPassword1!')

    def test_exception_is_limited_to_admin_bootstrap(self):
        backend = load('bootstrap_runtime_test', ROOT.parent/'backend/scripts/bootstrap_runtime.py')
        for mode in ('host', 'native'):
            adapter = load('adapter_' + mode, ROOT/mode/'bootstrap_admin.py')
            original = backend.STR_PASSWORD_PATTERN
            for login, password, accepted in [('admin','admin',True), ('other','admin',False), ('admin','short',False), ('other','ValidPassword1!',True)]:
                with patch.object(backend, 'STR_PASSWORD_PATTERN', adapter.InitialAdminPolicy(original, login)), patch.dict('os.environ', {'MEDIAUTO_BOOTSTRAP_ADMIN_ID':login, 'MEDIAUTO_BOOTSTRAP_ADMIN_PASSWORD':password}), patch.object(backend, '_check_postgres_and_admin', new_callable=AsyncMock, return_value=(True,'')) as database:
                    self.assertEqual(backend._check_database_and_admin(None,False)[0], accepted)
                    self.assertEqual(database.await_count, int(accepted))
            self.assertFalse(original.match('admin'))

if __name__ == '__main__': unittest.main()
