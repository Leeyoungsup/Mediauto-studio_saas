"""Keep native OpenSlide reads and explicit close mutually exclusive.

OpenSlide permits concurrent reads, but openslide_close must not overlap any
operation on the same handle. Manager eviction can otherwise abort the entire
process while another request is reading metadata, a thumbnail or a region.
Locks are per handle: the thread-local reader pool still reads in parallel.
"""
from collections.abc import Mapping
from functools import wraps
import threading

import openslide


def _with_open_handle(function):
    @wraps(function)
    def guarded(self, *args, **kwargs):
        with self._operation_lock:
            self._check_open()
            return function(self, *args, **kwargs)
    return guarded


class _GuardedMap(Mapping):
    """Protect lazy metadata/associated-image reads, not just map creation."""
    def __init__(self, owner, mapping):
        self._owner = owner
        self._mapping = mapping

    def __getitem__(self, key):
        with self._owner._operation_lock:
            self._owner._check_open()
            return self._mapping[key]

    def __iter__(self):
        with self._owner._operation_lock:
            self._owner._check_open()
            return iter(tuple(self._mapping))

    def __len__(self):
        with self._owner._operation_lock:
            self._owner._check_open()
            return len(self._mapping)


class GuardedOpenSlide(openslide.OpenSlide):
    def __init__(self, filename):
        self._operation_lock = threading.RLock()
        self._closed = False
        super().__init__(filename)

    def _check_open(self):
        if self._closed:
            raise openslide.OpenSlideError("Slide has been closed")

    def close(self):
        with self._operation_lock:
            if not self._closed:
                self._closed = True
                super().close()

    @property
    @_with_open_handle
    def level_count(self):
        return super().level_count

    @property
    @_with_open_handle
    def level_dimensions(self):
        return super().level_dimensions

    @property
    @_with_open_handle
    def level_downsamples(self):
        return super().level_downsamples

    @property
    @_with_open_handle
    def properties(self):
        return _GuardedMap(self, super().properties)

    @property
    @_with_open_handle
    def associated_images(self):
        return _GuardedMap(self, super().associated_images)

    @_with_open_handle
    def get_best_level_for_downsample(self, downsample):
        return super().get_best_level_for_downsample(downsample)

    @_with_open_handle
    def read_region(self, location, level, size):
        return super().read_region(location, level, size)

    @_with_open_handle
    def get_thumbnail(self, size):
        return super().get_thumbnail(size)

    @_with_open_handle
    def set_cache(self, cache):
        return super().set_cache(cache)
