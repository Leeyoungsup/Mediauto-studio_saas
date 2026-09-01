import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.configure_postgres_env import _parse_env, configure


class ConfigurePostgresEnvTests(unittest.TestCase):
    def test_docker_configuration_generates_persistent_secret(self):
        with tempfile.TemporaryDirectory() as str_temp, patch.dict(os.environ, {}, clear=True):
            path_env = Path(str_temp) / ".env.postgres"
            dict_first, bool_created = configure(path_env, "docker")
            dict_second, bool_created_again = configure(path_env, "docker")

            self.assertTrue(bool_created)
            self.assertFalse(bool_created_again)
            self.assertEqual(dict_first, dict_second)
            self.assertEqual(dict_first["DATABASE_BACKEND"], "postgresql")
            self.assertEqual(dict_first["POSTGRES_DEPLOYMENT"], "docker")
            self.assertNotIn("replace-with", dict_first["POSTGRES_PASSWORD"])
            if os.name != "nt":
                self.assertEqual(path_env.stat().st_mode & 0o777, 0o600)

    def test_external_configuration_requires_and_preserves_uri(self):
        str_uri = "postgresql+asyncpg://user:p%40ss@example.test:5432/app"
        with tempfile.TemporaryDirectory() as str_temp, patch.dict(
            os.environ, {"POSTGRES_URI": str_uri}, clear=True,
        ):
            path_env = Path(str_temp) / ".env.postgres"
            dict_values, _ = configure(path_env, "external")

            self.assertEqual(dict_values["POSTGRES_URI"], str_uri)
            self.assertEqual(_parse_env(path_env)["POSTGRES_DEPLOYMENT"], "external")


if __name__ == "__main__":
    unittest.main()
