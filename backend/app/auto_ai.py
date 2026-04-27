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


def _is_activity_idle_nolock() -> bool:
    """_activity_lock 이 이미 잡힌 상태에서만 호출 — 업로드/사용자활동 조건만 검사."""
    if _upload_in_progress > 0:
        return False
    if (time.monotonic() - _last_ai_activity_ts) < IDLE_THRESHOLD_SECONDS:
        return False
    return True


def is_system_idle() -> bool:
    """시스템이 자동 추론을 시작해도 되는지 판단 (비원자적 pre-check).

    조건 (모두 만족해야 idle):
      1. 진행 중인 업로드 없음
      2. 마지막 사용자 AI 활동 이후 IDLE_THRESHOLD_SECONDS 경과
      3. 현재 실행 중(queued/running) 인 AI task 없음

    주의: 이 함수는 스냅샷 체크일 뿐, 체크와 실제 task 등록 사이에 사용자 task 가
    끼어들 수 있다. 실제 reservation 은 check_idle_and_reserve() 로 원자적으로 수행.
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
    """원자적 "idle 확인 + task slot 예약".

    _tasks_lock 과 _activity_lock 을 동시에 잡은 상태에서 모든 idle 조건을 검사하고
    성공 시 즉시 _tasks 에 예약 레코드를 삽입한다. 이렇게 해야 사용자 엔드포인트가
    같은 _tasks_lock 으로 task 를 insert 하기 전/후로 race 가 발생하지 않는다.

    Lock 순서: _tasks_lock → _activity_lock (사용자 경로는 _tasks_lock 만 잡으므로
    데드락 위험 없음; _activity_lock 쪽에서 _tasks_lock 을 역순으로 잡는 경로가
    존재하지 않는다).
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
    # 원자적 idle 재확인 + 예약. 사용자 task 가 끼어들었으면 이 사이클 즉시 abort.
    if not check_idle_and_reserve(str_task_id, dict_initial):
        print(f"[auto_ai] reserve aborted (activity detected) — skip {str_filename}")
        return

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


def _vs_cache_exists(str_full_path: str, float_target_mpp: float) -> bool:
    """_run_virtual_stain 의 캐시 hit 조건과 동일 — meta.json + (level-0 타일 OR 레거시 PNG).

    auto_ai 가 사이클마다 슬라이드를 검사할 때 이 조건을 미리 보고 hit 면 스킵해야
    "inferring/done" 로그가 캐시 검증 때문에 매번 찍히는 것을 방지한다.
    """
    from app.routers.ai import _get_vs_cache_paths, _get_vs_tile_dir
    png_path, meta_path = _get_vs_cache_paths(str_full_path, float_target_mpp)
    if not meta_path.exists():
        return False
    path_lvl0 = _get_vs_tile_dir(str_full_path, float_target_mpp) / '0'
    bool_tiles_ok = path_lvl0.exists() and any(path_lvl0.glob('*.jpeg'))
    bool_png_legacy = png_path.exists()
    return bool_tiles_ok or bool_png_legacy


async def _scan_and_infer_once() -> None:
    """1 사이클 — 모든 활성 folder config 를 돌며 누락된 추론을 순차 수행.

    조용한 정책:
      - 캐시 hit 슬라이드는 로그 없이 스킵
      - 실제 추론이 발생한 슬라이드만 inferring/done 로그
      - 사이클 끝(또는 중단) 시 1 줄 요약 (실제 추론이 있었던 경우만)
    """
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

    int_scanned = 0    # 이번 사이클에 검사한 슬라이드 수 (캐시 hit + 추론 + 스킵 포함)
    int_inferred = 0   # 실제로 추론을 돌린 슬라이드 수

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

                int_scanned += 1

                if str_model == "VS-IHC" and _vs_cache_exists(str_full_path, float_target_mpp):
                    # 캐시 있음 → 조용히 스킵 (로그 X)
                    continue

                # 매 추론 전 idle 재확인 — 사용자 활동 / 업로드 끼어들면 중단
                if not is_system_idle():
                    if int_inferred > 0:
                        print(f"[auto_ai] activity detected — paused after {int_inferred}/{int_scanned} inferred")
                    return
                # 새로 업로드된 슬라이드 타일링이 끼어들면 양보
                if await slide_store.has_any_pending_tiles():
                    if int_inferred > 0:
                        print(f"[auto_ai] new tile job — yielded after {int_inferred}/{int_scanned} inferred")
                    return

                try:
                    await _run_auto_inference(str_full_path, str_model, str_variant, float_target_mpp)
                    int_inferred += 1
                except Exception as e:
                    print(f"[auto_ai] inference error: {e}")

                # DB 갱신 대기 (mark_ai_result_threadsafe 는 다른 루프에 스케줄)
                await asyncio.sleep(0.5)

    # 사이클 종료 요약 — 실제 추론이 발생했을 때만. 매 분 0/N 로그를 띄우지 않음.
    if int_inferred > 0:
        print(f"[auto_ai] cycle done — {int_inferred}/{int_scanned} inferred")


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
