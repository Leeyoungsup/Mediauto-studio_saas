"""Case-level clinical information helpers.

Clinical metadata is shared by AI and annotation viewers.  The source of truth
is the case name extracted from CODIPAI-style filenames, so slides from the same
case share one clinical-info document.
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import HTTPException

CLINICAL_INFO_KEYS = {
    "ER_proportion_score",
    "ER_intensity_score",
    "PR_proportion_score",
    "PR_intensity_score",
    "Ki67_index",
    "PD-L1_CPS_score",
    "ISH_for_HER2_(FISH_SISH)",
    "IHC_for_C-erbB2",
}


def case_name_from_filename(filename: str) -> str:
    """Extract BRCA-SS-00192 from CODIPAI-BRCA-SS-00192-I-KI-01.svs."""
    stem = Path(filename or "").stem
    parts = [part for part in stem.split("-") if part]
    if len(parts) >= 4 and parts[0].upper() == "CODIPAI":
        return "-".join(parts[1:4])
    if len(parts) >= 3:
        return "-".join(parts[:3])
    return stem


def case_filename_regex(case_name: str) -> str:
    return rf"(^|-)({re.escape(case_name)})(-|$)"


def normalize_clinical_info(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise HTTPException(400, "Invalid clinical info payload")
    clinical_info = {}
    for key in CLINICAL_INFO_KEYS:
        value = raw.get(key, "")
        if value is None:
            value = ""
        clinical_info[key] = str(value).strip()[:120]
    return clinical_info


def has_clinical_info(info: Optional[dict]) -> bool:
    return any(str(value or "").strip() for value in (info or {}).values())


def iso_datetime(value) -> Optional[str]:
    if not value:
        return None
    if not getattr(value, "tzinfo", None):
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.isoformat()


async def get_case_clinical_info(db, case_name: str) -> dict:
    case_doc = await db.case_clinical_info.find_one({"str_case_name": case_name})
    if case_doc and isinstance(case_doc.get("dict_clinical_info"), dict):
        return case_doc.get("dict_clinical_info") or {}
    slide_doc = await db.slides.find_one({
        "$or": [
            {"str_case_name": case_name},
            {"str_filename": {"$regex": case_filename_regex(case_name)}},
        ],
        "dict_clinical_info": {"$exists": True},
    })
    return (slide_doc or {}).get("dict_clinical_info") or {}


async def upsert_case_clinical_info(db, case_name: str, clinical_info: dict) -> None:
    now = datetime.now(timezone.utc)
    await db.case_clinical_info.update_one(
        {"str_case_name": case_name},
        {
            "$set": {
                "str_case_name": case_name,
                "dict_clinical_info": clinical_info,
                "dt_updated_at": now,
            },
            "$setOnInsert": {"dt_created_at": now},
        },
        upsert=True,
    )
    await db.slides.update_many(
        {"$or": [
            {"str_case_name": case_name},
            {"str_filename": {"$regex": case_filename_regex(case_name)}},
        ]},
        {"$set": {
            "str_case_name": case_name,
            "dict_clinical_info": clinical_info,
            "dt_updated_at": now,
        }},
    )
