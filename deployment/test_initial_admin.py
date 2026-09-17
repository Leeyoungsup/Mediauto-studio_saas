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
                    self.assertEqual(config['admin_password'], 'admin1234!')
                    self.assertEqual(config.get('admin_id', 'admin'), 'admin')
                    self.assertNotEqual(config['db_password'], 'admin')
                    config['admin_password'] = 'ExistingPassword1!'
                    module.write_private(module.RUNTIME/'settings.json', __import__('json').dumps(config))
                    with patch('builtins.input', side_effect=AssertionError('must reuse settings')):
                        self.assertEqual(module.configure()['admin_password'], 'ExistingPassword1!')

    def test_normal_password_policy_and_adapter(self):
        backend = load('bootstrap_runtime_test', ROOT.parent/'backend/scripts/bootstrap_runtime.py')
        self.assertTrue(backend.STR_PASSWORD_PATTERN.match('admin1234!'))
        self.assertFalse(backend.STR_PASSWORD_PATTERN.match('admin'))
        for mode in ('host', 'native'):
            adapter = load('adapter_' + mode, ROOT/mode/'bootstrap_admin.py')
            import types
            original = backend.STR_PASSWORD_PATTERN
            with patch.dict('sys.modules', {'scripts': types.SimpleNamespace(bootstrap_runtime=backend)}), patch.object(backend, 'main', return_value=0) as main:
                self.assertEqual(adapter.main(), 0)
                main.assert_called_once_with()
                self.assertIs(backend.STR_PASSWORD_PATTERN, original)

if __name__ == '__main__': unittest.main()
