import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

builder = load('builder', ROOT/'build_local_bundles.py')
config = load('config', ROOT/'local/configure.py')

class BundleTests(unittest.TestCase):
    def test_private_runtime_files_are_never_selected(self):
        for name in ['backend/.secrets.json', '.env.postgres', 'backend/uploads/slide.svs',
                     'backend/annotations/_projects/SS/classes.json', 'backend/ai_results/result.json',
                     'backend/cell_annotation/labels.json', 'backend/dicom/Leica-4.zip',
                     'postgres_data/PG_VERSION', 'reports/report.md', 'deployment/local/.env',
                     'deployment/local/ADMIN_LOGIN.txt', 'backend/model/HnE_detection.pt']:
            self.assertFalse(builder.allowed(name), name)
        for name in ['backend/main.py', 'backend/app/auth.py', 'backend/ai/nets/nn.py',
                     'frontend/js/multi-view-focus.js', 'deployment/local/compose.yml']:
            self.assertTrue(builder.allowed(name), name)

    def test_model_and_code_corruption_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'model.pt').write_bytes(b'weights')
            (root/'bundle-manifest.json').write_text(json.dumps({'files':[
                {'path':'model.pt','sha256':builder.digest(root/'model.pt')}]}))
            config.verify(root)
            (root/'model.pt').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                config.verify(root)

    def test_new_credentials_are_distinct_and_reinstall_preserves_them(self):
        with tempfile.TemporaryDirectory() as d:
            one=Path(d)/'one';two=Path(d)/'two'
            one.mkdir();two.mkdir()
            config.configure(one,'cpu');config.configure(two,'cpu')
            original=(one/'.deploy.env').read_text()
            values=dict(line.split('=',1) for line in original.splitlines())
            # App adds a 43-byte pepper before bcrypt, whose input limit is 72 bytes.
            self.assertLessEqual(len(values['ADMIN_PASSWORD'].encode()) + 43, 72)
            self.assertNotEqual(original,(two/'.deploy.env').read_text())
            self.assertIn('MEDIAUTO_BIND=127.0.0.1', original)
            config.configure(one,'cpu')
            self.assertEqual(original,(one/'.deploy.env').read_text())
            with self.assertRaises(ValueError): config.configure(one,'gpu')

if __name__ == '__main__': unittest.main()
