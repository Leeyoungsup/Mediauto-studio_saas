"""A slow native close must not stall unrelated requests."""
import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from app import slide_manager as module


class Info:
    def __init__(self, close=lambda: None):
        self.slide = SimpleNamespace(close=close)
        self.last_accessed = time.time()

    def touch(self):
        self.last_accessed = time.time()


@pytest.mark.parametrize('action', ['close', 'close_all', 'evict'])
def test_slow_close_does_not_hold_manager_lock(monkeypatch, action):
    manager = module.SlideManager()
    entered, release = threading.Event(), threading.Event()

    def slow_close():
        entered.set()
        assert release.wait(5)

    old = Info(slow_close)
    old.last_accessed = 0
    manager._slides['old'] = old
    monkeypatch.setattr(module, 'MAX_OPEN_SLIDES', 1)
    monkeypatch.setattr(module, 'open_slide_silently', lambda path: object())
    monkeypatch.setattr(module, 'SlideInfo', lambda slide, path: Info())
    with ThreadPoolExecutor(2) as pool:
        fn = {'close': lambda: manager.close('old'),
              'close_all': manager.close_all,
              'evict': lambda: manager.open('new', 'new.ndpi')}[action]
        closing = pool.submit(fn)
        try:
            assert entered.wait(2)
            # These must complete while native close is still blocked.
            assert pool.submit(manager.get, 'old').result(timeout=1) is None
            assert pool.submit(manager.get_generation, 'old').result(timeout=1) == 1
            assert not closing.done()
        finally:
            release.set()
        closing.result(timeout=2)


def test_lookup_does_not_close_unrelated_idle_slide():
    manager = module.SlideManager()
    closed = []
    old = Info(lambda: closed.append(True))
    old.last_accessed = 0
    manager._slides.update(old=old, active=Info())
    assert manager.get('active') is not None
    assert not closed


def test_tile_metadata_open_keeps_event_loop_responsive(monkeypatch):
    from app.routers import tiles
    entered, release = threading.Event(), threading.Event()

    def slow_find(slide_id):
        entered.set()
        assert release.wait(5)
        return SimpleNamespace(get_stage=lambda mpp: 0,
                               stage_dimensions=[(10, 10)], stage_downsamples=[1])

    monkeypatch.setattr(tiles, '_find_and_open', slow_find)

    async def run():
        task = asyncio.create_task(tiles.get_stage_level('slide', 1.0, {}))
        try:
            for _ in range(100):
                if entered.is_set():
                    break
                await asyncio.sleep(.01)
            assert entered.is_set()
            assert not task.done()
            # The coroutine is still executing while open waits in its worker.
            await asyncio.sleep(.02)
        finally:
            release.set()
        assert (await task)['stage'] == 0

    asyncio.run(run())
