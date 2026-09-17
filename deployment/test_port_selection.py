import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

class PortSelectionTests(unittest.TestCase):
    def test_replacement_validates_and_persists_without_changing_credentials(self):
        for mode in ('host','native'):
            spec=importlib.util.spec_from_file_location('ports_'+mode,Path(__file__).parent/mode/'install.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                config={'project':'test','paths':{'database':str(root/'data')},'app_port':18093,'db_port':55432,'pg_password':'preserved'}
                with patch.object(module,'RUNTIME',root),patch.object(module,'port_available',side_effect=lambda n:n not in (55432,55434)),patch('builtins.input',side_effect=['bad','18093','55434','']):
                    module.choose_replacement_port(config,'db_port')
                self.assertEqual(config['db_port'],55433)
                self.assertEqual(json.loads((root/'settings.json').read_text()),config)
                self.assertEqual(json.loads((root/'identity.json').read_text())['db_port'],55433)
                with patch.object(module,'RUNTIME',root),patch.object(module,'port_available',side_effect=AssertionError('existing identity must be accepted')):
                    module.check_ports(config)

if __name__=='__main__':unittest.main()
