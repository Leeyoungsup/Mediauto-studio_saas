"""Media endpoints for slide thumbnails and previews."""

import asyncio
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response

from app.auth import get_media_user
from app.cpu_layout import media_executor
from app.openslide_utils import open_slide_silently
from app.path_utils import safe_filename, safe_subpath
from app.philips_proxy import PhilipsSlideProxy, is_philips_isyntax
from app.resource_utils import close_many
from app.slide_manager import build_color_corrector, slide_manager
from app.thread_slide_pool import get_thread_slide
from app import tile_generator

router = APIRouter(dependencies=[Depends(get_media_user)])


def _consume_media_future(future) -> None:
    try:
        future.exception()
    except BaseException:
        pass


async def _run_media_job(request: Request, fn):
    """Run a blocking WSI media read with cooperative request cancellation."""

    obj_cancel = threading.Event()
    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(media_executor, lambda: fn(obj_cancel))
    while True:
        done, _ = await asyncio.wait({future}, timeout=0.1)
        if done:
            return future.result()
        if await request.is_disconnected():
            obj_cancel.set()
            if not future.cancel():
                future.add_done_callback(_consume_media_future)
            raise HTTPException(status_code=499, detail="Client closed request")


def _current_tile_cache(filename: str, file_path: str) -> bool:
    # Thumbnail requests are frequent (slide list, viewer, Data Linkage).
    # Deep validation opens the source slide, which means reopening and parsing
    # a DICOM ZIP even when the JPEG thumbnail is already cached. The complete
    # marker already contains source size/mtime identity, so use the cheap check
    # here and reserve deep validation for the tile worker.
    return tile_generator.tiles_marker_matches_file(filename, file_path)


def _legacy_thumbnail_path(tiles_root: Path, int_size: int) -> Path | None:
    """Return the pre-v1.1 thumbnail cache path for 300px thumbnails."""
    if int_size != 300:
        return None
    path_legacy = tiles_root / "thumbnail.jpeg"
    return path_legacy if path_legacy.exists() else None


