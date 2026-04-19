"""CPU 코어 파티셔닝 — viewer / AI / background tile_worker 분리.

시작 시 한 번 계산해 세 그룹의 CPU set 을 만들고, 각 그룹의
ThreadPoolExecutor 는 worker thread 시작 시 `os.sched_setaffinity` 로
자기 그룹에 핀닝된다.

핵심 트릭: **메인 프로세스 affinity 를 AI cores 로 설정**해 둔다.
- viewer / bg pool 은 initializer 로 자기 cores 를 override
- 그 외 모든 thread (uvicorn worker, AI 모듈의 raw threading.Thread 와
  중첩 ThreadPoolExecutor) 는 자동으로 AI cores 를 상속받음.

동적 분배 공식 — 사용 가능 코어 수 N 기준 (사용자 체감 우선):
    ai     = max(2, round(N / 6))       ~17%
    bg     = max(2, round(N / 6))       ~17%  (AI와 독립, 비공유)
    viewer = N - ai - bg                ~67%  (타일 서빙 + HTTP 처리)

예시:
    N=48 → viewer=32 / ai=8  / bg=8
    N=24 → viewer=16 / ai=4  / bg=4
    N=16 → viewer=10 / ai=3  / bg=3
    N=12 → viewer=8  / ai=2  / bg=2
    N=8  → viewer=4  / ai=2  / bg=2

기존 대비 변경점:
- bg 가 ai 의 부분집합이 아닌 **독립 코어 그룹**. 4명 동시 슬라이드
  열기 시 타일 프리젠과 AI 추론이 서로 간섭하지 않음.
- viewer 비율 유지(~67%)하되 남은 1/3 을 ai/bg 균등 분배.

Linux 만 지원 (`os.sched_setaffinity`). 다른 OS 면 핀닝은 noop 으로
fallback 하고 worker count 만 적용.
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

# ── 분배 공식: 사용자 체감 우선 ──
# ai/bg 각 ~17%, viewer 나머지 ~67%
# bg는 ai와 독립 — 타일 프리젠과 AI 추론이 간섭하지 않음
INT_AI: int = max(2, round(INT_TOTAL / 6))
INT_BG: int = max(2, round(INT_TOTAL / 6))
INT_VIEWER: int = max(2, INT_TOTAL - INT_AI - INT_BG)

# 코어 배치: [viewer | bg | ai] — 인접 슬라이스로 NUMA/cache 친화
list_viewer_cpus: List[int] = list_all_cpus[:INT_VIEWER]
list_bg_cpus: List[int] = list_all_cpus[INT_VIEWER:INT_VIEWER + INT_BG]
list_ai_cpus: List[int] = list_all_cpus[INT_VIEWER + INT_BG:]

# 실제 할당된 개수로 보정 (반올림 오차 방지)
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
    """프로세스 (메인 thread) affinity 를 AI cores 로 설정.

    이후 생성되는 모든 thread 는 명시적 override 가 없는 한 이 set 을 상속.
    """
    _pin_to(frozenset_ai_cpus)
    print(
        f"[cpu_layout] total={INT_TOTAL} "
        f"viewer={INT_VIEWER}({sorted(list_viewer_cpus)}) "
        f"bg={INT_BG}({sorted(list_bg_cpus)}) "
        f"ai={INT_AI}({sorted(list_ai_cpus)})"
    )


# 전용 executor 들 — 모듈 import 시 1회 생성
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
