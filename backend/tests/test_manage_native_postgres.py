import tempfile
import unittest
from pathlib import Path

from scripts.manage_native_postgres import (
    _validate_identifier,
    _write_managed_config,
    _write_user_service,
)


class ManageNativePostgresTests(unittest.TestCase):
    def test_identifier_validation_rejects_sql_fragments(self):
        _validate_identifier("medicus_studio", "database")
        with self.assertRaises(ValueError):
            _validate_identifier("db'; DROP DATABASE postgres;--", "database")

    def test_managed_config_is_idempotent_and_local_only(self):
        with tempfile.TemporaryDirectory() as str_temp:
            path_data = Path(str_temp)
            (path_data / "postgresql.conf").write_text("# base\n", encoding="utf-8")
            _write_managed_config(path_data, 55432)
            _write_managed_config(path_data, 55433)

            str_main = (path_data / "postgresql.conf").read_text(encoding="utf-8")
            str_managed = (path_data / "mediauto.conf").read_text(encoding="utf-8")
            self.assertEqual(str_main.count("include_if_exists = 'mediauto.conf'"), 1)
            self.assertIn("listen_addresses = '127.0.0.1'", str_managed)
            self.assertIn("port = 55433", str_managed)

    def test_user_service_contains_no_database_password(self):
        with tempfile.TemporaryDirectory() as str_temp:
            path_unit = Path(str_temp) / "mediauto-postgresql.service"
            _write_user_service(
                path_unit,
                Path("/opt/postgres/bin/postgres"),
                Path("/opt/postgres/bin/pg_ctl"),
                Path("/srv/postgres/data"),
            )
            str_unit = path_unit.read_text(encoding="utf-8")
            self.assertIn("ExecStart=/opt/postgres/bin/postgres", str_unit)
            self.assertNotIn("PASSWORD", str_unit.upper())


if __name__ == "__main__":
    unittest.main()
