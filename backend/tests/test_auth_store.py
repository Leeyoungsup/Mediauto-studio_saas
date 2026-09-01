import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects import postgresql

from app.postgres.models import Session, User
from app.repositories import auth_store


class AuthStoreTests(unittest.TestCase):
    def test_postgres_repositories_are_the_only_backend(self):
        self.assertIsInstance(auth_store.get_user_store(), auth_store.PostgresUserStore)
        self.assertIsInstance(auth_store.get_session_store(), auth_store.PostgresSessionStore)

    def test_public_user_mapping_excludes_authentication_secrets(self):
        obj_user = User(
            str_id="64f000000000000000000001",
            str_login_id="doctor01",
            str_hashed_password="hashed",
            str_name="Doctor",
            str_totp_secret_enc="encrypted",
            int_failed_login_attempts=3,
        )
        dict_user = auth_store._user_model_to_dict(obj_user, False)

        self.assertNotIn("str_hashed_password", dict_user)
        self.assertNotIn("str_totp_secret_enc", dict_user)
        self.assertNotIn("int_failed_login_attempts", dict_user)
        self.assertEqual(dict_user["_id"], obj_user.str_id)

    def test_refresh_rotation_statement_uses_atomic_predicate(self):
        obj_statement = (
            auth_store.update(Session)
            .where(
                Session.str_refresh_token == "old",
                Session.bool_is_revoked.is_(False),
            )
            .values(bool_is_revoked=True, str_replaced_by="new")
            .returning(Session)
        )
        str_sql = str(obj_statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        ))

        self.assertIn("bool_is_revoked IS false", str_sql)
        self.assertIn("RETURNING", str_sql)
        self.assertIn("str_refresh_token = 'old'", str_sql)

    def test_new_ids_remain_24_character_compatible_strings(self):
        str_id = auth_store._new_id()
        self.assertEqual(len(str_id), 24)
        int(str_id, 16)

    def test_session_model_accepts_timezone_aware_expiry(self):
        dt_now = datetime.now(timezone.utc)
        obj_session = Session(
            str_id="64f000000000000000000002",
            str_user_id="64f000000000000000000001",
            str_refresh_token="token",
            dt_expires_at=dt_now + timedelta(days=1),
        )
        self.assertIsNotNone(obj_session.dt_expires_at.tzinfo)


if __name__ == "__main__":
    unittest.main()
