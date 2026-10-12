"""Specialist stopwatch records compared with full AI result display time."""
import asyncio
import hashlib
import json
import math
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth import get_current_user, require_capability
from app.audit import get_client_ip, log_audit_event
from app.config import settings
from app.comparison_files import write_comparison_json
from app.ai_pipelines.scoring import PD_SCORE_CONFIG
from app.database import get_db, is_db_connected
from app.path_utils import rel_path_for, safe_filename
from app.slide_identity import slide_cache_key
from app.slide_manager import slide_manager
from app.repositories.application_store import PostgresDocumentCollection

router = APIRouter(dependencies=[Depends(get_current_user)])


def store():
    if not is_db_connected():
        raise HTTPException(503, "Comparison storage is unavailable")
    return PostgresDocumentCollection("pd_l1_comparisons")


class JsonReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slide_id: str = Field(min_length=1, max_length=64)
    tissue_type: Literal["Stomach", "Breast", "Lung"] = "Stomach"


class ComparisonRequest(JsonReadRequest):
    run_id: uuid.UUID
    specialist_elapsed_ms: float = Field(gt=0, le=86_400_000, allow_inf_nan=False)
    percentage: float = Field(ge=0, le=100, allow_inf_nan=False)
    grade: str = Field(min_length=1, max_length=80)
    ai_read_id: str | None = Field(default=None, max_length=64)
    ai_result_elapsed_ms: float | None = Field(default=None, gt=0, le=86_400_000, allow_inf_nan=False)
    ai_timing_basis: Literal["request_to_display", "slide_entry_to_display"] = "request_to_display"

    @field_validator("grade")
    @classmethod
    def valid_grade(cls, value):
        value = value.strip()
        if not value or any(ord(c) < 32 for c in value):
            raise ValueError("Enter a valid grade")
        return value


def score_grade(percentage: float, tissue: str) -> str:
    """Display score bands, not a numbered clinical grade or treatment decision.

    CPS 1/10: Agilent 22C3 CPS interpretation training.
    TPS 1/50: FDA P150013/S006 assay expression categories.
    """
    score_type, upper = ("TPS", 50) if tissue == "Lung" else ("CPS", 10)
    if percentage < 1:
        return f"{score_type} < 1"
    if percentage < upper:
        return f"1 ≤ {score_type} < {upper}"
    return f"{score_type} ≥ {upper}"


def slide_context(slide_id):
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "Open the slide before recording a comparison")
    relative = rel_path_for(info.file_path)
    if not relative:
        raise HTTPException(400, "Select a slide inside a project")
    return info, relative.split("/")[0]


async def check_project_model(project, tissue):
    document = await get_db().project_infos.find_one({"str_project_path": project})
    fixed = (document or {}).get("str_comparison_tissue_type")
    if fixed in PD_SCORE_CONFIG and fixed != tissue:
        raise HTTPException(409, "The project comparison model has changed. Reopen the project to use its fixed model.")


def read_json(path, tissue):
    # This interval contains file read and JSON parsing only, never model inference.
    started = time.perf_counter()
    try:
        with path.open("r", encoding="utf-8") as file:
            result = json.load(file)
    except FileNotFoundError:
        raise HTTPException(404, "No saved PD-L1 JSON for this slide and tissue")
    except (OSError, ValueError):
        raise HTTPException(422, "Saved PD-L1 JSON could not be read")
    elapsed = (time.perf_counter() - started) * 1000
    score = result.get("pd_score") if isinstance(result, dict) else None
    expected = PD_SCORE_CONFIG[tissue]["score_type"]
    if not isinstance(score, dict) or score.get("score_type") != expected:
        raise HTTPException(422, "Saved JSON does not contain the selected PD-L1 score")
    value = score.get("score")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100:
        raise HTTPException(422, "Saved JSON contains an invalid PD-L1 score")
    grade = score.get("grade")
    return {"ai_json_elapsed_ms": elapsed, "ai_percentage": value,
            "ai_grade": str(grade)[:80] if grade is not None else None,
            "score_type": expected, "result": result}


