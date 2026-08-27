"""
text text ??3text stage text level 0 text text text.

text:
  tiles/{slide_id}/
    ?쒋?? 0/{tx}_{ty}.jpeg    ??stage 0 (downsample 1, text text)
    ?쒋?? 1/{tx}_{ty}.jpeg    ??stage 1 (downsample 4, level0??096px text 1024 text)
    ?쒋?? 2/{tx}_{ty}.jpeg    ??stage 2 (downsample 8, level0??192px text 1024 text)
    ?쒋?? thumbnail.jpeg
    ?붴?? .complete           ??text text text (JSON: text/ICC text/text text)

text text:
  stage 2 text text(8192x8192 at level 0) text text text text text
    - stage 2 tile 1text (text 8192??024 text)
    - stage 1 tile 4text (4text 4096 text ??text 1024 text)
    - stage 0 tile 64text (8x8 text, 1024 text)
  text 69text text text text read_region text text. I/O text.
"""

import hashlib
import json
import math
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import openslide
from PIL import Image

from app.config import settings
from app.openslide_utils import open_slide_silently
from app.philips_proxy import PhilipsSlideProxy, is_philips_isyntax
from app.slide_identity import slide_cache_key
from app.slide_manager import (
    STAGE_READ_SIZE,
    STAGE_COUNT,
    TILE_SIZE_OUT,
    build_color_corrector,
)

_thumb_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="thumb")

TILE_SIZE = TILE_SIZE_OUT


def _open_slide(file_path: str):
    if is_philips_isyntax(file_path):
        return PhilipsSlideProxy(file_path)
    return open_slide_silently(file_path)

# .complete marker schema version. Bump when the on-disk tile format changes
# in a way that requires regeneration.
# v2: 3text stage text (level 0 text) ??text level-index text text text
# v3: Hamamatsu NDP.view2 text gamma=1.8 + Target.White.Intensity LUT text ??
#     text raw-pass-through text text text text text text.
# v5: stage 1/0 generated from 4096 reads; stage 2 derived from stage-1 tiles.
COMPLETE_MARKER_VERSION = 5
COMPLETE_MARKER_NAME = ".complete"


def image_to_white_rgb(obj_img: Image.Image) -> Image.Image:
    """Return RGB with transparent pixels composited onto white.

    OpenSlide regions may include transparent outside-slide padding. Direct
    RGBA-to-RGB conversion maps those pixels to black, which appears as
    letterbox bars in the viewer.
    """
    if obj_img.mode in ("RGBA", "LA"):
        obj_rgba = obj_img.convert("RGBA")
        obj_white = Image.new("RGB", obj_rgba.size, (255, 255, 255))
        obj_white.paste(obj_rgba, mask=obj_rgba.getchannel("A"))
        try:
            obj_rgba.close()
        except Exception:
            pass
        return obj_white
    if obj_img.mode == "P" and "transparency" in obj_img.info:
        obj_rgba = obj_img.convert("RGBA")
        obj_white = Image.new("RGB", obj_rgba.size, (255, 255, 255))
        obj_white.paste(obj_rgba, mask=obj_rgba.getchannel("A"))
        try:
            obj_rgba.close()
        except Exception:
            pass
        return obj_white
    return obj_img.convert("RGB")


def read_region_for_output(
    slide,
    location: tuple[int, int],
    scene_size: tuple[int, int],
    output_size: tuple[int, int],
) -> Image.Image:
    """Read a region efficiently for a requested output resolution.

    DICOM WSI is already stored as a native multi-resolution frame pyramid.
    Low-resolution viewer stages should use that pyramid instead of retrieving
    hundreds of level-0 DICOM frames and immediately downsampling them.
    Other slide formats keep the established level-0 behavior.
    """

    int_scene_w = max(1, int(scene_size[0]))
    int_scene_h = max(1, int(scene_size[1]))
    int_output_w = max(1, int(output_size[0]))
    int_output_h = max(1, int(output_size[1]))
    if not bool(getattr(slide, "is_dicom", False)):
        return slide.read_region(location, 0, (int_scene_w, int_scene_h))

    float_target_downsample = max(
        int_scene_w / int_output_w,
        int_scene_h / int_output_h,
        1.0,
    )
    int_level = int(slide.get_best_level_for_downsample(float_target_downsample))
    float_level_downsample = max(1.0, float(slide.level_downsamples[int_level]))
    int_read_w = max(1, int(math.ceil(int_scene_w / float_level_downsample)))
    int_read_h = max(1, int(math.ceil(int_scene_h / float_level_downsample)))
    return slide.read_region(location, int_level, (int_read_w, int_read_h))


