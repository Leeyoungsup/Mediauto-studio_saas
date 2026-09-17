import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import bootstrap_philips


class BootstrapPhilipsTests(unittest.TestCase):
    def test_sdk_root_is_selected_for_current_platform(self):
        with tempfile.TemporaryDirectory() as str_temp:
            path_root = Path(str_temp)
            str_expected = (
                bootstrap_philips.STR_WINDOWS_SDK_DIR
                if bootstrap_philips.os.name == "nt"
                else bootstrap_philips.STR_LINUX_SDK_DIR
            )
            path_expected = path_root / "bundle" / str_expected
            path_expected.mkdir(parents=True)

            self.assertEqual(bootstrap_philips._find_sdk_root(path_root), path_expected)

    def test_archive_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as str_temp:
            path_root = Path(str_temp)
            path_archive = path_root / "sdk.zip"
            path_output = path_root / "output"
            path_output.mkdir()
            with zipfile.ZipFile(path_archive, "w") as obj_archive:
                obj_archive.writestr("../escape.txt", b"blocked")

            with self.assertRaises(ValueError):
                bootstrap_philips._safe_extract_archive(path_archive, path_output)
            self.assertFalse((path_root / "escape.txt").exists())

    def test_soname_links_do_not_replace_dependency_with_symlink_cycle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = root / 'libtinyxml.so'
            library.write_bytes(b'library')
            alias = root / 'libtinyxml.so.2.6.2'
            alias.symlink_to(library.name)
            bootstrap_philips._ensure_linux_soname_links(root)
            self.assertFalse(library.is_symlink())
            self.assertEqual(alias.read_bytes(), b'library')

    def test_eula_flag_requires_explicit_true_value(self):
        with patch.dict(bootstrap_philips.os.environ, {}, clear=True):
            self.assertFalse(bootstrap_philips._env_enabled("MEDIAUTO_ACCEPT_PHILIPS_EULA"))
        with patch.dict(
            bootstrap_philips.os.environ,
            {"MEDIAUTO_ACCEPT_PHILIPS_EULA": "1"},
            clear=True,
        ):
            self.assertTrue(bootstrap_philips._env_enabled("MEDIAUTO_ACCEPT_PHILIPS_EULA"))


if __name__ == "__main__":
    unittest.main()
