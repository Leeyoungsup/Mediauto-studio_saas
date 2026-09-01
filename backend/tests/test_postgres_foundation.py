import unittest

from app.postgres.base import Base
from app.postgres.database import normalize_postgres_uri
from app.postgres import models  # noqa: F401


class PostgresFoundationTests(unittest.TestCase):
    def test_common_postgres_urls_are_normalized_for_asyncpg(self):
        self.assertEqual(
            normalize_postgres_uri("postgres://user:pass@db/app"),
            "postgresql+asyncpg://user:pass@db/app",
        )
        self.assertEqual(
            normalize_postgres_uri("postgresql://user:pass@db/app"),
            "postgresql+asyncpg://user:pass@db/app",
        )

    def test_initial_auth_tables_are_registered(self):
        self.assertEqual(set(Base.metadata.tables), {"users", "sessions"})
        self.assertIn("str_login_id", Base.metadata.tables["users"].columns)
        self.assertIn("str_refresh_token", Base.metadata.tables["sessions"].columns)


if __name__ == "__main__":
    unittest.main()
