"""AI text text text — text text text text text

text:
- 1text `folder_ai_configs` text text (SCAN_INTERVAL_SECONDS)
- text idle text text text (IDLE_THRESHOLD_SECONDS text text AI text text)
- text text text text text (upload counter text text)
- text text text text text text (model, variant) text text
- text text text text text idle text — text text text text text

Claude.md text text (str_/int_/bool_/list_/dict_/dt_ text).
"""

import asyncio
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from app.ai_pipelines.dedup import (
    cache_has_current_detection_postprocess,
    processing_metadata,
)
from app.slide_identity import slide_cache_key


# ── text text ──
IDLE_THRESHOLD_SECONDS = 600   # 10text text AI text text → idle
SCAN_INTERVAL_SECONDS = 60     # 1text text
STARTUP_SCAN_DELAY_SECONDS = 5
SCAN_STALE_CACHES = os.environ.get(
    "MEDIAUTO_AUTO_AI_SCAN_STALE_CACHES", ""
).lower() in ("1", "true", "yes")
IDLE_BLOCK_LOG_INTERVAL_SECONDS = 600
SCAN_SUMMARY_LOG_INTERVAL_SECONDS = 600

# ── text text text text ──
_activity_lock = threading.Lock()
_last_ai_activity_ts: float = time.monotonic() - IDLE_THRESHOLD_SECONDS
_upload_in_progress: int = 0
_worker_task: Optional[asyncio.Task] = None
_marker_cache_quality_cache: dict = {}
_last_idle_block_log_ts: float = 0.0
_last_scan_summary_log_ts: float = 0.0

_MARKER_CACHE_METADATA_WINDOW_BYTES = 64 * 1024
_CACHE_METADATA_KEYS = (
    "model_runtime",
    "patch_overlap_um",
    "global_dedup_version",
    "excluded_class_suppression_iou_threshold",
    "excluded_class_suppression_rule",
)
_CACHE_METADATA_MISSING = object()


def _log_throttled(str_key: str, str_message: str, float_interval: float) -> None:
    """Print noisy worker diagnostics at most once per interval."""
    global _last_idle_block_log_ts, _last_scan_summary_log_ts
    float_now = time.monotonic()
    if str_key == "idle_block":
        if _last_idle_block_log_ts + float_interval > float_now:
            return
        _last_idle_block_log_ts = float_now
    elif str_key == "scan_summary":
        if _last_scan_summary_log_ts + float_interval > float_now:
            return
        _last_scan_summary_log_ts = float_now
    print(str_message)


# ═══════════════════════════
# text text API
# ═══════════════════════════

def ping_ai_activity() -> None:
    """text AI text text / text text text text — idle text text."""
    global _last_ai_activity_ts
    with _activity_lock:
        _last_ai_activity_ts = time.monotonic()


def upload_enter() -> None:
    global _upload_in_progress
    with _activity_lock:
        _upload_in_progress += 1


def upload_exit() -> None:
    global _upload_in_progress
    with _activity_lock:
        _upload_in_progress = max(0, _upload_in_progress - 1)


def _is_activity_idle_nolock() -> bool:
    """_activity_lock text text text text text — text/text text text."""
    if _upload_in_progress > 0:
        return False
    if (time.monotonic() - _last_ai_activity_ts) < IDLE_THRESHOLD_SECONDS:
        return False
    return True