def render_pyramid_thumbnail(slide, int_size: int, apply_color=None) -> Image.Image:
    """Render a thumbnail from OpenSlide pyramid coordinates, not get_thumbnail().

    Some Leica/Aperio SVS files expose associated thumbnails whose spatial
    origin does not match read_region() level-0 coordinates.  The viewer, AI
    patch extraction, and VS overlays all use read_region coordinates, so
    thumbnails used for navigation or tissue selection must be derived from the
    same pyramid.
    """
    int_size = max(1, int(int_size))
    int_w0, int_h0 = [int(v) for v in slide.dimensions]
    if int_w0 <= 0 or int_h0 <= 0:
        return Image.new("RGB", (int_size, int_size), (255, 255, 255))

    float_scale = min(int_size / int_w0, int_size / int_h0)
    int_out_w = max(1, int(round(int_w0 * float_scale)))
    int_out_h = max(1, int(round(int_h0 * float_scale)))
    float_target_ds = max(int_w0 / int_out_w, int_h0 / int_out_h)

    try:
        int_level = int(slide.get_best_level_for_downsample(float_target_ds))
    except Exception:
        int_level = max(0, len(getattr(slide, "level_dimensions", [(int_w0, int_h0)])) - 1)
    int_level = max(0, min(int_level, len(slide.level_dimensions) - 1))
    int_lw, int_lh = [int(v) for v in slide.level_dimensions[int_level]]

    obj_region = slide.read_region((0, 0), int_level, (int_lw, int_lh))
    try:
        obj_rgb = image_to_white_rgb(obj_region)
        try:
            if apply_color is not None:
                obj_rgb = apply_color(obj_rgb)
            if obj_rgb.size != (int_out_w, int_out_h):
                obj_thumb = obj_rgb.resize((int_out_w, int_out_h), Image.LANCZOS)
            else:
                obj_thumb = obj_rgb.copy()
            return obj_thumb
        finally:
            try:
                obj_rgb.close()
            except Exception:
                pass
    finally:
        try:
            obj_region.close()
        except Exception:
            pass


def generate_standard_thumbnail_cache(
    slide,
    tiles_dir: Path,
    apply_color=None,
    sizes: tuple[int, ...] = (300, 420, 2048),
) -> None:
    """Render common UI thumbnail sizes from one pyramid read.

    DICOM slide initialization and frame retrieval are much more expensive than
    resizing a cached Pillow image. Generate the largest common preview once,
    then derive the sidebar/list variants without reopening the source archive.
    """

    tuple_sizes = tuple(sorted({max(64, int(value)) for value in sizes}))
    list_missing = [
        int_size for int_size in tuple_sizes
        if not (tiles_dir / f"thumbnail_{int_size}.jpeg").is_file()
    ]
    path_legacy = tiles_dir / "thumbnail.jpeg"
    if not list_missing and path_legacy.is_file():
        return

    int_master_size = max(tuple_sizes)
    obj_master = render_pyramid_thumbnail(
        slide, int_master_size, apply_color=apply_color
    )
    try:
        tiles_dir.mkdir(parents=True, exist_ok=True)
        for int_size in tuple_sizes:
            path_output = tiles_dir / f"thumbnail_{int_size}.jpeg"
            if path_output.is_file() and not (int_size == 300 and not path_legacy.is_file()):
                continue
            if int_size == int_master_size:
                obj_output = obj_master.copy()
            else:
                obj_output = obj_master.copy()
                obj_output.thumbnail((int_size, int_size), Image.LANCZOS)
            try:
                if not path_output.is_file():
                    obj_output.save(str(path_output), "JPEG", quality=85)
                if int_size == 300 and not path_legacy.is_file():
                    obj_output.save(str(path_legacy), "JPEG", quality=85)
            finally:
                obj_output.close()
    finally:
        obj_master.close()


def _image_has_visible_content(obj_img: Image.Image, int_threshold: int = 245) -> bool:
    """Return False for pure/near-white tiles that do not need disk storage."""
    try:
        obj_gray = obj_img.convert("L")
        extrema = obj_gray.getextrema()
        try:
            obj_gray.close()
        except Exception:
            pass
        return bool(extrema and extrema[0] < int_threshold)
    except Exception:
        return True


def _slide_icc_hash(slide) -> Optional[str]:
    """text ICC text text md5 text. text text text text text None."""
    try:
        obj_profile = getattr(slide, "color_profile", None)
        if obj_profile is None:
            return None
        if hasattr(obj_profile, "tobytes"):
            return hashlib.md5(obj_profile.tobytes()).hexdigest()
        # Fallback: description text (text text text text text text text)
        from PIL import ImageCms
        str_desc = ImageCms.getProfileDescription(obj_profile) or ""
        return hashlib.md5(("desc:" + str_desc).encode("utf-8")).hexdigest()
    except Exception as e:
        print(f"[tile_generator] ICC hash check failed: {e}")
        return None


def slide_source_signature(slide, file_path: str) -> dict:
    """Return a stable-enough signature for the slide backing a tile cache.

    The tile cache directory is keyed by filename stem, so a replaced file with
    the same name can otherwise reuse stale tiles from a previous slide.  Keep
    this signature cheap: OpenSlide quickhash when available plus filesystem and
    dimension metadata.
    """
    try:
        stat = Path(file_path).stat()
        int_size = int(stat.st_size)
        int_mtime_ns = int(stat.st_mtime_ns)
    except Exception:
        int_size = 0
        int_mtime_ns = 0
    try:
        dims = [int(v) for v in getattr(slide, "dimensions", (0, 0))]
    except Exception:
        dims = [0, 0]
    try:
        levels = [[int(w), int(h)] for w, h in getattr(slide, "level_dimensions", [])]
    except Exception:
        levels = []
    try:
        quickhash = str(slide.properties.get("openslide.quickhash-1") or "")
    except Exception:
        quickhash = ""
    try:
        vendor = str(slide.properties.get("openslide.vendor") or "")
    except Exception:
        vendor = ""
    return {
        "filename": Path(file_path).name,
        "size": int_size,
        "mtime_ns": int_mtime_ns,
        "quickhash": quickhash,
        "dimensions": dims,
        "level_dimensions": levels,
        "vendor": vendor,
    }


