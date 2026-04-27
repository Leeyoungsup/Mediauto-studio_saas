"""AI 워커 작업 상태 관리 — 진행률, 취소 플래그, 캐시 cleanup.

routers/ai.py 의 모든 백그라운드 워커(_run_detection, _run_pd_score,
_run_precise_ihc, _run_virtual_stain) 와 라우트 핸들러가 이 모듈을 통해
공유 상태 dict 에 접근한다.

설계 메모:
- _tasks 는 프로세스 메모리에 사는 단일 dict — On-Premise 단일 프로세스 전제.
- threading.Lock 으로 워커 스레드와 라우트 핸들러 간 동시 접근 직렬화.
- _update_task 는 사용자 트리거 task 일 때만 auto_ai 의 idle 타이머를 reset
  (auto_ 접두어 task 는 자동 추론이라 카운트하지 않는다).
"""

import shutil
import threading
from pathlib import Path

# {task_id: {status, progress, status_msg, result, error, cancel_requested, ...}}
_tasks: dict = {}
_tasks_lock = threading.Lock()


class TaskCancelled(Exception):
    """사용자가 추론을 중단 요청했을 때 워커가 raise 하는 예외."""
    pass


def get_tasks() -> dict:
    """라우트 핸들러용 — _tasks dict 직접 접근. lock 은 호출자 책임."""
    return _tasks


def get_lock() -> threading.Lock:
    """라우트 핸들러용 — _tasks_lock 직접 접근."""
    return _tasks_lock


def update_task(task_id: str, **kwargs) -> None:
    """워커 진행 상황 갱신. 사용자 task 면 auto_ai idle 타이머도 ping."""
    with _tasks_lock:
        if task_id in _tasks:
            _tasks[task_id].update(kwargs)
    if not task_id.startswith("auto_"):
        try:
            from app import auto_ai
            auto_ai.ping_ai_activity()
        except Exception:
            pass


def is_cancel_requested(task_id: str) -> bool:
    with _tasks_lock:
        task = _tasks.get(task_id)
        return bool(task and task.get("cancel_requested"))


def check_cancel(task_id: str) -> None:
    """체크포인트 — 취소 요청이 있으면 TaskCancelled 발생."""
    if is_cancel_requested(task_id):
        raise TaskCancelled()


def cleanup_cache_paths(list_paths) -> None:
    """취소 시 부분 저장된 캐시 파일/폴더 전부 삭제. 충돌 방지용."""
    for p in list_paths:
        if p is None:
            continue
        try:
            path_obj = Path(p)
            if path_obj.is_file():
                path_obj.unlink()
                print(f"[cancel] removed file: {path_obj}")
            elif path_obj.is_dir():
                shutil.rmtree(path_obj)
                print(f"[cancel] removed dir: {path_obj}")
        except Exception as e:
            print(f"[cancel] cleanup failed for {p}: {e}")
