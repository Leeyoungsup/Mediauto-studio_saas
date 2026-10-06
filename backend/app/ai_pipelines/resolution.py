"""Shared physical input resolution for Quanti models."""

import math
import shutil
from pathlib import Path

QUANTI_INPUT_MPP = 0.5
QUANTI_INPUT_SIZE = 512


def quanti_patch_size(source_mpp):
    """Level-zero pixels covering a 256 µm field, rounded to a whole pixel.

    Use the returned size for both reading and mapping detections back to WSI
    coordinates; assuming a fixed 2x scale breaks slides with other MPPs.
    """
    try:
        mpp = float(source_mpp)
    except (TypeError, ValueError):
        raise ValueError("Quanti requires a finite positive slide MPP") from None
    if not math.isfinite(mpp) or mpp <= 0:
        raise ValueError("Quanti requires a finite positive slide MPP")
    return max(1, round(QUANTI_INPUT_SIZE * QUANTI_INPUT_MPP / mpp))


def preserve_previous_resolution_cache(cache_path):
    """Keep the original result before recomputation; never overwrite a backup."""
    source = Path(cache_path)
    backup = source.with_name(source.name + '.before-quanti-mpp05.bak')
    try:
        dst = backup.open('xb')
    except FileExistsError:
        return
    try:
        with dst, source.open('rb') as src:
            shutil.copyfileobj(src, dst)
    except BaseException:
        backup.unlink(missing_ok=True)
        raise