def source_signature_matches(payload: dict, slide, file_path: str) -> bool:
    cached = payload.get("source")
    if not isinstance(cached, dict):
        return False
    current = slide_source_signature(slide, file_path)
    for key in ("filename", "size", "mtime_ns", "quickhash", "dimensions", "level_dimensions", "vendor"):
        if cached.get(key) != current.get(key):
            return False
    return True


def source_marker_matches_file_stat(payload: dict, file_path: str) -> bool:
    """Fast source check that does not open the WSI.

    Startup tile validation uses this to avoid deep OpenSlide/ICC checks across
    every cached slide.  Deep validation remains in tiles_are_valid().
    """
    cached = payload.get("source")
    if not isinstance(cached, dict):
        return False
    try:
        path = Path(file_path)
        stat = path.stat()
    except Exception:
        return False
    return (
        cached.get("filename") == path.name
        and cached.get("size") == int(stat.st_size)
        and cached.get("mtime_ns") == int(stat.st_mtime_ns)
    )


def read_complete_marker(filename: str, file_path: str = "") -> Optional[dict]:
    """text JSON text text text. text text/textJSON(legacy touch)/text text text None."""
    if not file_path:
        return None
    tiles_dir = get_tiles_dir_for_path(file_path)
    path = tiles_dir / COMPLETE_MARKER_NAME
    if not path.exists():
        return None
    try:
        str_text = path.read_text(encoding="utf-8").strip()
        if not str_text:
            return None  # legacy touch file (size 0)
        return json.loads(str_text)
    except Exception:
        return None