def is_system_idle() -> bool:
    """text text text text text text (text pre-check).

    text (text text idle):
      1. text text text text
      2. text text AI text text IDLE_THRESHOLD_SECONDS text
      3. text text text(queued/running) text AI task text

    text: text text text text text, text text task text text text task text
    text text text. text reservation text check_idle_and_reserve() text text text.
    """
    with _activity_lock:
        int_uploads = _upload_in_progress
        float_idle_for = time.monotonic() - _last_ai_activity_ts
        if not _is_activity_idle_nolock():
            if int_uploads > 0:
                _log_throttled(
                    "idle_block",
                    f"[auto_ai] idle blocked: upload in progress ({int_uploads})",
                    IDLE_BLOCK_LOG_INTERVAL_SECONDS,
                )
            else:
                _log_throttled(
                    "idle_block",
                    f"[auto_ai] idle blocked: recent AI activity {float_idle_for:.0f}s ago "
                    f"(threshold {IDLE_THRESHOLD_SECONDS}s)",
                    IDLE_BLOCK_LOG_INTERVAL_SECONDS,
                )
            return False

    try:
        from app.routers import ai as ai_router
        with ai_router._tasks_lock:
            list_active_tasks = []
            for dict_task in ai_router._tasks.values():
                if dict_task.get("status") in ("queued", "running"):
                    list_active_tasks.append(dict_task)
            if list_active_tasks:
                list_desc = []
                float_now = time.time()
                for dict_task in list_active_tasks[:5]:
                    float_created = float(
                        dict_task.get("created_at")
                        or dict_task.get("updated_at")
                        or float_now
                    )
                    list_desc.append(
                        f"{dict_task.get('status')} "
                        f"{dict_task.get('model') or '?'}"
                        f"/{dict_task.get('variant') or '?'} "
                        f"{dict_task.get('slide_filename') or '?'} "
                        f"age={float_now - float_created:.0f}s"
                    )
                _log_throttled(
                    "idle_block",
                    f"[auto_ai] idle blocked: {len(list_active_tasks)} active AI task(s): "
                    + "; ".join(list_desc),
                    IDLE_BLOCK_LOG_INTERVAL_SECONDS,
                )
                return False
    except Exception:
        pass

    return True


def check_idle_and_reserve(str_task_id: str, dict_task_initial: dict) -> bool:
    """text "idle text + task slot text".

    _tasks_lock text _activity_lock text text text text text idle text text
    text text text _tasks text text text text. text text text text
    text _tasks_lock text task text insert text text/text race text text text.

    Lock text: _tasks_lock → _activity_lock (text text _tasks_lock text text
    text text text; _activity_lock text _tasks_lock text text text text
    text text).
    """
    try:
        from app.routers import ai as ai_router
    except Exception:
        return False

    with ai_router._tasks_lock:
        for dict_task in ai_router._tasks.values():
            if dict_task.get("status") in ("queued", "running"):
                return False
        with _activity_lock:
            if not _is_activity_idle_nolock():
                return False
        ai_router._tasks[str_task_id] = dict_task_initial
        return True


# ═══════════════════════════
# text text
# ═══════════════════════════

