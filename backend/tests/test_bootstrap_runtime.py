import tempfile
import unittest
import zipfile
from unittest.mock import patch
from pathlib import Path

from scripts import bootstrap_runtime


class BootstrapRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.list_models = [
            {"filename": "one.pt", "feature": "test one", "required": True},
            {"filename": "two.pth", "feature": "test two", "required": True},
        ]

    def test_model_directory_installs_only_manifest_files(self):
        with tempfile.TemporaryDirectory() as str_temp:
            path_root = Path(str_temp)
            path_source = path_root / "source"
            path_target = path_root / "target"
            path_source.mkdir()
            path_target.mkdir()
            (path_source / "one.pt").write_bytes(b"one")
            (path_source / "ignored.pt").write_bytes(b"ignored")

            int_copied = bootstrap_runtime._copy_model_directory(
                path_source,
                path_target,
                self.list_models,
                False,
            )

            self.assertEqual(int_copied, 1)
            self.assertEqual((path_target / "one.pt").read_bytes(), b"one")
            self.assertFalse((path_target / "ignored.pt").exists())

    def test_nested_zip_model_is_installed_safely(self):
        with tempfile.TemporaryDirectory() as str_temp:
            path_root = Path(str_temp)
            path_target = path_root / "target"
            path_archive = path_root / "models.zip"
            path_target.mkdir()
            with zipfile.ZipFile(path_archive, "w") as obj_archive:
                obj_archive.writestr("bundle/backend/model/two.pth", b"two")
                obj_archive.writestr("../not-a-model.txt", b"ignored")

            int_copied = bootstrap_runtime._copy_model_archive(
                path_archive,
                path_target,
                self.list_models,
                False,
            )

            self.assertEqual(int_copied, 1)
            self.assertEqual((path_target / "two.pth").read_bytes(), b"two")
            self.assertFalse((path_root / "not-a-model.txt").exists())

    def test_default_bootstrap_administrator(self):
        with patch.dict("os.environ", {}, clear=True):
            bool_explicit, str_login_id, str_password, str_name, str_department = (
                bootstrap_runtime._admin_bootstrap_values()
            )

        self.assertFalse(bool_explicit)
        self.assertEqual(str_login_id, "admin")
        self.assertEqual(str_password, "urban12!@")
        self.assertEqual(str_name, "Administrator")
        self.assertEqual(str_department, "")


if __name__ == "__main__":
    unittest.main()
