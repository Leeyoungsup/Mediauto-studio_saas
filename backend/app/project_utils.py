"""Helpers for project metadata and project-level AI task settings."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import HTTPException

from app.config import settings
from app.database import get_db, is_db_connected


ANNOTATION_AI_OPTIONS = [
    {
        "key": "quanti_he_breast",
        "label": "Quanti HE-breast",
        "group": "inherited",
        "base_model": "Quanti HE",
        "variant": "Breast",
        "inherit_classes": True,
    },
    {
        "key": "quanti_he_stomach",
        "label": "Quanti HE-stomach",
        "group": "inherited",
        "base_model": "Quanti HE",
        "variant": "Stomach",
        "inherit_classes": True,
    },
    {
        "key": "quanti_he_other",
        "label": "Quanti HE-other",
        "group": "inherited",
        "base_model": "Quanti HE",
        "variant": "Other",
        "inherit_classes": True,
    },
    {
        "key": "quanti_pd_l1_stomach",
        "label": "Quanti PD-L1 - Stomach (CPS)",
        "group": "inherited",
        "base_model": "Quanti PD-L1",
        "variant": "Stomach",
        "inherit_classes": True,
    },
    {
        "key": "quanti_pd_l1_lung",
        "label": "Quanti PD-L1 - Lung (TPS)",
        "group": "inherited",
        "base_model": "Quanti PD-L1",
        "variant": "Lung",
        "inherit_classes": True,
    },
    {
        "key": "quanti_ihc_her2",
        "label": "Quanti IHC - HER2",
        "group": "inherited",
        "base_model": "Quanti IHC",
        "variant": "HER2",
        "inherit_classes": True,
    },
    {
        "key": "quanti_ihc_er_pr",
        "label": "Quanti IHC - ER/PR (Allred)",
        "group": "inherited",
        "base_model": "Quanti IHC",
        "variant": "ER_PR",
        "inherit_classes": True,
    },
    {
        "key": "quanti_ihc_ki_67",
        "label": "Quanti IHC - KI-67",
        "group": "inherited",
        "base_model": "Quanti IHC",
        "variant": "KI_67",
        "inherit_classes": True,
    },
    {
        "key": "hne",
        "label": "HnE",
        "group": "non_inherited",
        "base_model": "Quanti HE",
        "variant": "Other",
        "inherit_classes": False,
    },
    {
        "key": "ihc_membrane",
        "label": "IHC Membrane",
        "group": "non_inherited",
        "base_model": "Quanti IHC",
        "variant": "HER2",
        "inherit_classes": False,
    },
    {
        "key": "ihc_nucleus",
        "label": "IHC Nucleus",
        "group": "non_inherited",
        "base_model": "Quanti IHC",
        "variant": "ER_PR",
        "inherit_classes": False,
    },
]

ANNOTATION_AI_OPTION_BY_KEY = {item["key"]: item for item in ANNOTATION_AI_OPTIONS}


def list_project_dirs() -> list[Path]:
    upload_root = Path(settings.UPLOAD_DIR)
    if not upload_root.exists():
        return []
    return sorted(
        [
            path
            for path in upload_root.iterdir()
            if path.is_dir() and not path.name.startswith(".") and not path.name.startswith("_chunks_")
        ],
        key=lambda path: path.name.lower(),
    )


def project_public_info(dict_doc: Optional[dict]) -> dict:
    dict_doc = dict_doc or {}
    list_tasks = []
    for task in dict_doc.get("list_project_ai_tasks") or []:
        dict_task = {"model": task.get("model", ""), "variant": task.get("variant", "")}
        if task.get("target_mpp") is not None:
            dict_task["target_mpp"] = float(task.get("target_mpp"))
        list_tasks.append(dict_task)
    dict_annotation_ai = normalize_annotation_ai_config(
        bool(dict_doc.get("bool_annotation_ai_enabled", False)),
        dict_doc.get("str_annotation_ai_key", ""),
    )
    return {
        "title": dict_doc.get("str_title", ""),
        "institution": dict_doc.get("str_institution", ""),
        "department": dict_doc.get("str_department", ""),
        "owner": dict_doc.get("str_owner", ""),
        "status": dict_doc.get("str_status", "active"),
        "due_date": dict_doc.get("str_due_date", ""),
        "description": dict_doc.get("str_description", ""),
        "project_ai_enabled": bool(dict_doc.get("bool_project_ai_enabled", False)),
        "project_ai_tasks": list_tasks,
        "annotation_ai_enabled": bool(dict_annotation_ai.get("enabled")),
        "annotation_ai": dict_annotation_ai,
    }


def clean_ai_tasks(list_raw: list) -> list[dict]:
    dict_legacy_models = {
        "HE-Fit": "Quanti HE",
        "PD-Score": "Quanti PD-L1",
        "Precise-IHC": "Quanti IHC",
        "VS-IHC": "VS IHC",
    }
    set_allowed_models = {"Quanti HE", "Quanti PD-L1", "Quanti IHC", "VS IHC"}
    list_clean = []
    for dict_t in list_raw if isinstance(list_raw, list) else []:
        if not isinstance(dict_t, dict):
            continue
        str_model = str(dict_t.get("model", "")).strip()
        str_variant = str(dict_t.get("variant", "")).strip()
        str_model = dict_legacy_models.get(str_model, str_model)
        if str_model not in set_allowed_models or not str_variant:
            continue
        dict_entry = {"model": str_model, "variant": str_variant}
        if str_model == "VS IHC":
            try:
                float_mpp = float(dict_t.get("target_mpp", 2.0))
            except (TypeError, ValueError):
                float_mpp = 2.0
            dict_entry["target_mpp"] = float_mpp
        list_clean.append(dict_entry)
    return list_clean


def parse_ai_tasks_json(tasks_json: str) -> list[dict]:
    try:
        list_raw = json.loads(tasks_json or "[]")
        if not isinstance(list_raw, list):
            raise ValueError("tasks_json must be a JSON array")
    except Exception as exc:
        raise HTTPException(400, f"Invalid tasks_json: {exc}")
    return clean_ai_tasks(list_raw)


def normalize_annotation_ai_config(enabled: bool, key: str) -> dict:
    str_key = str(key or "").strip()
    option = ANNOTATION_AI_OPTION_BY_KEY.get(str_key)
    if not option:
        return {"enabled": False, "key": "", "label": ""}
    return {
        "enabled": bool(enabled),
        "key": option["key"],
        "label": option["label"],
        "group": option["group"],
        "base_model": option["base_model"],
        "variant": option["variant"],
        "inherit_classes": bool(option["inherit_classes"]),
    }


async def upsert_project_info(
    *,
    str_project_path: str,
    str_title: str = "",
    str_institution: str = "",
    str_department: str = "",
    str_owner: str = "",
    str_status: str = "active",
    str_due_date: str = "",
    str_description: str = "",
    bool_project_ai_enabled: bool = False,
    list_project_ai_tasks: Optional[list[dict]] = None,
    bool_annotation_ai_enabled: bool = False,
    str_annotation_ai_key: str = "",
) -> None:
    if not is_db_connected():
        return
    db = get_db()
    dt_now = datetime.now(timezone.utc)
    dict_annotation_ai = normalize_annotation_ai_config(bool_annotation_ai_enabled, str_annotation_ai_key)
    await db.project_infos.update_one(
        {"str_project_path": str_project_path},
        {
            "$set": {
                "str_project_path": str_project_path,
                "str_title": str_title.strip(),
                "str_institution": str_institution.strip(),
                "str_department": str_department.strip(),
                "str_owner": str_owner.strip(),
                "str_status": (str_status or "active").strip(),
                "str_due_date": str_due_date.strip(),
                "str_description": str_description.strip(),
                "bool_project_ai_enabled": bool(bool_project_ai_enabled),
                "list_project_ai_tasks": clean_ai_tasks(list_project_ai_tasks or []),
                "bool_annotation_ai_enabled": bool(dict_annotation_ai.get("enabled")),
                "str_annotation_ai_key": dict_annotation_ai.get("key", ""),
                "dt_updated_at": dt_now,
            },
            "$setOnInsert": {"dt_created_at": dt_now},
        },
        upsert=True,
    )
