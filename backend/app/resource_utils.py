"""Small resource-cleanup helpers used by backend workers and routers."""

import gc
from contextlib import suppress


def close_safely(resource) -> None:
    """Close PIL/OpenSlide/file-like objects without masking caller errors."""
    if resource is None:
        return
    close = getattr(resource, "close", None)
    if close is None:
        return
    with suppress(Exception):
        close()


def close_many(*resources) -> None:
    for resource in resources:
        close_safely(resource)


def collect_garbage() -> None:
    """Run CPython GC behind a tiny wrapper so call sites stay readable."""
    with suppress(Exception):
        gc.collect()
