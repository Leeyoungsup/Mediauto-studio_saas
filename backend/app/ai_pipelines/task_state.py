"""Shared AI task state for background analysis workers.

The API routes create task records here and the worker threads update them.
Large completed results are kept only until the client downloads them, because
the same payload is also persisted in the AI result cache on disk.
"""

import gc
import shutil
import threading
import time
from pathlib import Path

# {task_id: {status, progress, status_msg, result, error, cancel_requested, ...}}
_tasks: dict = {}
_tasks_lock = threading.Lock()

_FINISHED_TASK_TTL_SECONDS = 60 * 60
_TASK_CLEANUP_INTERVAL_SECONDS = 60
_last_task_cleanup_ts = 0.0


class TaskCancelled(Exception):
    """Raised by workers when a user requests task cancellation."""


def get_tasks() -> dict:
    """Return the shared task dict. Callers are responsible for locking."""
    return _tasks


def get_lock() -> threading.Lock:
    """Return the shared task lock."""
    return _tasks_lock


def update_task(task_id: str, **kwargs) -> None:
    """Update a task and ping the auto-AI idle timer for user-triggered tasks."""
    float_now = time.time()
    with _tasks_lock:
        if task_id in _tasks:
            _tasks[task_id].setdefault("created_at", float_now)
            kwargs.setdefault("updated_at", float_now)
            _tasks[task_id].update(kwargs)
    cleanup_old_tasks()
    if not task_id.startswith("auto_"):
        try:
            from app import auto_ai
            auto_ai.ping_ai_activity()
        except Exception:
            pass


def release_task_result(task_id: str) -> bool:
    """Drop a completed task's large in-memory result after the client fetches it."""
    bool_released = False
    float_now = time.time()
    with _tasks_lock:
        task = _tasks.get(task_id)
        if task is not None and task.get("result") is not None:
            task["result"] = None
            task["result_released"] = True
            task["result_released_at"] = float_now
            task["updated_at"] = float_now
            bool_released = True
    if bool_released:
        gc.collect()
    return bool_released


def cleanup_old_tasks() -> None:
    """Remove finished task records so the global task dict cannot grow forever."""
    global _last_task_cleanup_ts
    float_now = time.time()
    if _last_task_cleanup_ts + _TASK_CLEANUP_INTERVAL_SECONDS > float_now:
        return
    _last_task_cleanup_ts = float_now

    list_drop = []
    with _tasks_lock:
        for str_task_id, dict_task in list(_tasks.items()):
            if dict_task.get("status") not in ("completed", "error", "cancelled"):
                continue
            float_updated = float(dict_task.get("updated_at") or dict_task.get("created_at") or float_now)
            if float_updated + _FINISHED_TASK_TTL_SECONDS <= float_now:
                list_drop.append(str_task_id)
        for str_task_id in list_drop:
            _tasks.pop(str_task_id, None)
    if list_drop:
        gc.collect()


def is_cancel_requested(task_id: str) -> bool:
    with _tasks_lock:
        task = _tasks.get(task_id)
        return bool(task and task.get("cancel_requested"))


def check_cancel(task_id: str) -> None:
    """Raise TaskCancelled when a task cancellation request is pending."""
    if is_cancel_requested(task_id):
        raise TaskCancelled()


def cleanup_cache_paths(list_paths) -> None:
    """Remove partially written cache files/directories after cancellation."""
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