async def _run_auto_inference(
    str_full_path: str,
    str_model: str,
    str_variant: str,
    float_target_mpp: float = 2.0,
    dict_annotation_ai: Optional[dict] = None,
) -> None:
    """text text/text/variant text text text text text."""
    from app.slide_manager import slide_manager
    from app.routers import ai as ai_router

    str_filename = Path(str_full_path).name
    str_slide_id = slide_cache_key(str_full_path)

    # slide_manager text text open (text _open_and_generate text text text subset)
    if slide_manager.get(str_slide_id) is None:
        try:
            slide_manager.open(str_slide_id, str_full_path)
        except Exception as e:
            print(f"[auto_ai] open failed {str_filename}: {e}")
            return

    str_task_id = f"auto_{uuid.uuid4().hex[:10]}"
    dict_initial = {
        "status": "queued",
        "progress": 0,
        "result": None,
        "error": None,
        "status_msg": "",
        "slide_filename": str_filename,
        "model": str_model,
        "variant": str_variant,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    # text idle text + text. text task text text text text text abort.
    if not check_idle_and_reserve(str_task_id, dict_initial):
        print(f"[auto_ai] reserve aborted (activity detected) — skip {str_filename}")
        return

    def _dispatch() -> None:
        if dict_annotation_ai:
            from app.routers.cell_annotation import _run_labeling_assistance_task
            _run_labeling_assistance_task(
                str_task_id, str_slide_id, str_full_path, dict_annotation_ai
            )
        elif str_model in ("Quanti HE", "HE-Fit"):
            ai_router._run_detection(str_task_id, str_slide_id, None, str_variant)
        elif str_model in ("Quanti PD-L1", "PD-Score"):
            ai_router._run_pd_score(str_task_id, str_slide_id, None, str_variant)
        elif str_model in ("Quanti IHC", "Precise-IHC"):
            ai_router._run_precise_ihc(str_task_id, str_slide_id, None, str_variant)
        elif str_model in ("VS IHC", "VS-IHC"):
            # variant = stain_type (e.g. "ihc_membrane"), target_mpp text task text
            ai_router._run_virtual_stain(str_task_id, str_slide_id, None, str_variant, float_target_mpp)
        else:
            print(f"[auto_ai] unsupported model: {str_model}")

    print(f"[auto_ai] inferring {str_model}/{str_variant} on {str_filename}")
    from app.cpu_layout import ai_executor
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(ai_executor, _dispatch)
    with ai_router._tasks_lock:
        dict_finished = ai_router._tasks.get(str_task_id) or {}
        if dict_finished.get("status") == "error":
            raise RuntimeError(dict_finished.get("error") or "AI task failed")
    print(f"[auto_ai] done {str_model}/{str_variant} on {str_filename}")


def _vs_cache_exists(str_full_path: str, float_target_mpp: float) -> bool:
    """_run_virtual_stain text text hit text text — meta.json + (level-0 text OR text PNG).

    auto_ai text text text text text text text text text hit text text
    "inferring/done" text text text text text text text text.
    """
    from app.ai_pipelines.cache_paths import get_vs_cache_paths as _get_vs_cache_paths, get_vs_tile_dir as _get_vs_tile_dir
    from app.config import settings
    png_path, meta_path = _get_vs_cache_paths(str_full_path, float_target_mpp)
    if not meta_path.exists():
        return False
    from app.ai_pipelines.model_identity import model_identity
    from app.ai_pipelines.virtual_stain import VS_MODEL_FILES
    try:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            return False
        model_file = VS_MODEL_FILES.get(metadata.get("stain_type"))
        if not model_file or metadata.get("model_identity") != model_identity(Path(settings.MODEL_DIR) / model_file):
            return False
    except (OSError, ValueError, TypeError):
        return False
    path_lvl0 = _get_vs_tile_dir(str_full_path, float_target_mpp) / '0'
    bool_tiles_ok = path_lvl0.exists() and any(path_lvl0.glob('*.jpeg'))
    bool_png_legacy = png_path.exists()
    return bool_tiles_ok or bool_png_legacy


def _cell_has_bbox(cell) -> bool:
    if isinstance(cell, (list, tuple)):
        return len(cell) >= 8 and all(isinstance(cell[i], (int, float)) for i in range(4, 8))
    if isinstance(cell, dict):
        return all(k in cell for k in ("x0", "y0", "x1", "y1"))
    return False


def _marker_cache_path(str_full_path: str, str_model: str, str_variant: str) -> Optional[Path]:
    from app.ai_pipelines.cache_paths import (
        get_ai_cache_path,
        get_pd_score_cache_path,
        get_precise_ihc_cache_path,
    )

    if str_model in ("Quanti HE", "HE-Fit"):
        return get_ai_cache_path(str_full_path, str_variant)
    if str_model in ("Quanti PD-L1", "PD-Score"):
        return get_pd_score_cache_path(str_full_path, str_variant)
    if str_model in ("Quanti IHC", "Precise-IHC"):
        return get_precise_ihc_cache_path(str_full_path, str_variant)
    return None


def _marker_cache_requires_excluded_cells(str_model: str, str_variant: str) -> bool:
    try:
        if str_model in ("Quanti PD-L1", "PD-Score"):
            from app.ai_pipelines.scoring import PD_SCORE_CONFIG
            return bool((PD_SCORE_CONFIG.get(str_variant) or {}).get("exclude_classes"))
        if str_model in ("Quanti IHC", "Precise-IHC"):
            from app.ai_pipelines.scoring import PRECISE_IHC_CONFIG
            return bool((PRECISE_IHC_CONFIG.get(str_variant) or {}).get("exclude_classes"))
    except Exception:
        return False
    return False


def _expected_marker_model_runtime(str_model: str, str_variant: str) -> Optional[dict]:
    """Return model identity for markers whose architecture must invalidate cache."""
    if str_model not in ("Quanti IHC", "Precise-IHC"):
        return None
    try:
        from app.ai_pipelines.marker_pipeline import marker_model_runtime_metadata
        from app.ai_pipelines.scoring import PRECISE_IHC_CONFIG

        dict_config = PRECISE_IHC_CONFIG.get(str_variant) or {}
        if not dict_config.get("model_arch"):
            return None
        return marker_model_runtime_metadata(dict_config)
    except Exception as exc:
        _log_throttled(
            "scan_summary",
            f"[auto_ai] cannot resolve {str_model}/{str_variant} model runtime: {exc}",
            SCAN_SUMMARY_LOG_INTERVAL_SECONDS,
        )
        return None


def _json_value_after_key(str_chunk: str, str_key: str):
    """Decode one small JSON value from a cache head/tail chunk."""
    list_matches = list(re.finditer(rf'"{re.escape(str_key)}"\s*:\s*', str_chunk))
    if not list_matches:
        return _CACHE_METADATA_MISSING
    int_start = list_matches[-1].end()
    while int_start < len(str_chunk) and str_chunk[int_start].isspace():
        int_start += 1
    try:
        value, _ = json.JSONDecoder().raw_decode(str_chunk, int_start)
        return value
    except (ValueError, json.JSONDecodeError):
        return _CACHE_METADATA_MISSING


def _first_cached_cell_from_head(str_head: str):
    """Return (has_cells, first_cell) without decoding the full cells array."""
    match = re.search(r'"cells"\s*:\s*\[', str_head)
    if not match:
        return None
    int_start = match.end()
    while int_start < len(str_head) and str_head[int_start].isspace():
        int_start += 1
    if int_start >= len(str_head):
        return None
    if str_head[int_start] == "]":
        return False, None
    try:
        first_cell, _ = json.JSONDecoder().raw_decode(str_head, int_start)
        return True, first_cell
    except (ValueError, json.JSONDecodeError):
        return None


def _read_marker_cache_metadata(cache_path: Path) -> Optional[dict]:
    """Read only cache metadata plus the first compact cell.

    Marker caches can contain multi-million-cell arrays and reach hundreds of
    megabytes.  Auto-worker validation only needs a few top-level metadata
    fields and the first cell's bbox shape, so cap I/O at 64 KiB from each end.
    Full JSON validity is checked when a result is actually loaded by its
    pipeline; this startup scan must never deserialize the cell arrays.
    """
    try:
        with open(cache_path, "rb") as file_cache:
            int_size = file_cache.seek(0, os.SEEK_END)
            file_cache.seek(0)
            bytes_head = file_cache.read(_MARKER_CACHE_METADATA_WINDOW_BYTES)
            if int_size <= _MARKER_CACHE_METADATA_WINDOW_BYTES:
                bytes_tail = bytes_head
            else:
                file_cache.seek(max(0, int_size - _MARKER_CACHE_METADATA_WINDOW_BYTES))
                bytes_tail = file_cache.read(_MARKER_CACHE_METADATA_WINDOW_BYTES)
    except OSError:
        return None

    str_head = bytes_head.decode("utf-8", errors="ignore")
    str_tail = bytes_tail.decode("utf-8", errors="ignore")
    if not str_head.lstrip().startswith("{") or not str_tail.rstrip().endswith("}"):
        return None

    tuple_first_cell = _first_cached_cell_from_head(str_head)
    if tuple_first_cell is None:
        return None

    dict_metadata = {
        "has_cells": tuple_first_cell[0],
        "first_cell": tuple_first_cell[1],
    }
    for str_key in _CACHE_METADATA_KEYS:
        value = _json_value_after_key(str_tail, str_key)
        if value is _CACHE_METADATA_MISSING and str_tail != str_head:
            value = _json_value_after_key(str_head, str_key)
        if value is not _CACHE_METADATA_MISSING:
            dict_metadata[str_key] = value
    return dict_metadata


def _marker_cache_needs_refresh(str_full_path: str, str_model: str, str_variant: str) -> bool:
    cache_path = _marker_cache_path(str_full_path, str_model, str_variant)
    if not cache_path:
        return False
    if not cache_path.exists():
        print(f"[auto_ai] missing cache queued for inference: {cache_path.name}")
        return True

    dict_expected_runtime = _expected_marker_model_runtime(str_model, str_variant)
    try:
        stat = cache_path.stat()
        tuple_runtime_state = tuple(sorted((dict_expected_runtime or {}).items()))
        tuple_cache_state = (stat.st_mtime_ns, stat.st_size, tuple_runtime_state)
        tuple_cache_key = (str(cache_path), str_model, str_variant)
        tuple_cached_quality = _marker_cache_quality_cache.get(tuple_cache_key)
        if tuple_cached_quality and tuple_cached_quality[:-1] == tuple_cache_state:
            return bool(tuple_cached_quality[-1])
    except Exception:
        tuple_cache_state = None
        tuple_cache_key = None

    dict_cached_metadata = _read_marker_cache_metadata(cache_path)
    if dict_cached_metadata is None:
        print(f"[auto_ai] unreadable cache metadata queued for refresh: {cache_path.name}")
        bool_needs_refresh = True
        if tuple_cache_state and tuple_cache_key:
            _marker_cache_quality_cache[tuple_cache_key] = (*tuple_cache_state, bool_needs_refresh)
        return bool_needs_refresh

    bool_needs_refresh = False
    if dict_expected_runtime is not None:
        if dict_cached_metadata.get("model_runtime") != dict_expected_runtime:
            print(f"[auto_ai] stale cache model architecture or weights queued for refresh: {cache_path.name}")
            bool_needs_refresh = True
            if tuple_cache_state and tuple_cache_key:
                _marker_cache_quality_cache[tuple_cache_key] = (*tuple_cache_state, bool_needs_refresh)
            return bool_needs_refresh

    if not cache_has_current_detection_postprocess(dict_cached_metadata):
        print(f"[auto_ai] stale cache resolution or detection post-processing queued for refresh: {cache_path.name}")
        bool_needs_refresh = True
        if tuple_cache_state and tuple_cache_key:
            _marker_cache_quality_cache[tuple_cache_key] = (*tuple_cache_state, bool_needs_refresh)
        return bool_needs_refresh

    if _marker_cache_requires_excluded_cells(str_model, str_variant):
        dict_expected_processing = processing_metadata()
        for str_key in (
            "excluded_class_suppression_iou_threshold",
            "excluded_class_suppression_rule",
        ):
            if dict_cached_metadata.get(str_key) != dict_expected_processing.get(str_key):
                print(f"[auto_ai] stale cache missing excluded-cell metadata queued for refresh: {cache_path.name}")
                bool_needs_refresh = True
                if tuple_cache_state and tuple_cache_key:
                    _marker_cache_quality_cache[tuple_cache_key] = (*tuple_cache_state, bool_needs_refresh)
                return bool_needs_refresh

    if dict_cached_metadata.get("has_cells") and not _cell_has_bbox(dict_cached_metadata.get("first_cell")):
        print(f"[auto_ai] stale cache missing bbox queued for refresh: {cache_path.name}")
        bool_needs_refresh = True

    if tuple_cache_state and tuple_cache_key:
        _marker_cache_quality_cache[tuple_cache_key] = (*tuple_cache_state, bool_needs_refresh)
    return bool_needs_refresh


async def _stale_marker_cache_candidates(str_rel_path: str, str_model: str, str_variant: str) -> list:
    from app import slide_store

    if str_model not in ("Quanti HE", "HE-Fit", "Quanti PD-L1", "PD-Score", "Quanti IHC", "Precise-IHC"):
        return []

    dict_slides = await slide_store.list_slides_in_folder(str_rel_path)
    list_out = []
    for dict_slide in dict_slides.values():
        str_full_path = dict_slide.get("str_full_path") or ""
        if str_full_path and Path(str_full_path).exists() and _marker_cache_needs_refresh(str_full_path, str_model, str_variant):
            list_out.append(dict_slide)
    return list_out


def _merge_slide_candidates(*lists_candidates: list) -> list:
    dict_merged = {}
    for list_candidates in lists_candidates:
        for dict_slide in list_candidates or []:
            str_key = dict_slide.get("str_full_path") or dict_slide.get("str_filename") or str(id(dict_slide))
            dict_merged[str_key] = dict_slide
    return list(dict_merged.values())


async def _should_defer_slide_for_pending_tiles(dict_slide: dict) -> bool:
    """Defer only the current slide when its tiles are still queued."""
    from app.runtime_settings import get_worker_settings

    if not get_worker_settings().get("bool_tile_worker_enabled", True):
        return False
    return bool(dict_slide.get("bool_tiles_ready")) is not True


async def _should_yield_for_active_tile_generation() -> bool:
    from app.runtime_settings import get_worker_settings
    from app import tile_generator

    if not get_worker_settings().get("bool_tile_worker_enabled", True):
        return False
    return tile_generator.any_generation_running()


def _annotation_project_configs(dict_project: dict, set_paths: set) -> list:
    from app.project_utils import normalize_annotation_ai_config

    dict_config = normalize_annotation_ai_config(
        bool(dict_project.get("bool_annotation_ai_enabled")),
        dict_project.get("str_annotation_ai_key", ""),
    )
    if not dict_config.get("enabled"):
        return []
    return [{
        "str_rel_path": str_path,
        "bool_enabled": True,
        "list_tasks": [{
            "model": dict_config["base_model"],
            "variant": dict_config["variant"],
            "annotation_ai": dict_config,
            "source": "cell_annotation_ai_assistance",
        }],
    } for str_path in sorted(set_paths)]


_assistance_file_checks: dict = {}


def _assistance_needs_refresh(str_full_path: str, dict_config: dict) -> bool:
    """Check the assistance artifact without deleting or rewriting user data."""
    from app.config import settings
    from app.routers.cell_annotation import _expected_assistance_confidence_threshold

    path = Path(settings.CELL_ANNOTATION_DIR) / slide_cache_key(str_full_path) / "WSI_Labeling_assistance.json"
    try:
        stat = path.stat()
        expected_threshold = _expected_assistance_confidence_threshold(dict_config)
        state = (stat.st_mtime_ns, stat.st_size, dict_config["key"], expected_threshold,
                 tuple(sorted(processing_metadata().items())))
        cached = _assistance_file_checks.get(str(path))
        if cached and cached[0] == state:
            missing = cached[1]
        else:
            payload = json.loads(path.read_text(encoding="utf-8"))
            missing = (
                payload.get("annotation_ai", {}).get("key") != dict_config["key"]
                or not cache_has_current_detection_postprocess(payload.get("source_ai_postprocess"))
                or not isinstance(payload.get("labels"), list)
            )
            if expected_threshold is not None:
                try:
                    missing |= abs(float(payload.get("assistance_confidence_threshold")) - expected_threshold) >= 1e-6
                except (ValueError, TypeError):
                    missing = True
            _assistance_file_checks[str(path)] = (state, missing)
        return missing or _marker_cache_needs_refresh(
            str_full_path, dict_config["base_model"], dict_config["variant"]
        )
    except (OSError, ValueError, TypeError, AttributeError):
        return True


async def _scan_and_infer_once() -> None:
    """1 text — text text folder config text text text text text text.

    text text:
      - text hit text text text text
      - text text text text inferring/done text
      - text text(text text) text 1 text text (text text text text)
    """
    from app.database import is_db_connected, get_db
    from app import slide_store

    if not is_db_connected():
        return
    if not is_system_idle():
        return

    if await _should_yield_for_active_tile_generation():
        print("[auto_ai] tile generation active — yielding AI inference")
        return

    int_repaired = await slide_store.repair_folder_ai_config_paths()
    if int_repaired:
        print(f"[auto_ai] repaired {int_repaired} folder AI config path(s)")

    db = get_db()
    list_configs = []
    set_explicit_paths = set()
    async for dict_cfg in db.folder_ai_configs.find({}):
        str_cfg_path = (dict_cfg.get("str_rel_path") or "").replace("\\", "/").strip("/")
        set_explicit_paths.add(str_cfg_path)
        if dict_cfg.get("bool_enabled"):
            list_configs.append(dict_cfg)

    async for dict_project in db.project_infos.find({
        "$or": [
            {"bool_project_ai_enabled": True},
            {"bool_annotation_ai_enabled": True},
        ],
    }):
        str_project_path = (dict_project.get("str_project_path") or "").replace("\\", "/").strip("/")
        list_tasks = []
        if dict_project.get("bool_project_ai_enabled"):
            list_tasks.extend(dict_project.get("list_project_ai_tasks") or [])
        dict_unique_tasks = {}
        for dict_task in list_tasks:
            str_model_key = dict_task.get("model") or ""
            str_variant_key = dict_task.get("variant") or ""
            if str_model_key and str_variant_key:
                dict_unique_tasks[(str_model_key, str_variant_key)] = dict_task
        list_tasks = list(dict_unique_tasks.values())
        if not str_project_path:
            continue

        set_project_paths = set()
        set_inherited_paths = set()
        str_project_regex = f"^{re.escape(str_project_path)}(/|$)"
        async for dict_slide in db.slides.find(
            {"str_rel_path": {"$regex": str_project_regex}},
            {"str_rel_path": 1},
        ):
            str_slide_path = (dict_slide.get("str_rel_path") or "").replace("\\", "/").strip("/")
            if str_slide_path:
                set_project_paths.add(str_slide_path)
                if str_slide_path not in set_explicit_paths:
                    set_inherited_paths.add(str_slide_path)

        # Annotation assistance is a separate project option. Folder scoring
        # overrides must not discard it, and it needs its own saved output.
        list_configs.extend(_annotation_project_configs(dict_project, set_project_paths))

        for str_rel_path in sorted(set_inherited_paths):
            list_configs.append({
                "str_rel_path": str_rel_path,
                "bool_enabled": True,
                "list_tasks": list_tasks,
                "str_inherited_from_project": str_project_path,
            })

    int_scanned = 0    # text text text text text (text hit + text + text text)
    int_inferred = 0   # text text text text text
    int_tile_deferred = 0
    int_marker_candidates = 0
    int_vs_candidates = 0
    int_vs_cache_hits = 0
    int_missing_file = 0

    for dict_cfg in list_configs:
        str_rel_path = dict_cfg.get("str_rel_path", "")
        list_tasks = dict_cfg.get("list_tasks") or []
        if not list_tasks:
            continue

        # task text "text text"text DB text text text → text text text X
        for dict_task in list_tasks:
            str_model = dict_task.get("model") or ""
            str_variant = dict_task.get("variant") or ""
            if not str_model or not str_variant:
                continue

            dict_annotation_ai = dict_task.get("annotation_ai")
            float_target_mpp = 2.0
            if dict_annotation_ai:
                dict_slides = await slide_store.list_slides_in_folder(str_rel_path)
                list_candidates = []
                for dict_slide in dict_slides.values():
                    str_full_path = dict_slide.get("str_full_path") or ""
                    if not str_full_path or not Path(str_full_path).exists():
                        int_missing_file += 1
                        continue
                    if await asyncio.to_thread(
                        _assistance_needs_refresh, str_full_path, dict_annotation_ai
                    ):
                        list_candidates.append(dict_slide)
            elif str_model in ("VS IHC", "VS-IHC"):
                try:
                    float_target_mpp = float(dict_task.get("target_mpp", 2.0))
                except (TypeError, ValueError):
                    float_target_mpp = 2.0
                # VS IHC is tracked by per-mpp cache files, so build candidates
                # only for slides that actually need generation.
                dict_slides = await slide_store.list_slides_in_folder(str_rel_path)
                list_candidates = []
                for dict_slide in dict_slides.values():
                    str_full_path = dict_slide.get("str_full_path") or ""
                    if not str_full_path or not Path(str_full_path).exists():
                        int_missing_file += 1
                        continue
                    if await asyncio.to_thread(_vs_cache_exists, str_full_path, float_target_mpp):
                        int_vs_cache_hits += 1
                        continue
                    list_candidates.append(dict_slide)
            else:
                list_missing_candidates = await slide_store.list_slides_missing_variant(
                    str_rel_path, str_model, str_variant
                )
                list_stale_candidates = []
                # Architecture-tracked IHC tasks must always inspect cache
                # identity, even when the optional broad stale-cache scan is
                # disabled. This lets the worker migrate flat caches to the
                # configured hierarchical checkpoint automatically.
                if SCAN_STALE_CACHES or _expected_marker_model_runtime(str_model, str_variant) is not None:
                    list_stale_candidates = await _stale_marker_cache_candidates(
                        str_rel_path, str_model, str_variant
                    )
                list_candidates = _merge_slide_candidates(list_missing_candidates, list_stale_candidates)

            for dict_slide in list_candidates:
                str_full_path = dict_slide.get("str_full_path") or ""
                if not str_full_path or not Path(str_full_path).exists():
                    int_missing_file += 1
                    continue

                int_scanned += 1
                if str_model in ("VS IHC", "VS-IHC"):
                    int_vs_candidates += 1
                else:
                    int_marker_candidates += 1

                if str_model in ("VS IHC", "VS-IHC") and await asyncio.to_thread(_vs_cache_exists, str_full_path, float_target_mpp):
                    # text text → text text (text X)
                    int_vs_cache_hits += 1
                    continue

                # text text text idle text — text text / text text text
                if not is_system_idle():
                    if int_inferred > 0:
                        print(f"[auto_ai] activity detected — paused after {int_inferred}/{int_scanned} inferred")
                    return
                if await _should_yield_for_active_tile_generation():
                    if int_inferred > 0:
                        print(f"[auto_ai] tile generation active — yielded after {int_inferred}/{int_scanned} inferred")
                    return
                if await _should_defer_slide_for_pending_tiles(dict_slide):
                    int_tile_deferred += 1
                    continue

                try:
                    if dict_annotation_ai:
                        await _run_auto_inference(
                            str_full_path, str_model, str_variant, float_target_mpp,
                            dict_annotation_ai=dict_annotation_ai,
                        )
                    else:
                        await _run_auto_inference(str_full_path, str_model, str_variant, float_target_mpp)
                    int_inferred += 1
                except Exception as e:
                    print(f"[auto_ai] inference error: {e}")

                # DB text text (mark_ai_result_threadsafe text text text text)
                await asyncio.sleep(0.5)

    # text text text — text text text text. text text 0/N text text text.
    if int_inferred > 0:
        print(f"[auto_ai] cycle done — {int_inferred}/{int_scanned} inferred")
    elif int_tile_deferred > 0:
        print(f"[auto_ai] tile generation pending for {int_tile_deferred}/{int_scanned} candidate(s) — skipped this cycle")
    elif int_scanned > 0:
        _log_throttled(
            "scan_summary",
            f"[auto_ai] cycle scanned {int_scanned} candidate(s), no inference needed "
            f"(marker={int_marker_candidates}, vs={int_vs_candidates}, "
            f"vs_cache_hit={int_vs_cache_hits}, missing_file={int_missing_file})",
            SCAN_SUMMARY_LOG_INTERVAL_SECONDS,
        )
    else:
        _log_throttled(
            "scan_summary",
            f"[auto_ai] cycle scanned 0 candidate(s) across {len(list_configs)} config(s) "
            f"(vs_cache_hit={int_vs_cache_hits}, missing_file={int_missing_file})",
            SCAN_SUMMARY_LOG_INTERVAL_SECONDS,
        )


async def _worker_loop() -> None:
    """text text text — text text text text text."""
    print(f"[auto_ai] worker loop started (scan every {SCAN_INTERVAL_SECONDS}s, idle threshold {IDLE_THRESHOLD_SECONDS}s)")
    await asyncio.sleep(STARTUP_SCAN_DELAY_SECONDS)
    while True:
        try:
            await _scan_and_infer_once()
            await asyncio.sleep(SCAN_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            print("[auto_ai] worker cancelled")
            raise
        except Exception as e:
            import traceback
            print(f"[auto_ai] worker loop error: {e}\n{traceback.format_exc()}")


async def start_auto_worker() -> None:
    global _worker_task
    if _worker_task is not None:
        return
    _worker_task = asyncio.create_task(_worker_loop())


async def stop_auto_worker() -> None:
    global _worker_task
    if _worker_task is None:
        return
    _worker_task.cancel()
    try:
        await _worker_task
    except asyncio.CancelledError:
        pass
    _worker_task = None
    print("[auto_ai] worker stopped")


def is_auto_worker_running() -> bool:
    return _worker_task is not None and not _worker_task.done()
