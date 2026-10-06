"""Deterministic read/close races without crashing a real native handle."""
from concurrent.futures import ThreadPoolExecutor
import threading

import openslide
import pytest

from app.guarded_openslide import GuardedOpenSlide


@pytest.fixture
def slide(monkeypatch):
    monkeypatch.setattr(openslide.OpenSlide, '__init__', lambda self, filename: None)
    return GuardedOpenSlide('test.ndpi')


@pytest.mark.parametrize('operation', ['read_region', 'get_thumbnail', 'properties', 'associated_images'])
def test_close_waits_for_active_operation(slide, monkeypatch, operation):
    entered = threading.Event()
    release = threading.Event()
    closing = threading.Event()
    closed = threading.Event()

    def blocking_read(*args):
        entered.set()
        assert release.wait(3)
        assert not closed.is_set()
        return 'read-result'

    monkeypatch.setattr(openslide.OpenSlide, 'close', lambda self: closed.set())
    if operation in ('properties', 'associated_images'):
        class LazyMap(dict):
            def __getitem__(self, key):
                return blocking_read()
        monkeypatch.setattr(openslide.OpenSlide, operation, property(lambda self: LazyMap(key=1)))
        # Obtain the lazy map BEFORE the concurrent read/close calls.
        mapping = getattr(slide, operation)
        read = lambda: mapping['key']
    else:
        monkeypatch.setattr(openslide.OpenSlide, operation, blocking_read)
        read = lambda: getattr(slide, operation)(*((0, 0), 0, (8, 8)) if operation == 'read_region' else ((8, 8),))

    def close():
        closing.set()
        slide.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(read)
        assert entered.wait(3)
        close_future = pool.submit(close)
        try:
            assert closing.wait(3)
            assert not closed.wait(.05)
        finally:
            release.set()
        assert future.result(3) == 'read-result'
        close_future.result(3)
    assert closed.is_set()
    with pytest.raises(openslide.OpenSlideError, match='closed'):
        read()


def test_close_idempotent_and_metadata_rejected_after_close(slide, monkeypatch):
    calls = []
    monkeypatch.setattr(openslide.OpenSlide, 'close', lambda self: calls.append('close'))
    monkeypatch.setattr(openslide.OpenSlide, 'properties', property(lambda self: {'vendor': 'hamamatsu'}))
    metadata = slide.properties
    assert list(metadata) == ['vendor']
    slide.close()
    slide.close()
    assert calls == ['close']
    for read in (lambda: list(metadata), lambda: len(metadata), lambda: slide.level_count):
        with pytest.raises(openslide.OpenSlideError):
            read()


def test_separate_handles_do_not_serialize(slide, monkeypatch):
    barrier = threading.Barrier(2)
    def read(self, *args):
        barrier.wait(timeout=3)
        return 1
    monkeypatch.setattr(openslide.OpenSlide, 'read_region', read)
    other = GuardedOpenSlide('other.ndpi')
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(s.read_region, (0, 0), 0, (1, 1)) for s in (slide, other)]
        assert [f.result(4) for f in futures] == [1, 1]
