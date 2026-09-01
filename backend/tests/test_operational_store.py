import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from bson import ObjectId
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.config import settings
from app.postgres.models import AuditLog
from app.repositories import operational_store
from scripts.migrate_operational_to_postgres import _with_string_id


class OperationalStoreTests(unittest.TestCase):
    def test_backend_switch_selects_all_operational_repositories(self):
        with patch.object(settings, "DATABASE_BACKEND", "mongodb"):
            self.assertIsInstance(operational_store.get_audit_store(), operational_store.MongoAuditStore)
            self.assertIsInstance(operational_store.get_ip_geo_store(), operational_store.MongoIpGeoStore)
            self.assertIsInstance(operational_store.get_clinical_info_store(), operational_store.MongoClinicalInfoStore)
        with patch.object(settings, "DATABASE_BACKEND", "postgresql"):
            self.assertIsInstance(operational_store.get_audit_store(), operational_store.PostgresAuditStore)
            self.assertIsInstance(operational_store.get_ip_geo_store(), operational_store.PostgresIpGeoStore)
            self.assertIsInstance(operational_store.get_clinical_info_store(), operational_store.PostgresClinicalInfoStore)

    def test_audit_extra_fields_round_trip_as_top_level_values(self):
        obj_log = AuditLog(
            str_id="64f000000000000000000001",
            str_action="slide.view",
            dt_created_at=datetime.now(timezone.utc),
            dict_extra={"str_slide_name": "sample.svs", "int_patch": 3},
        )
        dict_log = operational_store._audit_model_to_dict(obj_log)
        self.assertEqual(dict_log["str_slide_name"], "sample.svs")
        self.assertEqual(dict_log["int_patch"], 3)
        self.assertNotIn("dict_extra", dict_log)

    def test_audit_filter_escapes_like_wildcards(self):
        obj_query = operational_store.PostgresAuditStore._where(
            select(AuditLog), str_action_search="slide_%",
        )
        str_sql = str(obj_query.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True},
        ))
        self.assertIn("ILIKE", str_sql)
        self.assertIn("ESCAPE", str_sql)
        self.assertEqual(obj_query.whereclause.right.value, "%slide\\_\\%%")

    def test_migration_preserves_object_id(self):
        obj_id = ObjectId()
        dt_naive = datetime(2026, 9, 1, 0, 0)
        dict_copy = _with_string_id({"_id": obj_id, "dt_created_at": dt_naive})
        self.assertEqual(dict_copy["_id"], str(obj_id))
        self.assertEqual(dict_copy["dt_created_at"].tzinfo, timezone.utc)

    def test_json_extra_converts_bson_values(self):
        obj_id = ObjectId()
        _, dict_values = operational_store._audit_values({
            "str_action": "test",
            "nested": {"id": obj_id},
        })
        self.assertEqual(dict_values["dict_extra"]["nested"]["id"], str(obj_id))


if __name__ == "__main__":
    unittest.main()