def _cached_thumbnail_response(path_thumb: Path) -> FileResponse:
    return FileResponse(
        path=str(path_thumb),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


def _no_label_response() -> Response:
    return Response(
        status_code=204,
        headers={"Cache-Control": "private, max-age=3600"},
    )


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
    request: Request,
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

    def _generate_thumbnail(obj_cancel: threading.Event) -> Path | None:
        slide = None
        thumb_rgb = None
        thumb_ndp = None
        try:
            if obj_cancel.is_set():
                return None
            if is_philips_isyntax(file_path):
                slide = PhilipsSlideProxy(str(file_path))
            else:
                slide = open_slide_silently(str(file_path))
            if obj_cancel.is_set():
                return None
            apply_color, _ = build_color_corrector(slide)
            thumb_rgb = tile_generator.render_pyramid_thumbnail(
                slide, int_size, apply_color=apply_color
            )
            # read_region/get_thumbnail cannot be interrupted in the middle,
            # but an obsolete request must not continue into resize/save work.
            if obj_cancel.is_set():
                return None
            thumb_path_raw.parent.mkdir(parents=True, exist_ok=True)
            thumb_rgb.save(str(thumb_path_raw), "JPEG", quality=85)

            if ndp:
                if obj_cancel.is_set():
                    return None
                from app.ndp_color_match import apply_ndp_fit
                thumb_ndp = apply_ndp_fit(thumb_rgb)
                if obj_cancel.is_set():
                    return None
                thumb_path_ndp.parent.mkdir(parents=True, exist_ok=True)
                thumb_ndp.save(str(thumb_path_ndp), "JPEG", quality=85)
                return thumb_path_ndp
            return thumb_path_raw
        finally:
            close_many(thumb_ndp, thumb_rgb, slide)

    try:
        path_generated = await _run_media_job(request, _generate_thumbnail)
        if path_generated is None:
            raise HTTPException(499, "Client closed request")
        return _cached_thumbnail_response(path_generated)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Thumbnail generation failed: {exc}")


@router.get("/label-by-name")
async def get_label_by_name(
    request: Request,
    filename: str = Query(...),
    path: str = Query(""),
    size: int = Query(300, ge=64, le=1024),
):
    """Return the scanner specimen label when the WSI contains one.

    Negative results are cached with the source identity so reopening the
    sidebar does not repeatedly scan label-less WSI files.
    """

    filename = safe_filename(filename)
    int_size = max(64, min(1024, int(size or 300)))
    file_path = safe_subpath(path) / filename
    if not file_path.is_file():
        raise HTTPException(404, "File not found")

    tiles_root = tile_generator.get_tiles_dir_for_path(str(file_path))
    path_label = tiles_root / f"associated_label_{int_size}.jpeg"
    bool_cached = tile_generator.associated_label_cache_status(str(file_path))
    if bool_cached is True and path_label.is_file():
        return _cached_thumbnail_response(path_label)
    if bool_cached is False:
        return _no_label_response()

    def _generate_label(obj_cancel: threading.Event) -> Path | None:
        slide = None
        try:
            if obj_cancel.is_set():
                return None
            if is_philips_isyntax(file_path):
                slide = PhilipsSlideProxy(str(file_path))
            else:
                slide = open_slide_silently(str(file_path))
            if obj_cancel.is_set():
                return None
            path_generated = tile_generator.generate_associated_label_cache(
                slide,
                tiles_root,
                str(file_path),
                int_size=int_size,
            )
            if obj_cancel.is_set():
                return None
            return path_generated
        finally:
            close_many(slide)

    try:
        path_generated = await _run_media_job(request, _generate_label)
        if path_generated is None:
            return _no_label_response()
        return _cached_thumbnail_response(path_generated)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Label extraction failed: {exc}")


@router.get("/{slide_id}/preview")
async def get_preview(
    request: Request,
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

    def _generate_preview(obj_cancel: threading.Event) -> Path | None:
        thumb_rgb = None
        thumb_ndp = None
        try:
            if obj_cancel.is_set():
                return None
            obj_slide = get_thread_slide(slide_id, info.file_path)
            thumb_rgb = tile_generator.render_pyramid_thumbnail(
                obj_slide, int_size, apply_color=info.apply_icc
            )
            if obj_cancel.is_set():
                return None
            thumb_path_raw.parent.mkdir(parents=True, exist_ok=True)
            thumb_rgb.save(str(thumb_path_raw), "JPEG", quality=92)
            if ndp:
                if obj_cancel.is_set():
                    return None
                from app.ndp_color_match import apply_ndp_fit
                thumb_ndp = apply_ndp_fit(thumb_rgb)
                if obj_cancel.is_set():
                    return None
                thumb_path_ndp.parent.mkdir(parents=True, exist_ok=True)
                thumb_ndp.save(str(thumb_path_ndp), "JPEG", quality=92)
                return thumb_path_ndp
            return thumb_path_raw
        finally:
            close_many(thumb_ndp, thumb_rgb)

    path_generated = await _run_media_job(request, _generate_preview)
    if path_generated is None:
        raise HTTPException(499, "Client closed request")
    return _cached_thumbnail_response(path_generated)


@router.get("/{slide_id}/thumbnail")
async def get_thumbnail(
    request: Request,
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

    if ndp and thumb_path_ndp.exists() and bool_use_thumb_cache:
        return _cached_thumbnail_response(thumb_path_ndp)

    if not ndp and thumb_path_raw.exists() and bool_use_thumb_cache:
        return _cached_thumbnail_response(thumb_path_raw)
    path_legacy = _legacy_thumbnail_path(tiles_root, int_size)
    if not ndp and path_legacy and bool_use_thumb_cache:
        return _cached_thumbnail_response(path_legacy)

    def _generate_thumbnail(obj_cancel: threading.Event) -> Path | None:
        from PIL import Image as _Image

        thumb_rgb = None
        thumb_ndp = None
        try:
            if ndp and thumb_path_raw.exists() and bool_use_thumb_cache:
                with _Image.open(str(thumb_path_raw)) as file_obj:
                    thumb_rgb = file_obj.convert("RGB")
            else:
                if obj_cancel.is_set():
                    return None
                obj_slide = get_thread_slide(slide_id, info.file_path)
                thumb_rgb = tile_generator.render_pyramid_thumbnail(
                    obj_slide, int_size, apply_color=info.apply_icc
                )
                if obj_cancel.is_set():
                    return None
                thumb_path_raw.parent.mkdir(parents=True, exist_ok=True)
                thumb_rgb.save(str(thumb_path_raw), "JPEG", quality=85)

            if not ndp:
                return thumb_path_raw
            if obj_cancel.is_set():
                return None
            from app.ndp_color_match import apply_ndp_fit
            thumb_ndp = apply_ndp_fit(thumb_rgb)
            if obj_cancel.is_set():
                return None
            thumb_path_ndp.parent.mkdir(parents=True, exist_ok=True)
            thumb_ndp.save(str(thumb_path_ndp), "JPEG", quality=85)
            return thumb_path_ndp
        finally:
            close_many(thumb_ndp, thumb_rgb)

    path_generated = await _run_media_job(request, _generate_thumbnail)
    if path_generated is None:
        raise HTTPException(499, "Client closed request")
    return _cached_thumbnail_response(path_generated)
