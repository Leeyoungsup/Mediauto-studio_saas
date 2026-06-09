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
CELL_ANNOTATION_ROOT = Path(__file__).resolve().parents[1] / "cell_annotation"
OTHER_CELL_CLASS = {"id": "other", "name": "Other", "color": [149, 165, 166]}


def _hex_to_rgb(value: str) -> list[int]:
    raw = str(value or "").strip().lstrip("#")
    if len(raw) != 6:
        return [149, 165, 166]
    try:
        return [int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)]
    except Exception:
        return [149, 165, 166]


def _classes_from_model_metadata(class_names: dict, class_colors: dict) -> list[dict]:
    classes = []
    for class_id in sorted(int(key) for key in class_names):
        str_class_id = str(class_id)
        classes.append({
            "id": str_class_id,
            "name": str(class_names.get(class_id, class_names.get(str_class_id, ""))),
            "color": _hex_to_rgb(class_colors.get(class_id, class_colors.get(str_class_id, "#95a5a6"))),
        })
    if classes and not any(str(cls.get("name", "")).lower() == "other" for cls in classes):
        classes.append(dict(OTHER_CELL_CLASS))
    return classes or [dict(OTHER_CELL_CLASS)]


def _normalize_cell_class_color(value) -> list[int]:
    if isinstance(value, str):
        return _hex_to_rgb(value)
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        out = []
        for item in value[:3]:
            try:
                out.append(max(0, min(255, int(item))))
            except Exception:
                out.append(0)
        return out
    return list(OTHER_CELL_CLASS["color"])


def _normalize_cell_classes(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    classes = []
    seen = set()
    for idx, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()[:64] or f"Class {idx}"
        raw_id = str(item.get("id") or name).strip()[:80]
        raw_id = "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in raw_id)
        raw_id = raw_id.strip("_-") or f"class_{idx}"
        base_id = raw_id
        suffix = 2
        while raw_id in seen:
            raw_id = f"{base_id}_{suffix}"
            suffix += 1
        seen.add(raw_id)
        classes.append({
            "id": raw_id,
            "name": name,
            "color": _normalize_cell_class_color(item.get("color")),
        })
    return classes


def _merge_cell_classes(base_classes: list[dict], default_classes: list[dict]) -> list[dict]:
    default_names = {str(cls.get("name", "")).lower() for cls in (default_classes or []) if cls.get("name")}
    default_ids = {str(cls.get("id", "")) for cls in (default_classes or []) if cls.get("id") is not None}
    merged = [
        cls for cls in (base_classes or [])
        if str(cls.get("id", "")) in default_ids or str(cls.get("name", "")).lower() not in default_names
    ]
    seen_ids = {str(cls.get("id", "")) for cls in merged}
    for cls in default_classes or []:
        cls_id = str(cls.get("id", ""))
        if cls_id in seen_ids:
            continue
        merged.append(dict(cls))
        seen_ids.add(cls_id)
    has_other = any(str(cls.get("name", "")).lower() == "other" for cls in merged)
    if not has_other:
        other_id = str(OTHER_CELL_CLASS["id"])
        if other_id in seen_ids:
            other_id = "other_cell"
        merged.append({**OTHER_CELL_CLASS, "id": other_id})
    return merged or [dict(OTHER_CELL_CLASS)]


def cell_annotation_classes_for_ai(enabled: bool, key: str) -> list[dict]:
    dict_config = normalize_annotation_ai_config(enabled, key)
    if not dict_config.get("enabled"):
        return []
    if not dict_config.get("inherit_classes"):
        return [dict(OTHER_CELL_CLASS)]
    str_base_model = dict_config.get("base_model")
    str_variant = dict_config.get("variant")
    if str_base_model == "Quanti HE":
        from ai.quanti_he import CLASS_COLORS, CLASS_NAMES

        return _classes_from_model_metadata(CLASS_NAMES, CLASS_COLORS)
    if str_base_model == "Quanti PD-L1":
        from app.ai_pipelines.scoring import PD_SCORE_CONFIG

        dict_model = PD_SCORE_CONFIG.get(str_variant) or {}
        return _classes_from_model_metadata(
            dict_model.get("class_names") or {},
            dict_model.get("class_colors") or {},
        )
    if str_base_model == "Quanti IHC":
        from app.ai_pipelines.scoring import PRECISE_IHC_CONFIG

        dict_model = PRECISE_IHC_CONFIG.get(str_variant) or {}
        return _classes_from_model_metadata(
            dict_model.get("class_names") or {},
            dict_model.get("class_colors") or {},
        )
    return [dict(OTHER_CELL_CLASS)]


def sync_project_cell_annotation_classes(str_project_path: str, enabled: bool, key: str) -> list[dict]:
    str_project = str(str_project_path or "").replace("\\", "/").split("/")[0].strip()
    if not str_project:
        return []
    path_classes = CELL_ANNOTATION_ROOT / "_projects" / str_project / "classes.json"
    existing_classes = []
    if path_classes.exists():
        try:
            payload = json.loads(path_classes.read_text(encoding="utf-8"))
            existing_classes = _normalize_cell_classes(payload.get("classes") if isinstance(payload, dict) else payload)
        except Exception:
            existing_classes = []
    classes = _merge_cell_classes(existing_classes, cell_annotation_classes_for_ai(enabled, key))
    path_classes.parent.mkdir(parents=True, exist_ok=True)
    path_classes.write_text(json.dumps({"classes": classes}, ensure_ascii=False, indent=2), encoding="utf-8")
    return classes


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
