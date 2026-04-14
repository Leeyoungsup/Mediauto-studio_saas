"""AI 자동 추론 워커 — 폴더별 설정 기반 백그라운드 스케줄러

정책:
- 1분마다 `folder_ai_configs` 를 스캔 (SCAN_INTERVAL_SECONDS)
- 시스템이 idle 일 때만 실행 (IDLE_THRESHOLD_SECONDS 동안 사용자 AI 활동 없음)
- 업로드 중일 때는 실행하지 않음 (upload counter 로 확인)
- 슬라이드마다 결과 유무를 확인 후 누락된 (model, variant) 만 추론
- 한 슬라이드 처리 후 다시 idle 확인 — 사용자가 끼어들면 이번 사이클 중단

Claude.md 규칙 준수 (str_/int_/bool_/list_/dict_/dt_ 접두어).
"""

import asyncio
import hashlib
import threading
import time
import uuid
from pathlib import Path
from typing import Optional


# ── 설정 상수 ──
IDLE_THRESHOLD_SECONDS = 600   # 10분간 사용자 AI 활동 없음 → idle
SCAN_INTERVAL_SECONDS = 60     # 1분마다 스캔

# ── 전역 활동 추적 상태 ──
_activity_lock = threading.Lock()
_last_ai_activity_ts: float = 0.0   # 0 → "idle" 로 간주되지 않도록 startup 직후 now 로 세팅됨
_upload_in_progress: int = 0
_worker_task: Optional[asyncio.Task] = None


# ═══════════════════════════
# 활동 추적 API
# ═══════════════════════════

def ping_ai_activity() -> None:
    """사용자 AI 엔드포인트 호출 / 진행 업데이트 시 호출 — idle 타이머 리셋."""
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


def is_system_idle() -> bool:
    """시스템이 자동 추론을 시작해도 되는지 판단.

    조건 (모두 만족해야 idle):
      1. 진행 중인 업로드 없음
      2. 마지막 사용자 AI 활동 이후 IDLE_THRESHOLD_SECONDS 경과
      3. 현재 실행 중(queued/running) 인 AI task 없음
    """
    with _activity_lock:
        if _upload_in_progress > 0:
            return False
        if (time.monotonic() - _last_ai_activity_ts) < IDLE_THRESHOLD_SECONDS:
            return False

    # 실행 중 task 확인 (ai 라우터 import 는 순환 방지 위해 지연)
    try:
        from app.routers import ai as ai_router
        with ai_router._tasks_lock:
            for dict_task in ai_router._tasks.values():
                if dict_task.get("status") in ("queued", "running"):
                    return False
    except Exception:
        pass

    return True


# ═══════════════════════════
# 워커 로직
# ═══════════════════════════

async def _run_auto_inference(
    str_full_path: str,
    str_model: str,
    str_variant: str,
    float_target_mpp: float = 2.0,
) -> None:
    """한 슬라이드/모델/variant 에 대한 추론을 스레드풀에서 실행."""
    from app.slide_manager import slide_manager
    from app.routers import ai as ai_router

    str_filename = Path(str_full_path).name
    str_slide_id = hashlib.md5(str_filename.encode()).hexdigest()[:12]

    # slide_manager 에 없으면 open (기존 _open_and_generate 와 동일 로직의 subset)
    if slide_manager.get(str_slide_id) is None:
        try:
            slide_manager.open(str_slide_id, str_full_path)
        except Exception as e:
            print(f"[auto_ai] open failed {str_filename}: {e}")
            return

    str_task_id = f"auto_{uuid.uuid4().hex[:10]}"
    with ai_router._tasks_lock:
        ai_router._tasks[str_task_id] = {
            "status": "queued",
            "progress": 0,
            "result": None,
            "error": None,
            "status_msg": "",
            "slide_filename": str_filename,
            "model": str_model,
            "variant": str_variant,
        }

    def _dispatch() -> None:
        if str_model == "HE-Fit":
            ai_router._run_detection(str_task_id, str_slide_id, None, str_variant)
        elif str_model == "PD-Score":
            ai_router._run_pd_score(str_task_id, str_slide_id, None, str_variant)
        elif str_model == "Precise-IHC":
            ai_router._run_precise_ihc(str_task_id, str_slide_id, None, str_variant)
        elif str_model == "VS-IHC":
            # variant = stain_type (e.g. "ihc_membrane"), target_mpp 는 task 설정값
            ai_router._run_virtual_stain(str_task_id, str_slide_id, None, str_variant, float_target_mpp)
        else:
            print(f"[auto_ai] unsupported model: {str_model}")

    print(f"[auto_ai] inferring {str_model}/{str_variant} on {str_filename}")
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _dispatch)
    print(f"[auto_ai] done {str_model}/{str_variant} on {str_filename}")


