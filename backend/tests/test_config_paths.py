"""Load isolated config copies: never create or read workstation secrets."""
import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch


class ConfigPathsTests(unittest.TestCase):
    def load(self, root, env):
        app = root / 'backend/app'
        app.mkdir(parents=True)
        file = app / 'config.py'
        shutil.copyfile(Path(__file__).parents[1] / 'app/config.py', file)
        spec = importlib.util.spec_from_file_location('isolated_config', file)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, env, clear=True):
            spec.loader.exec_module(module)
        return module.settings

    def test_existing_project_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = self.load(root, {})
            self.assertEqual(settings.CELL_ANNOTATION_DIR, str(root/'backend/cell_annotation'))
            self.assertTrue((root/'backend/.secrets.json').is_file())
            self.assertEqual(settings.UPLOAD_DIR, str(root/'backend/uploads'))

    def test_external_paths_and_secrets_survive_reload(self):
        with tempfile.TemporaryDirectory(prefix='mediauto paths ') as directory:
            root = Path(directory)
            secret = root/'external/secrets.json'
            env = {'MEDIAUTO_SECRETS_FILE':str(secret), 'CELL_ANNOTATION_DIR':str(root/'patches'),
                   'UPLOAD_DIR':'relative/slides', 'OPENSLIDE_PATH':str(root/'dll')}
            settings = self.load(root/'checkout1', env)
            content = secret.read_bytes()
            self.load(root/'checkout2', env)
            self.assertEqual(secret.read_bytes(), content)
            self.assertFalse((root/'checkout1/backend/.secrets.json').exists())
            self.assertEqual(settings.CELL_ANNOTATION_DIR, str(root/'patches'))
            self.assertEqual(settings.UPLOAD_DIR, str(root/'checkout1/backend/relative/slides'))
            self.assertEqual(settings.OPENSLIDE_PATH, str(root/'dll'))

    def test_blank_override_uses_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = self.load(root, {'CELL_ANNOTATION_DIR':' ', 'MODEL_DIR':''})
            self.assertEqual(settings.CELL_ANNOTATION_DIR,str(root/'backend/cell_annotation'))
            self.assertEqual(settings.MODEL_DIR,str(root/'backend/model'))
