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
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from app.ai_pipelines.dedup import cache_has_current_detection_postprocess
from app.slide_identity import slide_cache_key


# ── text text ──
IDLE_THRESHOLD_SECONDS = 600   # 10text text AI text text → idle
SCAN_INTERVAL_SECONDS = 60     # 1text text
STARTUP_SCAN_DELAY_SECONDS = 5

# ── text text text text ──
_activity_lock = threading.Lock()
_last_ai_activity_ts: float = 0.0   # 0 → "idle" text text text startup text now text text
_upload_in_progress: int = 0
_worker_task: Optional[asyncio.Task] = None
_marker_cache_quality_cache: dict = {}


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
        if not _is_activity_idle_nolock():
            return False

    try:
        from app.routers import ai as ai_router
        with ai_router._tasks_lock:
            for dict_task in ai_router._tasks.values():
                if dict_task.get("status") in ("queued", "running"):
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
    }
    # text idle text + text. text task text text text text text abort.
    if not check_idle_and_reserve(str_task_id, dict_initial):
        print(f"[auto_ai] reserve aborted (activity detected) — skip {str_filename}")
        return

    def _dispatch() -> None:
        if str_model in ("Quanti HE", "HE-Fit"):
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
    print(f"[auto_ai] done {str_model}/{str_variant} on {str_filename}")


def _vs_cache_exists(str_full_path: str, float_target_mpp: float) -> bool:
    """_run_virtual_stain text text hit text text — meta.json + (level-0 text OR text PNG).

    auto_ai text text text text text text text text text hit text text
    "inferring/done" text text text text text text text text.
    """
    from app.routers.ai import _get_vs_cache_paths, _get_vs_tile_dir
    png_path, meta_path = _get_vs_cache_paths(str_full_path, float_target_mpp)
    if not meta_path.exists():
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


def _marker_cache_needs_refresh(str_full_path: str, str_model: str, str_variant: str) -> bool:
    cache_path = _marker_cache_path(str_full_path, str_model, str_variant)
    if not cache_path:
        return False
    if not cache_path.exists():
        print(f"[auto_ai] missing cache queued for inference: {cache_path.name}")
        return True

    try:
        stat = cache_path.stat()
        tuple_cache_state = (stat.st_mtime_ns, stat.st_size)
        tuple_cache_key = (str(cache_path), str_model, str_variant)
        tuple_cached_quality = _marker_cache_quality_cache.get(tuple_cache_key)
        if tuple_cached_quality and tuple_cached_quality[:2] == tuple_cache_state:
            return bool(tuple_cached_quality[2])
    except Exception:
        tuple_cache_state = None
        tuple_cache_key = None

    bool_needs_refresh = False
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
    except Exception as exc:
        print(f"[auto_ai] unreadable cache queued for refresh: {cache_path.name} ({exc})")
        bool_needs_refresh = True
        if tuple_cache_state and tuple_cache_key:
            _marker_cache_quality_cache[tuple_cache_key] = (*tuple_cache_state, bool_needs_refresh)
        return bool_needs_refresh

    if not isinstance(cached, dict):
        print(f"[auto_ai] invalid cache queued for refresh: {cache_path.name}")
        bool_needs_refresh = True
        if tuple_cache_state and tuple_cache_key:
            _marker_cache_quality_cache[tuple_cache_key] = (*tuple_cache_state, bool_needs_refresh)
        return bool_needs_refresh

    if not cache_has_current_detection_postprocess(cached):
        print(f"[auto_ai] stale cache missing 10um overlap/global dedup queued for refresh: {cache_path.name}")
        bool_needs_refresh = True
        if tuple_cache_state and tuple_cache_key:
            _marker_cache_quality_cache[tuple_cache_key] = (*tuple_cache_state, bool_needs_refresh)
        return bool_needs_refresh

    if _marker_cache_requires_excluded_cells(str_model, str_variant) and "excluded_cells" not in cached:
        print(f"[auto_ai] stale cache missing excluded cells queued for refresh: {cache_path.name}")
        bool_needs_refresh = True
        if tuple_cache_state and tuple_cache_key:
            _marker_cache_quality_cache[tuple_cache_key] = (*tuple_cache_state, bool_needs_refresh)
        return bool_needs_refresh

    cells = cached.get("cells")
    if isinstance(cells, list) and cells and not _cell_has_bbox(cells[0]):
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


