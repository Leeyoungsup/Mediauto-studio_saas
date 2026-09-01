import unittest
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.audit import (
    _compute_log_hmac,
    compute_audit_seal_hmac,
    compute_audit_snapshot_digest,
    verify_log_hmac,
)
from app.postgres.models import AuditLog
from app.repositories import operational_store


class OperationalStoreTests(unittest.TestCase):
    def test_postgres_repositories_are_the_only_backend(self):
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

    def test_json_extra_converts_custom_scalar_values(self):
        obj_id = "64f000000000000000000001"
        _, dict_values = operational_store._audit_values({
            "str_action": "test",
            "nested": {"id": obj_id},
        })
        self.assertEqual(dict_values["dict_extra"]["nested"]["id"], obj_id)

    def test_legacy_millisecond_loss_is_recovered_without_resigning(self):
        dt_exact = datetime(2026, 9, 1, 1, 2, 3, 456789, tzinfo=timezone.utc)
        dict_exact = {
            "str_action": "slide.view",
            "str_user_id": "64f000000000000000000001",
            "str_user_email": "admin",
            "str_resource_type": "slide",
            "str_resource_id": "slide-1",
            "str_detail": "sample.svs",
            "str_ip_address": "127.0.0.1",
            "dt_created_at": dt_exact,
            "str_prev_hmac": "",
        }
        dict_exact["str_hmac"] = _compute_log_hmac(dict_exact, "")
        dict_stored = dict(dict_exact)
        dict_stored["dt_created_at"] = dt_exact.replace(microsecond=456000)

        bool_valid, str_status, dt_recovered = verify_log_hmac(dict_stored)
        self.assertTrue(bool_valid)
        self.assertEqual(str_status, "valid_millisecond_recovered")
        self.assertEqual(dt_recovered, dt_exact)
        self.assertEqual(dict_stored["str_hmac"], dict_exact["str_hmac"])

    def test_snapshot_seal_detects_content_changes(self):
        list_logs = [{"_id": "1", "str_action": "a"}, {"_id": "2", "str_action": "b"}]
        str_digest = compute_audit_snapshot_digest(list_logs)
        str_hmac = compute_audit_seal_hmac("scope", 2, "1", "2", str_digest)
        list_logs[1]["str_action"] = "changed"
        str_changed = compute_audit_snapshot_digest(list_logs)
        self.assertNotEqual(str_digest, str_changed)
        self.assertNotEqual(
            str_hmac,
            compute_audit_seal_hmac("scope", 2, "1", "2", str_changed),
        )


if __name__ == "__main__":
    unittest.main()