async def _scan_and_infer_once() -> None:
    """1 사이클 — 모든 활성 folder config 를 돌며 누락된 추론을 순차 수행."""
    from app.database import is_db_connected, get_db
    from app import slide_store

    if not is_db_connected():
        return
    if not is_system_idle():
        return

    # 뷰어 타일링이 우선 — 미완료 슬라이드가 있으면 이번 사이클 skip
    if await slide_store.has_any_pending_tiles():
        print("[auto_ai] tile generation pending — deferring AI inference")
        return

    db = get_db()
    list_configs = []
    async for dict_cfg in db.folder_ai_configs.find({"bool_enabled": True}):
        list_configs.append(dict_cfg)

    for dict_cfg in list_configs:
        str_rel_path = dict_cfg.get("str_rel_path", "")
        list_tasks = dict_cfg.get("list_tasks") or []
        if not list_tasks:
            continue

        # task 단위로 "누락된 슬라이드"를 DB 에 직접 질의 → 폴더 전체 순회 X
        for dict_task in list_tasks:
            str_model = dict_task.get("model") or ""
            str_variant = dict_task.get("variant") or ""
            if not str_model or not str_variant:
                continue

            float_target_mpp = 2.0
            if str_model == "VS-IHC":
                try:
                    float_target_mpp = float(dict_task.get("target_mpp", 2.0))
                except (TypeError, ValueError):
                    float_target_mpp = 2.0
                # VS-IHC 는 per-mpp 캐시라 DB 로 base 필터만 하고 폴더 전체를 후보로 봄
                dict_slides = await slide_store.list_slides_in_folder(str_rel_path)
                list_candidates = list(dict_slides.values())
            else:
                list_candidates = await slide_store.list_slides_missing_variant(
                    str_rel_path, str_model, str_variant
                )

            for dict_slide in list_candidates:
                str_full_path = dict_slide.get("str_full_path") or ""
                if not str_full_path or not Path(str_full_path).exists():
                    continue

                if str_model == "VS-IHC":
                    from app.routers.ai import _get_vs_cache_paths
                    png_path, _ = _get_vs_cache_paths(str_full_path, str_variant, float_target_mpp)
                    if png_path.exists():
                        continue

                # 매 추론 전 idle 재확인 — 사용자 활동 / 업로드 끼어들면 중단
                if not is_system_idle():
                    print("[auto_ai] activity detected — pausing cycle")
                    return
                # 새로 업로드된 슬라이드 타일링이 끼어들면 양보
                if await slide_store.has_any_pending_tiles():
                    print("[auto_ai] new tile job pending — yielding cycle")
                    return

                try:
                    await _run_auto_inference(str_full_path, str_model, str_variant, float_target_mpp)
                except Exception as e:
                    print(f"[auto_ai] inference error: {e}")

                # DB 갱신 대기 (mark_ai_result_threadsafe 는 다른 루프에 스케줄)
                await asyncio.sleep(0.5)


async def _worker_loop() -> None:
    """메인 워커 루프 — 앱 생명주기 동안 계속 돔."""
    # 스타트업 직후 바로 돌지 않도록 timer 초기화
    ping_ai_activity()
    print(f"[auto_ai] worker loop started (scan every {SCAN_INTERVAL_SECONDS}s, idle threshold {IDLE_THRESHOLD_SECONDS}s)")
    while True:
        try:
            await asyncio.sleep(SCAN_INTERVAL_SECONDS)
            await _scan_and_infer_once()
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
