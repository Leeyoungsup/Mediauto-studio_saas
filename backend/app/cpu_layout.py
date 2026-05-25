"""CPU text text — viewer / AI / background tile_worker text.

text text text text text text text CPU set text text, text text
ThreadPoolExecutor text worker thread text text `os.sched_setaffinity` text
text text text.

text text: **text text affinity text AI cores text text**text text.
- viewer / bg pool text initializer text text cores text override
- text text text thread (uvicorn worker, AI text raw threading.Thread text
  text ThreadPoolExecutor) text text AI cores text text.

text text text — text text text text N text (text text text):
    ai     = max(2, round(N / 6))       ~17%
    bg     = max(2, round(N / 6))       ~17%  (AItext text, text)
    viewer = N - ai - bg                ~67%  (text text + HTTP text)

text:
    N=48 → viewer=32 / ai=8  / bg=8
    N=24 → viewer=16 / ai=4  / bg=4
    N=16 → viewer=10 / ai=3  / bg=3
    N=12 → viewer=8  / ai=2  / bg=2
    N=8  → viewer=4  / ai=2  / bg=2

text text text:
- bg text ai text text text **text text text**. 4text text text
  text text text text AI text text text text.
- viewer text text(~67%)text text 1/3 text ai/bg text text.

Linux text text (`os.sched_setaffinity`). text OS text text noop text
fallback text worker count text text.
"""

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import FrozenSet, List


def _has_affinity_api() -> bool:
    return sys.platform.startswith("linux") and hasattr(os, "sched_setaffinity")


def _initial_cpus() -> List[int]:
    if _has_affinity_api():
        try:
            return sorted(os.sched_getaffinity(0))
        except Exception:
            pass
    int_n = os.cpu_count() or 1
    return list(range(int_n))


list_all_cpus: List[int] = _initial_cpus()
INT_TOTAL: int = len(list_all_cpus)

# ── text text: text text text ──
# ai/bg text ~17%, viewer text ~67%
# bgtext aitext text — text text AI text text text
INT_AI: int = max(2, round(INT_TOTAL / 6))
INT_BG: int = max(2, round(INT_TOTAL / 6))
INT_VIEWER: int = max(2, INT_TOTAL - INT_AI - INT_BG)

# text text: [viewer | bg | ai] — text text NUMA/cache text
list_viewer_cpus: List[int] = list_all_cpus[:INT_VIEWER]
list_bg_cpus: List[int] = list_all_cpus[INT_VIEWER:INT_VIEWER + INT_BG]
list_ai_cpus: List[int] = list_all_cpus[INT_VIEWER + INT_BG:]

# text text text text (text text text)
INT_VIEWER = len(list_viewer_cpus)
INT_BG = len(list_bg_cpus)
INT_AI = len(list_ai_cpus)

frozenset_viewer_cpus: FrozenSet[int] = frozenset(list_viewer_cpus)
frozenset_ai_cpus: FrozenSet[int] = frozenset(list_ai_cpus)
frozenset_bg_cpus: FrozenSet[int] = frozenset(list_bg_cpus)


def _pin_to(set_cpus: FrozenSet[int]) -> None:
    if not _has_affinity_api():
        return
    try:
        os.sched_setaffinity(0, set_cpus)
    except Exception as e:
        print(f"[cpu_layout] pin failed: {e}")


def _make_initializer(set_cpus: FrozenSet[int]):
    def _init():
        _pin_to(set_cpus)
    return _init


def setup_process_affinity() -> None:
    """text (text thread) affinity text AI cores text text.

    text text text thread text text override text text text text set text text.
    """
    _pin_to(frozenset_ai_cpus)
    print(
        f"[cpu_layout] total={INT_TOTAL} "
        f"viewer={INT_VIEWER}({sorted(list_viewer_cpus)}) "
        f"bg={INT_BG}({sorted(list_bg_cpus)}) "
        f"ai={INT_AI}({sorted(list_ai_cpus)})"
    )


# text executor text — text import text 1text text
viewer_executor = ThreadPoolExecutor(
    max_workers=INT_VIEWER,
    thread_name_prefix="viewer",
    initializer=_make_initializer(frozenset_viewer_cpus),
)

bg_executor = ThreadPoolExecutor(
    max_workers=INT_BG,
    thread_name_prefix="tile_worker",
    initializer=_make_initializer(frozenset_bg_cpus),
)
