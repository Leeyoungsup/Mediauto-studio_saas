from datetime import datetime, timezone

import pytest

from app.audit import _compute_log_hmac, verify_log_hmac
from app.postgres.models import AuditLog
from app.repositories.operational_store import _audit_model_to_dict, _audit_values


def signed_record():
    record = {
        "int_hmac_version": 2, "str_action": "file.status", "str_user_id": "test",
        "str_user_email": None, "str_resource_type": "file", "str_resource_id": "test.svs",
        "str_detail": "Changed status", "str_ip_address": "127.0.0.1", "str_user_agent": "test",
        "dt_created_at": datetime(2026, 9, 14, tzinfo=timezone.utc),
        "dict_before": {"status": "pending"}, "dict_after": {"status": "done"},
        "list_filenames": ["test.svs"], "str_prev_hmac": "previous",
    }
    record["str_hmac"] = _compute_log_hmac(record, "previous")
    return record


@pytest.mark.parametrize("field,value", [("dict_before", {}), ("dict_after", {}),
                                        ("list_filenames", []), ("int_hmac_version", 1)])
def test_new_signature_detects_changed_details(field, value):
    record = signed_record()
    assert verify_log_hmac(record)[0]
    record[field] = value
    assert not verify_log_hmac(record)[0]


def test_new_signature_survives_repository_roundtrip_and_geo_enrichment():
    record = signed_record()
    identifier, values = _audit_values(record)
    restored = _audit_model_to_dict(AuditLog(str_id=identifier, **values))
    assert verify_log_hmac(restored)[0]
    restored["str_city"] = "Seoul"
    assert verify_log_hmac(restored)[0]


def test_legacy_record_keeps_original_verifier():
    record = signed_record()
    del record["int_hmac_version"]
    record["str_hmac"] = _compute_log_hmac(record, "previous")
    assert verify_log_hmac(record)[0]
