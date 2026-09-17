import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock,patch

spec=importlib.util.spec_from_file_location('local_setup',Path(__file__).parent/'host/local_setup.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class DockerLocalTests(unittest.TestCase):
 def test_shared_checkout_data_and_manual_preflight_with_editable_workspace(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'application';runtime=root/'config'
   config={'project':'mediauto_host_test','paths':{'models':'existing-models'},'db_port':55433,'admin_password':'admin1234!'}
   python=root/'venv/bin/python'
   native=types.SimpleNamespace(prepare_application=Mock(return_value=python),run=Mock(),prepare_manual_launch=Mock())
   fake_spec=types.SimpleNamespace(loader=types.SimpleNamespace(exec_module=Mock()))
   with patch.object(m.importlib.util,'spec_from_file_location',return_value=fake_spec),patch.object(m.importlib.util,'module_from_spec',return_value=native),patch.dict('os.environ',{'SUDO_USER':''}):
    m.prepare(config,source,root,runtime)
    local=native.prepare_application.call_args.args[0]
    self.assertEqual(local['paths'],config['paths']);self.assertEqual(local['db_port'],55433)
    self.assertEqual(native.prepare_application.call_args.args[1],source)
    self.assertEqual(native.ROOT,root);self.assertEqual(native.RUNTIME,runtime)
    self.assertEqual(native.run.call_args.args[0][-1],'--check')
    workspace=root/'MeDIAuto-local.code-workspace'
    data=json.loads(workspace.read_text());self.assertEqual(data['settings']['python.defaultInterpreterPath'],str(python))
    self.assertNotIn('admin1234!',workspace.read_text())
    workspace.write_text('custom developer settings')
    m.prepare(config,source,root,runtime)
    self.assertEqual(workspace.read_text(),'custom developer settings')

if __name__=='__main__':unittest.main()
