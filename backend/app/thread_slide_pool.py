"""Thread-local OpenSlide text text — text/LRU text

text text
============
OpenSlide text thread-safe text read_region text mutex text text. text
text text text text text thread text text text text
text `threading.local()` text text `{slide_id: OpenSlide}` text text
text. text:

1. **text text**: SlideManager.close(slide_id) text text worker thread text
   thread-local text text text fd/text text text text leak.
2. **text text**: text text text(text text text text text text) text
   workers text text text text text text text text.
3. **text text**: text text text text text text text.

text text text
===============
- **Generation text**: text text text SlideManager.get_generation(slide_id)
  text text text text text close text text text.
- **LRU text**: thread text text INT_MAX_SLIDES_PER_THREAD text text. text text
  LRU text text.
- **text text text**: text thread text local text text text thread text text
  text. text text close text OpenSlide read text text text text.
"""

import threading
from collections import OrderedDict
from typing import Tuple

import openslide

from app.openslide_utils import open_slide_silently
from app.philips_proxy import PhilipsSlideProxy, is_philips_isyntax
from app.slide_manager import slide_manager

INT_MAX_SLIDES_PER_THREAD = 8


class _ThreadPool:
    """thread-local text. OrderedDict text LRU text."""

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
    """text thread text OpenSlide text text.

    - text text + generation text: text text text, LRU text text.
    - text text + generation text (stale): text text close, text.
    - text text: text text LRU text text (text text text text text eviction).
    """
    obj_pool = _get_thread_pool()
    int_current_gen = slide_manager.get_generation(str_slide_id)

    tuple_cached = obj_pool.dict_slides.get(str_slide_id)
    if tuple_cached is not None:
        obj_slide, int_cached_gen = tuple_cached
        if int_cached_gen == int_current_gen:
            # LRU text
            obj_pool.dict_slides.move_to_end(str_slide_id)
            return obj_slide
        # stale — text text text text text
        _close_silently(obj_slide)
        del obj_pool.dict_slides[str_slide_id]

    if is_philips_isyntax(str_file_path):
        obj_new_slide = PhilipsSlideProxy(str_file_path)
    else:
        obj_new_slide = open_slide_silently(str_file_path)
    obj_pool.dict_slides[str_slide_id] = (obj_new_slide, int_current_gen)
    obj_pool.dict_slides.move_to_end(str_slide_id)

    # LRU eviction
    while len(obj_pool.dict_slides) > INT_MAX_SLIDES_PER_THREAD:
        _str_evict_id, tuple_evict = obj_pool.dict_slides.popitem(last=False)
        _close_silently(tuple_evict[0])

    return obj_new_slide


def drop_thread_slide(str_slide_id: str) -> None:
    """text thread text text slide text text text.

    text text text AI text text thread text text text text text.
    text thread text text text text (threading.local text).
    """
    obj_pool = _get_thread_pool()
    tuple_cached = obj_pool.dict_slides.pop(str_slide_id, None)
    if tuple_cached is not None:
        _close_silently(tuple_cached[0])


def drop_all_thread_slides() -> None:
    """text thread text text text text. text text text text text."""
    obj_pool = _get_thread_pool()
    for tuple_cached in obj_pool.dict_slides.values():
        _close_silently(tuple_cached[0])
    obj_pool.dict_slides.clear()
