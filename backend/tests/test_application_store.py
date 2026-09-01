from datetime import datetime, timezone

from app.repositories.application_store import (
    apply_projection,
    decode_document_value,
    document_matches,
    encode_document_value,
)


def test_document_codec_preserves_datetime_and_string_id():
    obj_id = "64f000000000000000000001"
    dt_value = datetime(2026, 9, 1, 1, 2, 3, 456789, tzinfo=timezone.utc)
    dict_round_trip = decode_document_value(encode_document_value({
        "_id": obj_id,
        "dt_updated_at": dt_value,
        "list_nested": [{"dt_value": dt_value}],
    }))
    assert dict_round_trip["_id"] == obj_id
    assert dict_round_trip["dt_updated_at"] == dt_value
    assert dict_round_trip["list_nested"][0]["dt_value"] == dt_value


def test_document_matcher_supports_application_queries():
    dict_doc = {
        "str_slide_id": "slide-1",
        "str_status": "done",
        "str_patch_id": "patch_12",
        "dict_ai_results": {"Quanti HE": {"bool_has_result": True}},
        "list_variants": ["ER", "PR"],
    }
    assert document_matches(dict_doc, {
        "$or": [
            {"str_status": "pending"},
            {"dict_ai_results.Quanti HE.bool_has_result": True},
        ],
        "str_patch_id": {"$regex": r"^patch_\d+$"},
        "list_variants": {"$in": ["PR"]},
    })
    assert document_matches(dict_doc, {"missing": {"$exists": False}})
    assert not document_matches(dict_doc, {"str_status": {"$ne": "done"}})


def test_projection_matches_mongo_include_and_exclude_rules():
    dict_doc = {
        "_id": "id-1",
        "str_status": "done",
        "dict_ai_results": {"Quanti HE": {"bool_has_result": True}},
        "str_secret": "hidden",
    }
    assert apply_projection(dict_doc, {"str_status": 1, "_id": 0}) == {
        "str_status": "done",
    }
    assert apply_projection(dict_doc, {"str_secret": 0}) == {
        "_id": "id-1",
        "str_status": "done",
        "dict_ai_results": {"Quanti HE": {"bool_has_result": True}},
    }
