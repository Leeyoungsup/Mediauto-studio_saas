"""
text text text text text.

text text text text text text, AI text text
`wait_if_viewer_busy()` text text text text/CPU/GIL text text.
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
    return viewer_recent(VIEWER_GRACE_SEC)


def seconds_since_viewer_activity() -> float:
    with _lock:
        last = _last_viewer_activity
    if last <= 0:
        return float("inf")
    return time.monotonic() - last


def viewer_recent(grace_sec: float = VIEWER_GRACE_SEC) -> bool:
    return seconds_since_viewer_activity() < float(grace_sec)


def wait_if_viewer_busy(max_wait: float = AI_YIELD_MAX_WAIT_SEC) -> None:
    if not viewer_busy():
        return
    int_deadline = time.monotonic() + max_wait
    while viewer_busy() and time.monotonic() < int_deadline:
        time.sleep(AI_YIELD_POLL_SEC)
