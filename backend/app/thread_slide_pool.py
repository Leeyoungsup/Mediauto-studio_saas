"""Thread-local OpenSlide 핸들 풀 — 무효화/LRU 지원

왜 필요한가
============
OpenSlide 는 thread-safe 이지만 read_region 내부 mutex 로 직렬화된다. 같은
슬라이드를 여러 코어에서 병렬 디코딩하려면 thread 별로 독립된 핸들이 필요해
과거엔 `threading.local()` 에 직접 `{slide_id: OpenSlide}` 딕셔너리를 꽂아
썼다. 문제점:

1. **핸들 누수**: SlideManager.close(slide_id) 가 호출돼도 worker thread 의
   thread-local 핸들은 남아있어 파일 fd/메모리가 프로세스 수명 동안 leak.
2. **스테일 캐시**: 슬라이드 파일이 교체(삭제 후 같은 이름 업로드 등) 되면
   workers 가 구 핸들을 계속 써서 잘못된 데이터를 반환.
3. **무한 증가**: 많은 슬라이드를 훑는 워커에서 핸들이 무제한 누적.

이 모듈의 정책
===============
- **Generation 검증**: 핸들을 꺼낼 때마다 SlideManager.get_generation(slide_id)
  과 비교해 스테일이면 자기 핸들을 close 한 뒤 재오픈한다.
- **LRU 제한**: thread 당 최대 INT_MAX_SLIDES_PER_THREAD 핸들만 유지. 초과 시
  LRU 가 닫힌다.
- **스레드 소유권 준수**: 한 thread 의 local 핸들은 오직 그 thread 가 직접
  조작한다. 크로스 스레드 close 는 OpenSlide read 와 레이스가 되므로 금지.
"""

import threading
from collections import OrderedDict
from typing import Tuple

import openslide

from app.slide_manager import slide_manager

INT_MAX_SLIDES_PER_THREAD = 8


class _ThreadPool:
    """thread-local 저장소. OrderedDict 로 LRU 구현."""

    def __init__(self):
        # slide_id → (OpenSlide, int_generation)
        self.dict_slides: "OrderedDict[str, Tuple[openslide.OpenSlide, int]]" = OrderedDict()


_thread_local = threading.local()


def _get_thread_pool() -> _ThreadPool:
    obj_pool = getattr(_thread_local, "pool", None)
    if obj_pool is None:
        obj_pool = _ThreadPool()
        _thread_local.pool = obj_pool
    return obj_pool


def _close_silently(obj_slide: openslide.OpenSlide) -> None:
    try:
        obj_slide.close()
    except Exception:
        pass


def get_thread_slide(str_slide_id: str, str_file_path: str) -> openslide.OpenSlide:
    """현재 thread 의 OpenSlide 핸들 반환.

    - 캐시 히트 + generation 일치: 기존 핸들 재사용, LRU 우선순위 갱신.
    - 캐시 히트 + generation 불일치 (stale): 기존 핸들 close, 재오픈.
    - 캐시 미스: 새로 열고 LRU 에 추가 (초과 시 가장 오래된 항목 eviction).
    """
    obj_pool = _get_thread_pool()
    int_current_gen = slide_manager.get_generation(str_slide_id)

    tuple_cached = obj_pool.dict_slides.get(str_slide_id)
    if tuple_cached is not None:
        obj_slide, int_cached_gen = tuple_cached
        if int_cached_gen == int_current_gen:
            # LRU 갱신
            obj_pool.dict_slides.move_to_end(str_slide_id)
            return obj_slide
        # stale — 자기 핸들 정리 후 재오픈
        _close_silently(obj_slide)
        del obj_pool.dict_slides[str_slide_id]

    obj_new_slide = openslide.OpenSlide(str_file_path)
    obj_pool.dict_slides[str_slide_id] = (obj_new_slide, int_current_gen)
    obj_pool.dict_slides.move_to_end(str_slide_id)

    # LRU eviction
    while len(obj_pool.dict_slides) > INT_MAX_SLIDES_PER_THREAD:
        _str_evict_id, tuple_evict = obj_pool.dict_slides.popitem(last=False)
        _close_silently(tuple_evict[0])

    return obj_new_slide


def drop_thread_slide(str_slide_id: str) -> None:
    """현재 thread 의 특정 slide 핸들을 명시적으로 닫는다.

    작업 종료 시점에 AI 워커가 자기 thread 의 핸들을 정리할 때 쓴다.
    다른 thread 의 데이터는 건드리지 않는다 (threading.local 보호).
    """
    obj_pool = _get_thread_pool()
    tuple_cached = obj_pool.dict_slides.pop(str_slide_id, None)
    if tuple_cached is not None:
        _close_silently(tuple_cached[0])


def drop_all_thread_slides() -> None:
    """현재 thread 의 모든 핸들을 닫는다. 워커 종료 훅에서 호출 가능."""
    obj_pool = _get_thread_pool()
    for tuple_cached in obj_pool.dict_slides.values():
        _close_silently(tuple_cached[0])
    obj_pool.dict_slides.clear()
