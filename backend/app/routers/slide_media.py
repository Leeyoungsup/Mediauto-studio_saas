"""Media endpoints for slide thumbnails and previews."""

import io
from pathlib import Path

import openslide
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.auth import get_media_user
from app.openslide_utils import open_slide_silently
from app.path_utils import safe_filename, safe_subpath
from app.philips_proxy import PhilipsSlideProxy, is_philips_isyntax
from app.resource_utils import close_many
from app.slide_manager import build_color_corrector, slide_manager
from app import tile_generator

router = APIRouter(dependencies=[Depends(get_media_user)])


def _current_tile_cache(filename: str, file_path: str) -> bool:
    return tile_generator.tiles_are_valid(filename, file_path)


def _jpeg_response(image, quality: int = 85) -> StreamingResponse:
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/jpeg")


def _legacy_thumbnail_path(tiles_root: Path, int_size: int) -> Path | None:
    """Return the pre-v1.1 thumbnail cache path for 300px thumbnails."""
    if int_size != 300:
        return None
    path_legacy = tiles_root / "thumbnail.jpeg"
    return path_legacy if path_legacy.exists() else None


def _cached_thumbnail_response(path_thumb: Path) -> StreamingResponse:
    return StreamingResponse(open(path_thumb, "rb"), media_type="image/jpeg")


def _can_use_thumbnail_cache(tiles_root: Path, bool_current_cache: bool) -> bool:
    """Use thumbnail caches even while full tile generation is still incomplete.

    `.complete` validates the full tile pyramid.  A thumbnail can already be
    valid and useful before the full pyramid is done, especially for Leica SVS
    slides where opening the original file just to render a list thumbnail is
    expensive.  If a complete marker exists but is stale, keep the stricter
    validation and regenerate.
    """
    if bool_current_cache:
        return True
    return not (tiles_root / tile_generator.COMPLETE_MARKER_NAME).exists()


@router.get("/thumbnail-by-name")
async def get_thumbnail_by_name(
    filename: str = Query(...),
    path: str = Query(""),
    size: int = Query(2048, ge=64, le=8192),
    ndp: bool = Query(False, description="true returns an NDP-matched thumbnail"),
):
    """Return a thumbnail by filename without requiring the slide to be open."""
    filename = safe_filename(filename)
    int_size = max(64, min(8192, int(size or 2048)))
    file_path = safe_subpath(path) / filename
    tiles_root = tile_generator.get_tiles_dir_for_path(str(file_path))
    thumb_path_raw = tiles_root / f"thumbnail_{int_size}.jpeg"
    thumb_path_ndp = tiles_root / "ndpmatch" / f"thumbnail_{int_size}.jpeg"
    bool_current_cache = _current_tile_cache(filename, str(file_path))
    bool_use_thumb_cache = _can_use_thumbnail_cache(tiles_root, bool_current_cache)

    if ndp and thumb_path_ndp.exists() and bool_use_thumb_cache:
        return _cached_thumbnail_response(thumb_path_ndp)
    if not ndp and thumb_path_raw.exists() and bool_use_thumb_cache:
        return _cached_thumbnail_response(thumb_path_raw)
    path_legacy = _legacy_thumbnail_path(tiles_root, int_size)
    if not ndp and path_legacy and bool_use_thumb_cache:
        return _cached_thumbnail_response(path_legacy)

    if not file_path.exists():
        raise HTTPException(404, "File not found")

    slide = None
    thumb = None
    thumb_rgb = None
    thumb_ndp = None
    try:
        if is_philips_isyntax(file_path):
            slide = PhilipsSlideProxy(str(file_path))
        else:
            slide = open_slide_silently(str(file_path))
        apply_color, _ = build_color_corrector(slide)
        thumb_rgb = tile_generator.render_pyramid_thumbnail(
            slide, int_size, apply_color=apply_color
        )
        thumb_path_raw.parent.mkdir(parents=True, exist_ok=True)
        thumb_rgb.save(str(thumb_path_raw), "JPEG", quality=85)

        if ndp:
            from app.ndp_color_match import apply_ndp_fit
            thumb_ndp = apply_ndp_fit(thumb_rgb)
            thumb_path_ndp.parent.mkdir(parents=True, exist_ok=True)
            thumb_ndp.save(str(thumb_path_ndp), "JPEG", quality=85)
            return _jpeg_response(thumb_ndp, quality=85)

        return _jpeg_response(thumb_rgb, quality=85)
    except Exception as exc:
        raise HTTPException(500, f"Thumbnail generation failed: {exc}")
    finally:
        close_many(thumb_ndp, thumb_rgb, thumb, slide)


