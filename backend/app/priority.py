"""
뷰어 타일 요청 우선순위 게이팅.

뷰어가 타일을 요청하는 순간 타임스탬프를 갱신하고, AI 추론 워커는
`wait_if_viewer_busy()` 로 잠시 양보해 디스크/CPU/GIL 경쟁을 완화한다.
"""
import time
import threading

VIEWER_GRACE_SEC = 1.2
AI_YIELD_POLL_SEC = 0.04
AI_YIELD_MAX_WAIT_SEC = 3.0

_last_viewer_activity = 0.0
_lock = threading.Lock()


def notify_viewer_activity() -> None:
    global _last_viewer_activity
    with _lock:
        _last_viewer_activity = time.monotonic()


def viewer_busy() -> bool:
    return (time.monotonic() - _last_viewer_activity) < VIEWER_GRACE_SEC


def wait_if_viewer_busy(max_wait: float = AI_YIELD_MAX_WAIT_SEC) -> None:
    if not viewer_busy():
        return
    int_deadline = time.monotonic() + max_wait
    while viewer_busy() and time.monotonic() < int_deadline:
        time.sleep(AI_YIELD_POLL_SEC)