async def _should_defer_for_pending_tiles() -> bool:
    """Defer auto AI only when the tile worker is expected to clear the queue."""
    from app.runtime_settings import get_worker_settings
    from app import slide_store

    if not get_worker_settings().get("bool_tile_worker_enabled", True):
        return False
    return await slide_store.has_any_pending_tiles()


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

    # text text text — text text text text text skip
    if await _should_defer_for_pending_tiles():
        print("[auto_ai] tile generation pending — deferring AI inference")
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
        if dict_project.get("bool_annotation_ai_enabled"):
            from app.project_utils import normalize_annotation_ai_config
            dict_annotation_ai = normalize_annotation_ai_config(
                True,
                dict_project.get("str_annotation_ai_key", ""),
            )
            if dict_annotation_ai.get("enabled"):
                list_tasks.append({
                    "model": dict_annotation_ai.get("base_model", ""),
                    "variant": dict_annotation_ai.get("variant", ""),
                    "source": "cell_annotation_ai_assistance",
                })
        dict_unique_tasks = {}
        for dict_task in list_tasks:
            str_model_key = dict_task.get("model") or ""
            str_variant_key = dict_task.get("variant") or ""
            if str_model_key and str_variant_key:
                dict_unique_tasks[(str_model_key, str_variant_key)] = dict_task
        list_tasks = list(dict_unique_tasks.values())
        if not str_project_path or not list_tasks:
            continue

        set_inherited_paths = set()
        str_project_regex = f"^{re.escape(str_project_path)}(/|$)"
        async for dict_slide in db.slides.find(
            {"str_rel_path": {"$regex": str_project_regex}},
            {"str_rel_path": 1},
        ):
            str_slide_path = (dict_slide.get("str_rel_path") or "").replace("\\", "/").strip("/")
            if str_slide_path and str_slide_path not in set_explicit_paths:
                set_inherited_paths.add(str_slide_path)

        for str_rel_path in sorted(set_inherited_paths):
            list_configs.append({
                "str_rel_path": str_rel_path,
                "bool_enabled": True,
                "list_tasks": list_tasks,
                "str_inherited_from_project": str_project_path,
            })

    int_scanned = 0    # text text text text text (text hit + text + text text)
    int_inferred = 0   # text text text text text

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

            float_target_mpp = 2.0
            if str_model in ("VS IHC", "VS-IHC"):
                try:
                    float_target_mpp = float(dict_task.get("target_mpp", 2.0))
                except (TypeError, ValueError):
                    float_target_mpp = 2.0
                # VS IHC text per-mpp text DB text base text text text text text text
                dict_slides = await slide_store.list_slides_in_folder(str_rel_path)
                list_candidates = list(dict_slides.values())
            else:
                list_missing_candidates = await slide_store.list_slides_missing_variant(
                    str_rel_path, str_model, str_variant
                )
                list_stale_candidates = await _stale_marker_cache_candidates(
                    str_rel_path, str_model, str_variant
                )
                list_candidates = _merge_slide_candidates(list_missing_candidates, list_stale_candidates)

            for dict_slide in list_candidates:
                str_full_path = dict_slide.get("str_full_path") or ""
                if not str_full_path or not Path(str_full_path).exists():
                    continue

                int_scanned += 1

                if str_model in ("VS IHC", "VS-IHC") and _vs_cache_exists(str_full_path, float_target_mpp):
                    # text text → text text (text X)
                    continue

                # text text text idle text — text text / text text text
                if not is_system_idle():
                    if int_inferred > 0:
                        print(f"[auto_ai] activity detected — paused after {int_inferred}/{int_scanned} inferred")
                    return
                # text text text text text text
                if await _should_defer_for_pending_tiles():
                    if int_inferred > 0:
                        print(f"[auto_ai] new tile job — yielded after {int_inferred}/{int_scanned} inferred")
                    return

                try:
                    await _run_auto_inference(str_full_path, str_model, str_variant, float_target_mpp)
                    int_inferred += 1
                except Exception as e:
                    print(f"[auto_ai] inference error: {e}")

                # DB text text (mark_ai_result_threadsafe text text text text)
                await asyncio.sleep(0.5)

    # text text text — text text text text. text text 0/N text text text.
    if int_inferred > 0:
        print(f"[auto_ai] cycle done — {int_inferred}/{int_scanned} inferred")


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