@router.post("/read-json")
async def read_saved_json(body: JsonReadRequest, user=Depends(get_current_user)):
    repository = store()
    info, project = slide_context(body.slide_id)
    await check_project_model(project, body.tissue_type)
    key = slide_cache_key(info.file_path)
    directory = (Path(settings.AI_RESULTS_DIR) / "Quanti PD-L1").resolve()
    path = directory / f"{key}_Quanti PD-L1_{body.tissue_type}.json"
    if path.is_symlink():
        raise HTTPException(422, "Saved JSON must be a regular cache file")
    result = await asyncio.to_thread(read_json, path, body.tissue_type)
    payload = result.pop("result")
    record = {"_id": uuid.uuid4().hex, "kind": "json_read", "project_path": project,
              "slide_id": body.slide_id, "filename": Path(info.file_path).name,
              "tissue_type": body.tissue_type, "user_id": user["_id"],
              "dt_created_at": datetime.now(timezone.utc), **result}
    await repository.insert_one(record)
    return {"ai_read_id": record["_id"], **result, "result": payload}


async def export_comparison(record, slide_path):
    try:
        await asyncio.to_thread(write_comparison_json, record, slide_path)
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(503, "DB record retained, but comparison JSON could not be saved. Retry this measurement.")


@router.post("/records")
async def save_comparison(body: ComparisonRequest, request: Request,
                          user=Depends(require_capability("comparison.write"))):
    repository = store()
    info, project = slide_context(body.slide_id)
    identifier = hashlib.sha256(f"{user['_id']}:{body.run_id}".encode()).hexdigest()
    signature = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    existing = await repository.find_one({"_id": identifier})
    if existing:
        if existing.get("request_signature") != signature:
            raise HTTPException(409, "This measurement has already been recorded")
        await export_comparison(existing, info.file_path)
        return existing
    await check_project_model(project, body.tissue_type)
    if body.ai_result_elapsed_ms is not None and not body.ai_read_id:
        raise HTTPException(400, "AI display timing requires a JSON receipt")
    ai = {}
    if body.ai_read_id:
        ai = await repository.find_one({"_id": body.ai_read_id, "kind": "json_read"})
        if not ai or any(ai.get(k) != v for k, v in {
            "user_id": user["_id"], "slide_id": body.slide_id,
            "project_path": project, "tissue_type": body.tissue_type,
        }.items()):
            raise HTTPException(400, "JSON timing belongs to a different measurement context")
    record = {"_id": identifier, "kind": "comparison", "project_path": project,
              "slide_id": body.slide_id, "filename": Path(info.file_path).name,
              "user_id": user["_id"], "user_name": user.get("str_name", ""),
              "username": user.get("str_username", ""), "tissue_type": body.tissue_type,
              "score_type": PD_SCORE_CONFIG[body.tissue_type]["score_type"],
              "percentage": body.percentage, "grade": score_grade(body.percentage, body.tissue_type),
              "grade_basis": "score_bands_v1",
              "specialist_elapsed_ms": body.specialist_elapsed_ms,
              "ai_read_id": body.ai_read_id,
              "ai_result_elapsed_ms": body.ai_result_elapsed_ms,
              "ai_timing_basis": body.ai_timing_basis if body.ai_result_elapsed_ms is not None else None,
              "ai_json_elapsed_ms": ai.get("ai_json_elapsed_ms"),
              "ai_percentage": ai.get("ai_percentage"), "ai_grade": ai.get("ai_grade"),
              "request_signature": signature, "dt_created_at": datetime.now(timezone.utc)}
    await repository.insert_one(record)
    await log_audit_event(str_action="pd_l1.comparison_saved", str_user_id=user["_id"],
                          str_resource_type="pd_l1_comparison", str_resource_id=identifier,
                          str_detail="Specialist assessment and AI result timing recorded",
                          str_ip_address=get_client_ip(request))
    await export_comparison(record, info.file_path)
    return record


@router.get("/records")
async def list_comparisons(slide_id: str = Query(min_length=1, max_length=64),
                           limit: int = Query(default=50, ge=1, le=200)):
    _, project = slide_context(slide_id)
    records = await store().find({"kind": "comparison", "project_path": project,
                                  "slide_id": slide_id}).sort("dt_created_at", -1).to_list(length=None)
    # Keep all measurement history stored, but show each account's latest assessment.
    latest = {}
    for record in records:
        latest.setdefault(record["user_id"], record)
    return {"records": list(latest.values())[:limit]}


@router.get("/completed")
async def completed_slides(project_path: str = Query(min_length=1, max_length=256),
                           user=Depends(get_current_user)):
    project = safe_filename(project_path)
    records = await store().find({"kind": "comparison", "project_path": project,
                                  "user_id": user["_id"]}).to_list(length=None)
    return {"user_id": user["_id"],
            "slide_ids": sorted({record["slide_id"] for record in records})}