def _write_complete_marker(
    tiles_dir: Path,
    str_icc_hash: Optional[str],
    bool_icc_applied: bool,
    slide=None,
    file_path: str = "",
) -> None:
    """text JSON text. _generate_tiles text text text."""
    dict_marker = {
        "version": COMPLETE_MARKER_VERSION,
        "icc_hash": str_icc_hash,
        "icc_applied": bool(bool_icc_applied),
        "source": slide_source_signature(slide, file_path) if slide is not None and file_path else {},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (tiles_dir / COMPLETE_MARKER_NAME).write_text(
        json.dumps(dict_marker, ensure_ascii=False),
        encoding="utf-8",
    )


def _save_jpeg(obj_img: Image.Image, path: Path, quality: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{threading.get_ident()}.{time.time_ns()}.tmp")
    try:
        obj_img.save(str(tmp_path), "JPEG", quality=quality)
        tmp_path.replace(path)
        blank_tile_marker_path(path).unlink(missing_ok=True)
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


def blank_tile_marker_path(path_tile: Path) -> Path:
    """Return the zero-byte marker used for an intentionally blank tile."""
    return path_tile.with_suffix(".blank")


def blank_tile_marker_exists(path_tile: Path) -> bool:
    return blank_tile_marker_path(path_tile).is_file()


def _mark_blank_tile(path_tile: Path) -> None:
    """Remember a decoded blank region without storing a white JPEG."""
    path_marker = blank_tile_marker_path(path_tile)
    path_marker.parent.mkdir(parents=True, exist_ok=True)
    if not path_tile.exists():
        path_marker.touch(exist_ok=True)


def _tile_result_exists(path_tile: Path) -> bool:
    return path_tile.is_file() or blank_tile_marker_exists(path_tile)


def tiles_are_valid(filename: str, file_path: str) -> bool:
    """text text text text text text text.

    - text text / text touch text / text text ??False (text text)
    - text icc_hash text text text ICC text text ??False
    - text icc_applied=False text text text ICC text text ??False
    - text text text ??True (text text text; text text)

    text: text text text text text text text. text text _generate_tiles text
    text text, text text text text text text.
    """
    tiles_dir = get_tiles_dir_for_path(file_path)
    if not tiles_dir.exists():
        return False
    dict_marker = read_complete_marker(filename, file_path)
    if dict_marker is None:
        return False
    if dict_marker.get("version") != COMPLETE_MARKER_VERSION:
        return False
    try:
        slide = _open_slide(file_path)
    except Exception as e:
        print(f"[tile_generator] tiles_are_valid: slide open failed ({filename}): {e}")
        return True  # Avoid invalidating existing tiles when the slide cannot be opened.
    try:
        str_current_hash = _slide_icc_hash(slide)
        bool_source_matches = source_signature_matches(dict_marker, slide, file_path)
    finally:
        try:
            slide.close()
        except Exception:
            pass

    str_marker_hash = dict_marker.get("icc_hash")
    if str_marker_hash != str_current_hash:
        return False
    if not bool_source_matches:
        return False
    # text text text text text ICC text text text: text text text
    # text text text. text text text text text valid text text.
    # text(PIL/openslide)text text text text text text tile dir text text text.
    return True


def tiles_marker_matches_file(filename: str, file_path: str) -> bool:
    """Return True when .complete matches cheap file identity fields only."""
    tiles_dir = get_tiles_dir_for_path(file_path)
    if not tiles_dir.exists():
        return False
    dict_marker = read_complete_marker(filename, file_path)
    if dict_marker is None:
        return False
    if dict_marker.get("version") != COMPLETE_MARKER_VERSION:
        return False
    return source_marker_matches_file_stat(dict_marker, file_path)


def invalidate_tiles(filename: str, file_path: str = "") -> None:
    """text text text text ??text text text."""
    if not file_path:
        return
    tiles_dir = get_tiles_dir_for_path(file_path)
    if tiles_dir.exists():
        shutil.rmtree(tiles_dir, ignore_errors=True)


# ?? text text ??

class TileGenProgress:
    __slots__ = ("total_tiles", "generated_tiles", "current_level", "status", "error")

    def __init__(self):
        self.total_tiles = 0
        self.generated_tiles = 0
        self.current_level = -1
        self.status = "pending"  # pending | generating | completed | error
        self.error = None

    @property
    def progress(self):
        if self.total_tiles == 0:
            return 0
        return min(100, int(self.generated_tiles / self.total_tiles * 100))

    def to_dict(self):
        return {
            "status": self.status,
            "progress": self.progress,
            "total_tiles": self.total_tiles,
            "generated_tiles": self.generated_tiles,
            "current_level": self.current_level,
            "error": self.error,
        }


_progress: dict[str, TileGenProgress] = {}
_progress_lock = threading.Lock()
_priority_lock = threading.Lock()
_priority_block_locks: dict[tuple[str, int, int], threading.Lock] = {}
_priority_stage1: dict[str, set[tuple[int, int]]] = {}
_completed_cache_repairs: set[tuple[str, int, int, int]] = set()


def get_tiles_dir(filename: str) -> Path:
    """Legacy tile dir keyed by filename stem."""
    stem = Path(filename).stem
    return Path(settings.TILES_DIR) / stem


def get_tiles_dir_for_path(file_path: str) -> Path:
    """Current tile dir keyed by full slide identity."""
    return Path(settings.TILES_DIR) / slide_cache_key(file_path)


def tiles_ready(filename: str, file_path: str = "") -> bool:
    """text text text text"""
    if not file_path:
        return False
    tiles_dir = get_tiles_dir_for_path(file_path)
    return (tiles_dir / ".complete").exists()


def get_progress(filename: str, file_path: str = "") -> Optional[dict]:
    """text text text (text None)"""
    if not file_path:
        return None
    progress_key = slide_cache_key(file_path)
    with _progress_lock:
        p = _progress.get(progress_key)
        if p:
            return p.to_dict()
    # text text text
    if tiles_ready(filename, file_path):
        return {"status": "completed", "progress": 100,
                "total_tiles": 0, "generated_tiles": 0,
                "current_level": -1, "error": None}
    return None


def is_generation_running(filename: str, file_path: str = "") -> bool:
    if not file_path:
        return False
    progress_key = slide_cache_key(file_path)
    with _progress_lock:
        return _progress.get(progress_key, None) is not None and _progress[progress_key].status == "generating"


def any_generation_running() -> bool:
    with _progress_lock:
        return any(progress.status == "generating" for progress in _progress.values())


def start_generation(filename: str, file_path: str):
    """text text text text text (text text/text text text)"""
    if tiles_marker_matches_file(filename, file_path):
        return

    progress_key = slide_cache_key(file_path)
    with _progress_lock:
        if progress_key in _progress and _progress[progress_key].status == "generating":
            return  # text text text

    from app.cpu_layout import tile_executor
    tile_executor.submit(_generate_tiles, filename, file_path)


def _stage2_coord_for_tile(level: int, tile_x: int, tile_y: int) -> tuple[int, int]:
    if level <= 0:
        return tile_x // 8, tile_y // 8
    if level == 1:
        return tile_x // 2, tile_y // 2
    return tile_x, tile_y


def _stage1_coord_for_tile(level: int, tile_x: int, tile_y: int) -> tuple[int, int]:
    if level <= 0:
        return tile_x // 4, tile_y // 4
    if level == 1:
        return tile_x, tile_y
    return tile_x * 2, tile_y * 2


def _target_tile_path_for_file(file_path: str, level: int, tile_x: int, tile_y: int) -> Path:
    return get_tiles_dir_for_path(file_path) / str(level) / f"{tile_x}_{tile_y}.jpeg"


def _completed_cache_repair_key(
    file_path: str,
    level: int,
    tile_x: int,
    tile_y: int,
) -> tuple[str, int, int, int]:
    return (slide_cache_key(file_path), level, tile_x, tile_y)


def is_completed_cache_tile_repair_pending(
    file_path: str,
    level: int,
    tile_x: int,
    tile_y: int,
) -> bool:
    key = _completed_cache_repair_key(file_path, level, tile_x, tile_y)
    with _priority_lock:
        return key in _completed_cache_repairs


def queue_completed_cache_tile_repair(
    filename: str,
    file_path: str,
    level: int,
    tile_x: int,
    tile_y: int,
) -> bool:
    """Queue one missing tile without restarting a completed pyramid."""
    path_target = _target_tile_path_for_file(file_path, level, tile_x, tile_y)
    if _tile_result_exists(path_target) or not tiles_marker_matches_file(filename, file_path):
        return False

    key = _completed_cache_repair_key(file_path, level, tile_x, tile_y)
    with _priority_lock:
        if key in _completed_cache_repairs:
            return True
        _completed_cache_repairs.add(key)

    def _repair() -> None:
        try:
            generate_priority_single_tile(
                filename,
                file_path,
                level,
                tile_x,
                tile_y,
                store_blank=True,
            )
        except Exception as exc:
            print(
                f"[tile_repair] failed: {filename} "
                f"S{level} {tile_x},{tile_y}: {exc}"
            )
        finally:
            with _priority_lock:
                _completed_cache_repairs.discard(key)

    try:
        from app.cpu_layout import viewer_executor

        viewer_executor.submit(_repair)
    except Exception:
        with _priority_lock:
            _completed_cache_repairs.discard(key)
        raise
    return True


def _get_priority_block_lock(progress_key: str, tx2: int, ty2: int) -> threading.Lock:
    key = (progress_key, tx2, ty2)
    with _priority_lock:
        lock = _priority_block_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _priority_block_locks[key] = lock
        return lock


def request_priority_tile(filename: str, file_path: str, level: int, tile_x: int, tile_y: int) -> None:
    """Prioritize the stage-1 block(s) that contain a viewer-requested tile."""
    if tiles_marker_matches_file(filename, file_path):
        return
    progress_key = slide_cache_key(file_path)
    with _priority_lock:
        set_priority = _priority_stage1.setdefault(progress_key, set())
        if level == 2:
            for sub_ty in range(2):
                for sub_tx in range(2):
                    set_priority.add((tile_x * 2 + sub_tx, tile_y * 2 + sub_ty))
        else:
            set_priority.add(_stage1_coord_for_tile(level, tile_x, tile_y))
    start_generation(filename, file_path)


def _next_stage1_coord(
    progress_key: str,
    list_all_coords: list[tuple[int, int]],
    set_done: set[tuple[int, int]],
) -> tuple[int, int] | None:
    with _priority_lock:
        set_priority = _priority_stage1.setdefault(progress_key, set())
        for coord in list(set_priority):
            if coord in set_done:
                set_priority.discard(coord)
                continue
            if coord in list_all_coords:
                set_priority.discard(coord)
                return coord
            set_priority.discard(coord)
    for coord in list_all_coords:
        if coord not in set_done:
            return coord
    return None


def _rects_intersect(rect_a: tuple[int, int, int, int], rect_b: tuple[int, int, int, int]) -> bool:
    ax0, ax1, ay0, ay1 = rect_a
    bx0, bx1, by0, by1 = rect_b
    return ax0 <= bx1 and bx0 <= ax1 and ay0 <= by1 and by0 <= ay1


def _stage2_coords_with_data(slide, int_nx2: int, int_ny2: int, int_read_size2: int) -> list[tuple[int, int]]:
    rects = [
        tuple(int(v) for v in rect)
        for rect in getattr(slide, "data_envelope_rectangles", [])
        if len(rect) == 4
    ]
    if not rects:
        return [(tx2, ty2) for ty2 in range(int_ny2) for tx2 in range(int_nx2)]
    coords = []
    for ty2 in range(int_ny2):
        for tx2 in range(int_nx2):
            x0 = tx2 * int_read_size2
            y0 = ty2 * int_read_size2
            block = (x0, x0 + int_read_size2 - 1, y0, y0 + int_read_size2 - 1)
            if any(_rects_intersect(block, rect) for rect in rects):
                coords.append((tx2, ty2))
    return coords


def _stage1_coords_with_data(slide, int_nx1: int, int_ny1: int, int_read_size1: int) -> list[tuple[int, int]]:
    rects = [
        tuple(int(v) for v in rect)
        for rect in getattr(slide, "data_envelope_rectangles", [])
        if len(rect) == 4
    ]
    if not rects:
        return [(tx1, ty1) for ty1 in range(int_ny1) for tx1 in range(int_nx1)]
    coords = []
    for ty1 in range(int_ny1):
        for tx1 in range(int_nx1):
            x0 = tx1 * int_read_size1
            y0 = ty1 * int_read_size1
            block = (x0, x0 + int_read_size1 - 1, y0, y0 + int_read_size1 - 1)
            if any(_rects_intersect(block, rect) for rect in rects):
                coords.append((tx1, ty1))
    return coords


def _tile_intersects_data_envelope(slide, level: int, tile_x: int, tile_y: int) -> bool:
    rects = [
        tuple(int(v) for v in rect)
        for rect in getattr(slide, "data_envelope_rectangles", [])
        if len(rect) == 4
    ]
    if not rects:
        return True
    int_read_size = STAGE_READ_SIZE[level]
    x0 = tile_x * int_read_size
    y0 = tile_y * int_read_size
    tile_rect = (x0, x0 + int_read_size - 1, y0, y0 + int_read_size - 1)
    return any(_rects_intersect(tile_rect, rect) for rect in rects)


def _generate_stage1_block(
    slide,
    _to_srgb,
    stage0_dir: Path,
    stage1_dir: Path,
    tx1: int,
    ty1: int,
    int_nx0: int,
    int_ny0: int,
) -> tuple[bool, int, int]:
    int_read_size1 = STAGE_READ_SIZE[1]
    int_tile_out = TILE_SIZE_OUT
    path_tile1 = stage1_dir / f"{tx1}_{ty1}.jpeg"
    bool_stage1_saved = _tile_result_exists(path_tile1)
    int_stage0_count = 0

    obj_region = slide.read_region(
        (tx1 * int_read_size1, ty1 * int_read_size1),
        0,
        (int_read_size1, int_read_size1),
    )
    obj_rgb = _to_srgb(image_to_white_rgb(obj_region))
    try:
        if not _tile_result_exists(path_tile1):
            obj_tile1 = obj_rgb.resize((int_tile_out, int_tile_out), Image.LANCZOS)
            try:
                if _image_has_visible_content(obj_tile1):
                    _save_jpeg(obj_tile1, path_tile1, settings.TILE_QUALITY)
                else:
                    _mark_blank_tile(path_tile1)
                bool_stage1_saved = True
            finally:
                obj_tile1.close()

        for sub_ty in range(4):
            for sub_tx in range(4):
                tx0 = tx1 * 4 + sub_tx
                ty0 = ty1 * 4 + sub_ty
                if tx0 >= int_nx0 or ty0 >= int_ny0:
                    continue
                path_tile0 = stage0_dir / f"{tx0}_{ty0}.jpeg"
                if _tile_result_exists(path_tile0):
                    int_stage0_count += 1
                    continue
                int_bx = sub_tx * int_tile_out
                int_by = sub_ty * int_tile_out
                obj_tile0 = obj_rgb.crop(
                    (int_bx, int_by, int_bx + int_tile_out, int_by + int_tile_out)
                )
                try:
                    if _image_has_visible_content(obj_tile0):
                        _save_jpeg(obj_tile0, path_tile0, settings.TILE_QUALITY)
                    else:
                        _mark_blank_tile(path_tile0)
                    int_stage0_count += 1
                finally:
                    obj_tile0.close()
        return _tile_result_exists(path_tile1), int_stage0_count, 1
    finally:
        obj_region.close()
        try:
            obj_rgb.close()
        except Exception:
            pass


def _compose_stage2_from_stage1(
    stage1_dir: Path,
    stage2_dir: Path,
    tx2: int,
    ty2: int,
    int_nx1: int,
    int_ny1: int,
    *,
    require_all_children: bool,
) -> bool:
    path_tile2 = stage2_dir / f"{tx2}_{ty2}.jpeg"
    if _tile_result_exists(path_tile2):
        return True

    int_tile_out = TILE_SIZE_OUT
    list_children: list[tuple[int, int, Path]] = []
    bool_all_children_ready = True
    int_expected_children = 0
    for sub_ty in range(2):
        for sub_tx in range(2):
            tx1 = tx2 * 2 + sub_tx
            ty1 = ty2 * 2 + sub_ty
            if tx1 >= int_nx1 or ty1 >= int_ny1:
                continue
            int_expected_children += 1
            path_child = stage1_dir / f"{tx1}_{ty1}.jpeg"
            bool_child_ready = _tile_result_exists(path_child)
            bool_all_children_ready = bool_all_children_ready and bool_child_ready
            if require_all_children and not bool_child_ready:
                return False
            if path_child.exists():
                list_children.append((sub_tx, sub_ty, path_child))

    if not list_children:
        if int_expected_children > 0 and bool_all_children_ready:
            _mark_blank_tile(path_tile2)
            return True
        return False

    obj_canvas = Image.new("RGB", (int_tile_out * 2, int_tile_out * 2), (255, 255, 255))
    try:
        for sub_tx, sub_ty, path_child in list_children:
            with Image.open(str(path_child)) as obj_child:
                obj_rgb = obj_child.convert("RGB")
                try:
                    obj_canvas.paste(obj_rgb, (sub_tx * int_tile_out, sub_ty * int_tile_out))
                finally:
                    obj_rgb.close()
        obj_tile2 = obj_canvas.resize((int_tile_out, int_tile_out), Image.LANCZOS)
        try:
            if _image_has_visible_content(obj_tile2):
                _save_jpeg(obj_tile2, path_tile2, settings.TILE_QUALITY)
            else:
                _mark_blank_tile(path_tile2)
        finally:
            obj_tile2.close()
        return _tile_result_exists(path_tile2)
    finally:
        obj_canvas.close()


def generate_priority_single_tile(
    filename: str,
    file_path: str,
    level: int,
    tile_x: int,
    tile_y: int,
    slide=None,
    apply_color=None,
    store_blank: bool = False,
) -> bool:
    """Generate only the viewer-requested tile instead of a whole stage-2 block."""
    path_target = _target_tile_path_for_file(file_path, level, tile_x, tile_y)
    if _tile_result_exists(path_target):
        if not (get_tiles_dir_for_path(file_path) / COMPLETE_MARKER_NAME).exists() or tiles_marker_matches_file(filename, file_path):
            return True
        invalidate_tiles(filename, file_path)
    if level < 0 or level >= STAGE_COUNT:
        return False

    tx2, ty2 = _stage2_coord_for_tile(level, tile_x, tile_y)
    progress_key = slide_cache_key(file_path)
    lock = _get_priority_block_lock(progress_key, tx2, ty2)
    with lock:
        if _tile_result_exists(path_target):
            if not (get_tiles_dir_for_path(file_path) / COMPLETE_MARKER_NAME).exists() or tiles_marker_matches_file(filename, file_path):
                return True
            invalidate_tiles(filename, file_path)

        bool_close_slide = slide is None
        if slide is None:
            slide = _open_slide(file_path)
        try:
            if apply_color is None:
                _to_srgb, _ = build_color_corrector(slide)
            else:
                _to_srgb = apply_color
            int_w0, int_h0 = slide.dimensions
            int_read_size = STAGE_READ_SIZE[level]
            int_nx = max(1, math.ceil(int_w0 / int_read_size))
            int_ny = max(1, math.ceil(int_h0 / int_read_size))
            if tile_x < 0 or tile_y < 0 or tile_x >= int_nx or tile_y >= int_ny:
                return False
            if not _tile_intersects_data_envelope(slide, level, tile_x, tile_y):
                return False

            obj_region = read_region_for_output(
                slide,
                (tile_x * int_read_size, tile_y * int_read_size),
                (int_read_size, int_read_size),
                (TILE_SIZE_OUT, TILE_SIZE_OUT),
            )
            obj_rgb = _to_srgb(image_to_white_rgb(obj_region))
            try:
                if obj_rgb.size != (TILE_SIZE_OUT, TILE_SIZE_OUT):
                    obj_tile = obj_rgb.resize((TILE_SIZE_OUT, TILE_SIZE_OUT), Image.LANCZOS)
                else:
                    obj_tile = obj_rgb
                try:
                    if store_blank or _image_has_visible_content(obj_tile):
                        _save_jpeg(obj_tile, path_target, settings.TILE_QUALITY)
                    else:
                        _mark_blank_tile(path_target)
                finally:
                    if obj_tile is not obj_rgb:
                        obj_tile.close()
                return _tile_result_exists(path_target)
            finally:
                obj_region.close()
                try:
                    obj_rgb.close()
                except Exception:
                    pass
        finally:
            if bool_close_slide:
                try:
                    slide.close()
                except Exception:
                    pass


def generate_priority_tile_block(
    filename: str,
    file_path: str,
    level: int,
    tile_x: int,
    tile_y: int,
    slide=None,
    apply_color=None,
) -> bool:
    """Generate the stage-1 block(s) needed for a requested tile immediately."""
    path_target = _target_tile_path_for_file(file_path, level, tile_x, tile_y)
    if _tile_result_exists(path_target):
        if not (get_tiles_dir_for_path(file_path) / COMPLETE_MARKER_NAME).exists() or tiles_marker_matches_file(filename, file_path):
            return True
        invalidate_tiles(filename, file_path)

    tx2, ty2 = _stage2_coord_for_tile(level, tile_x, tile_y)
    progress_key = slide_cache_key(file_path)
    lock = _get_priority_block_lock(progress_key, tx2, ty2)
    with lock:
        if _tile_result_exists(path_target):
            if not (get_tiles_dir_for_path(file_path) / COMPLETE_MARKER_NAME).exists() or tiles_marker_matches_file(filename, file_path):
                return True
            invalidate_tiles(filename, file_path)

        bool_close_slide = slide is None
        if slide is None:
            slide = _open_slide(file_path)
        try:
            if apply_color is None:
                _to_srgb, _ = build_color_corrector(slide)
            else:
                _to_srgb = apply_color

            int_w0, int_h0 = slide.dimensions
            list_stage_nx = []
            list_stage_ny = []
            for int_stage in range(STAGE_COUNT):
                int_scene_tile = STAGE_READ_SIZE[int_stage]
                list_stage_nx.append(max(1, math.ceil(int_w0 / int_scene_tile)))
                list_stage_ny.append(max(1, math.ceil(int_h0 / int_scene_tile)))

            tiles_dir = get_tiles_dir_for_path(file_path)
            for int_stage in range(STAGE_COUNT):
                (tiles_dir / str(int_stage)).mkdir(parents=True, exist_ok=True)
            stage0_dir = tiles_dir / "0"
            stage1_dir = tiles_dir / "1"
            stage2_dir = tiles_dir / "2"

            int_read_size1 = STAGE_READ_SIZE[1]
            int_nx1 = list_stage_nx[1]
            int_ny1 = list_stage_ny[1]
            int_nx0 = list_stage_nx[0]
            int_ny0 = list_stage_ny[0]
            list_stage1_coords = _stage1_coords_with_data(slide, int_nx1, int_ny1, int_read_size1)
            set_stage1_coords = set(list_stage1_coords)

            if level == 2:
                coords_needed = [
                    (tile_x * 2 + sub_tx, tile_y * 2 + sub_ty)
                    for sub_ty in range(2)
                    for sub_tx in range(2)
                    if tile_x * 2 + sub_tx < int_nx1 and tile_y * 2 + sub_ty < int_ny1
                ]
            else:
                coords_needed = [_stage1_coord_for_tile(level, tile_x, tile_y)]

            bool_generated_any = False
            for tx1, ty1 in coords_needed:
                if tx1 < 0 or ty1 < 0 or tx1 >= int_nx1 or ty1 >= int_ny1:
                    continue
                if (tx1, ty1) not in set_stage1_coords:
                    continue
                _generate_stage1_block(slide, _to_srgb, stage0_dir, stage1_dir, tx1, ty1, int_nx0, int_ny0)
                bool_generated_any = True

            if level == 2:
                _compose_stage2_from_stage1(
                    stage1_dir,
                    stage2_dir,
                    tile_x,
                    tile_y,
                    int_nx1,
                    int_ny1,
                    require_all_children=False,
                )
            else:
                parent_tx2, parent_ty2 = _stage2_coord_for_tile(level, tile_x, tile_y)
                _compose_stage2_from_stage1(
                    stage1_dir,
                    stage2_dir,
                    parent_tx2,
                    parent_ty2,
                    int_nx1,
                    int_ny1,
                    require_all_children=True,
                )

            return _tile_result_exists(path_target) or bool_generated_any
        finally:
            if bool_close_slide:
                try:
                    slide.close()
                except Exception:
                    pass


def _generate_tiles(filename: str, file_path: str):
    """text text text ??text text(text text)text text text text text text text"""
    progress = TileGenProgress()
    progress_key = slide_cache_key(file_path)
    with _progress_lock:
        _progress[progress_key] = progress

    tiles_dir = get_tiles_dir_for_path(file_path)
    bool_completed = False

    try:
        if tiles_dir.exists() and (tiles_dir / COMPLETE_MARKER_NAME).exists() and not tiles_are_valid(filename, file_path):
            shutil.rmtree(tiles_dir, ignore_errors=True)
        slide = _open_slide(file_path)

        # text text text callable (ICC ??NDP LUT ??raw text).
        # text text ICC text "text text text" text ??transform text
        # text text text text text text.
        str_icc_hash = _slide_icc_hash(slide)
        _to_srgb, dict_color_meta = build_color_corrector(slide)
        bool_icc_applied = bool(dict_color_meta.get("icc_applied"))
        if str_icc_hash is not None and not bool_icc_applied:
            print(f"[tile_generator] WARN {filename}: ICC profile detected but no color transform was applied")
        # NDP LUT text text text text text text text ??text.

        # 3text stage text ??text level 0 text text downsample [1, 4, 8] text text
        int_w0, int_h0 = slide.dimensions

        # text stage text text text (nx, ny) text
        list_stage_nx = []
        list_stage_ny = []
        int_total_tiles = 0
        for int_stage in range(STAGE_COUNT):
            int_scene_tile = STAGE_READ_SIZE[int_stage]
            int_nx = max(1, math.ceil(int_w0 / int_scene_tile))
            int_ny = max(1, math.ceil(int_h0 / int_scene_tile))
            list_stage_nx.append(int_nx)
            list_stage_ny.append(int_ny)
            int_total_tiles += int_nx * int_ny

        progress.total_tiles = int_total_tiles
        progress.status = "generating"

        # text text text
        generate_standard_thumbnail_cache(
            slide,
            tiles_dir,
            apply_color=_to_srgb,
        )

        # stage text text
        for int_stage in range(STAGE_COUNT):
            (tiles_dir / str(int_stage)).mkdir(parents=True, exist_ok=True)
        stage0_dir = tiles_dir / "0"
        stage1_dir = tiles_dir / "1"
        stage2_dir = tiles_dir / "2"

        int_read_size2 = STAGE_READ_SIZE[2]   # 8192
        int_read_size1 = STAGE_READ_SIZE[1]   # 4096
        int_nx2 = list_stage_nx[2]
        int_ny2 = list_stage_ny[2]
        int_nx1 = list_stage_nx[1]
        int_ny1 = list_stage_ny[1]
        int_nx0 = list_stage_nx[0]
        int_ny0 = list_stage_ny[0]

        list_stage1_coords = _stage1_coords_with_data(slide, int_nx1, int_ny1, int_read_size1)
        set_done_stage1: set[tuple[int, int]] = set()
        while len(set_done_stage1) < len(list_stage1_coords):
            coord_stage1 = _next_stage1_coord(progress_key, list_stage1_coords, set_done_stage1)
            if coord_stage1 is None:
                break
            tx1, ty1 = coord_stage1
            set_done_stage1.add(coord_stage1)

            progress.current_level = 1
            _generate_stage1_block(slide, _to_srgb, stage0_dir, stage1_dir, tx1, ty1, int_nx0, int_ny0)
            progress.generated_tiles += 1

            progress.current_level = 0
            for sub_ty in range(4):
                for sub_tx in range(4):
                    tx0 = tx1 * 4 + sub_tx
                    ty0 = ty1 * 4 + sub_ty
                    if tx0 < int_nx0 and ty0 < int_ny0:
                        progress.generated_tiles += 1

        progress.current_level = 2
        list_stage2_coords = _stage2_coords_with_data(slide, int_nx2, int_ny2, int_read_size2)
        for tx2, ty2 in list_stage2_coords:
            _compose_stage2_from_stage1(
                stage1_dir,
                stage2_dir,
                tx2,
                ty2,
                int_nx1,
                int_ny1,
                require_all_children=False,
            )
            progress.generated_tiles += 1

        # text text ??text text ICC text + text text text text
        _write_complete_marker(
            tiles_dir,
            str_icc_hash=str_icc_hash,
            bool_icc_applied=bool_icc_applied,
            slide=slide,
            file_path=file_path,
        )
        bool_completed = True
        progress.generated_tiles = progress.total_tiles
        progress.status = "completed"
        slide.close()

        # DB text text (text text ??text text text)
        try:
            from app import slide_store
            slide_store.mark_tiles_ready_threadsafe(file_path)
        except Exception as e:
            print(f"[tile_generator] mark_tiles_ready failed ({filename}): {e}")

    except Exception as e:
        progress.status = "error"
        progress.error = str(e)
    finally:
        # text text text ??text text text text text .complete text
        # text text text text. text text tiles_are_valid text
        # False text text invalidate_tiles text text text, text text
        # text 404/text text text text text text text text text.
        # thumbnail text text text text text text overwrite text text text.
        if not bool_completed and tiles_dir.exists():
            try:
                shutil.rmtree(tiles_dir, ignore_errors=True)
                print(f"[tile_generator] removed incomplete tile directory: {tiles_dir}")
            except Exception as exc_cleanup:
                print(f"[tile_generator] cleanup failed ({filename}): {exc_cleanup}")

        # text text text text text progress text
        def _cleanup():
            time.sleep(60)
            with _progress_lock:
                _progress.pop(progress_key, None)
        threading.Thread(target=_cleanup, daemon=True).start()
