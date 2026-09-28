"""Provenance for patches cropped at their requested level-zero coordinates."""
from pathlib import Path
import shutil

from app.philips_proxy import is_philips_isyntax

PHILIPS_PATCH_COORDINATES_VERSION = 2


def patch_coordinate_metadata(slide_path):
    if is_philips_isyntax(slide_path):
        return {'philips_patch_coordinates_version': PHILIPS_PATCH_COORDINATES_VERSION}
    return {}


def validate_patch_coordinate_cache(payload, slide_path, cache_path):
    if not is_philips_isyntax(slide_path):
        return
    if payload.get('philips_patch_coordinates_version') == PHILIPS_PATCH_COORDINATES_VERSION:
        return
    # Keep the original result before a requested inference replaces its cache.
    source = Path(cache_path)
    backup = source.with_name(source.name + '.before-philips-coordinate-v2.bak')
    try:
        with backup.open('xb') as dst, source.open('rb') as src:
            shutil.copyfileobj(src, dst)
    except FileExistsError:
        pass
    raise ValueError('stale Philips patch coordinates; original cache preserved at ' + str(backup))