@router.get("/{slide_id}/preview")
async def get_preview(
    slide_id: str,
    size: int = Query(2048, ge=64, le=8192),
    ndp: bool = Query(False, description="true applies NDP color matching"),
):
    """Return a high-resolution slide preview."""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "Slide not found")
    int_size = max(64, min(8192, int(size or 2048)))
    filename = Path(info.file_path).name
    tiles_root = tile_generator.get_tiles_dir_for_path(info.file_path)
    thumb_path_raw = tiles_root / f"thumbnail_{int_size}.jpeg"
    thumb_path_ndp = tiles_root / "ndpmatch" / f"thumbnail_{int_size}.jpeg"
    bool_current_cache = _current_tile_cache(filename, info.file_path)
    bool_use_thumb_cache = _can_use_thumbnail_cache(tiles_root, bool_current_cache)

    if ndp and thumb_path_ndp.exists() and bool_use_thumb_cache:
        return _cached_thumbnail_response(thumb_path_ndp)
    if not ndp and thumb_path_raw.exists() and bool_use_thumb_cache:
        return _cached_thumbnail_response(thumb_path_raw)
    path_legacy = _legacy_thumbnail_path(tiles_root, int_size)
    if not ndp and path_legacy and bool_use_thumb_cache:
        return _cached_thumbnail_response(path_legacy)

    thumb = None
    thumb_rgb = None
    thumb_ndp = None
    try:
        thumb_rgb = tile_generator.render_pyramid_thumbnail(
            info.slide, int_size, apply_color=info.apply_icc
        )
        thumb_path_raw.parent.mkdir(parents=True, exist_ok=True)
        thumb_rgb.save(str(thumb_path_raw), "JPEG", quality=92)
        if ndp:
            from app.ndp_color_match import apply_ndp_fit
            thumb_ndp = apply_ndp_fit(thumb_rgb)
            thumb_path_ndp.parent.mkdir(parents=True, exist_ok=True)
            thumb_ndp.save(str(thumb_path_ndp), "JPEG", quality=92)
            return _jpeg_response(thumb_ndp, quality=92)
        return _jpeg_response(thumb_rgb, quality=92)
    finally:
        close_many(thumb_ndp, thumb_rgb, thumb)


@router.get("/{slide_id}/thumbnail")
async def get_thumbnail(
    slide_id: str,
    size: int = Query(2048, ge=64, le=8192),
    ndp: bool = Query(False, description="true returns an NDP-matched thumbnail"),
):
    """Return a cached or generated slide thumbnail."""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "Slide not found")

    filename = Path(info.file_path).name
    tiles_root = tile_generator.get_tiles_dir_for_path(info.file_path)
    int_size = max(64, min(8192, int(size or 2048)))
    thumb_path_raw = tiles_root / f"thumbnail_{int_size}.jpeg"
    thumb_path_ndp = tiles_root / "ndpmatch" / f"thumbnail_{int_size}.jpeg"
    bool_current_cache = _current_tile_cache(filename, info.file_path)
    bool_use_thumb_cache = _can_use_thumbnail_cache(tiles_root, bool_current_cache)

    if ndp:
        if thumb_path_ndp.exists() and bool_use_thumb_cache:
            return _cached_thumbnail_response(thumb_path_ndp)

        from PIL import Image as _Image
        from app.ndp_color_match import apply_ndp_fit
        thumb = None
        thumb_rgb = None
        thumb_ndp = None
        if thumb_path_raw.exists() and bool_use_thumb_cache:
            with _Image.open(str(thumb_path_raw)) as file_obj:
                thumb_rgb = file_obj.convert("RGB")
        else:
            thumb_rgb = tile_generator.render_pyramid_thumbnail(
                info.slide, int_size, apply_color=info.apply_icc
            )
            thumb_path_raw.parent.mkdir(parents=True, exist_ok=True)
            thumb_rgb.save(str(thumb_path_raw), "JPEG", quality=85)

        try:
            thumb_ndp = apply_ndp_fit(thumb_rgb)
            thumb_path_ndp.parent.mkdir(parents=True, exist_ok=True)
            thumb_ndp.save(str(thumb_path_ndp), "JPEG", quality=85)
            return _jpeg_response(thumb_ndp, quality=85)
        finally:
            close_many(thumb_ndp, thumb_rgb, thumb)

    if thumb_path_raw.exists() and bool_use_thumb_cache:
        return _cached_thumbnail_response(thumb_path_raw)
    path_legacy = _legacy_thumbnail_path(tiles_root, int_size)
    if path_legacy and bool_use_thumb_cache:
        return _cached_thumbnail_response(path_legacy)

    thumb = None
    thumb_rgb = None
    try:
        thumb_rgb = tile_generator.render_pyramid_thumbnail(
            info.slide, int_size, apply_color=info.apply_icc
        )
        thumb_path_raw.parent.mkdir(parents=True, exist_ok=True)
        thumb_rgb.save(str(thumb_path_raw), "JPEG", quality=85)
        return _jpeg_response(thumb_rgb, quality=85)
    finally:
        close_many(thumb_rgb, thumb)
