"""
text text — 3text stage text level 0 text text text.

text:
  tiles/{slide_id}/
    ├── 0/{tx}_{ty}.jpeg    ← stage 0 (downsample 1, text text)
    ├── 1/{tx}_{ty}.jpeg    ← stage 1 (downsample 4, level0→4096px text 1024 text)
    ├── 2/{tx}_{ty}.jpeg    ← stage 2 (downsample 8, level0→8192px text 1024 text)
    ├── thumbnail.jpeg
    └── .complete           ← text text text (JSON: text/ICC text/text text)

text text:
  stage 2 text text(8192x8192 at level 0) text text text text text
    - stage 2 tile 1text (text 8192→1024 text)
    - stage 1 tile 4text (4text 4096 text → text 1024 text)
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
from app.slide_manager import (
    STAGE_READ_SIZE,
    STAGE_COUNT,
    TILE_SIZE_OUT,
    build_color_corrector,
)

_thumb_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="thumb")

TILE_SIZE = TILE_SIZE_OUT

# .complete marker schema version. Bump when the on-disk tile format changes
# in a way that requires regeneration.
# v2: 3text stage text (level 0 text) — text level-index text text text
# v3: Hamamatsu NDP.view2 text gamma=1.8 + Target.White.Intensity LUT text —
#     text raw-pass-through text text text text text text.
COMPLETE_MARKER_VERSION = 4
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
        print(f"[tile_generator] icc hash text text: {e}")
        return None


def read_complete_marker(filename: str) -> Optional[dict]:
    """text JSON text text text. text text/textJSON(legacy touch)/text text text None."""
    path = get_tiles_dir(filename) / COMPLETE_MARKER_NAME
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
) -> None:
    """text JSON text. _generate_tiles text text text."""
    dict_marker = {
        "version": COMPLETE_MARKER_VERSION,
        "icc_hash": str_icc_hash,
        "icc_applied": bool(bool_icc_applied),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (tiles_dir / COMPLETE_MARKER_NAME).write_text(
        json.dumps(dict_marker, ensure_ascii=False),
        encoding="utf-8",
    )


def tiles_are_valid(filename: str, file_path: str) -> bool:
    """text text text text text text text.

    - text text / text touch text / text text → False (text text)
    - text icc_hash text text text ICC text text → False
    - text icc_applied=False text text text ICC text text → False
    - text text text → True (text text text; text text)

    text: text text text text text text text. text text _generate_tiles text
    text text, text text text text text text.
    """
    tiles_dir = get_tiles_dir(filename)
    if not tiles_dir.exists():
        return False
    dict_marker = read_complete_marker(filename)
    if dict_marker is None:
        return False
    if dict_marker.get("version") != COMPLETE_MARKER_VERSION:
        return False
    try:
        slide = openslide.OpenSlide(file_path)
    except Exception as e:
        print(f"[tile_generator] tiles_are_valid: OpenSlide text ({filename}): {e}")
        return True  # text text — text text text
    try:
        str_current_hash = _slide_icc_hash(slide)
    finally:
        try:
            slide.close()
        except Exception:
            pass

    str_marker_hash = dict_marker.get("icc_hash")
    if str_marker_hash != str_current_hash:
        return False
    # text text text text text ICC text text text: text text text
    # text text text. text text text text text valid text text.
    # text(PIL/openslide)text text text text text text tile dir text text text.
    return True


def invalidate_tiles(filename: str) -> None:
    """text text text text — text text text."""
    tiles_dir = get_tiles_dir(filename)
    if tiles_dir.exists():
        shutil.rmtree(tiles_dir, ignore_errors=True)


# ── text text ──

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


def get_tiles_dir(filename: str) -> Path:
    """text text text text text (text text)"""
    stem = Path(filename).stem
    return Path(settings.TILES_DIR) / stem


def tiles_ready(filename: str) -> bool:
    """text text text text"""
    return (get_tiles_dir(filename) / ".complete").exists()


def get_progress(filename: str) -> Optional[dict]:
    """text text text (text None)"""
    with _progress_lock:
        p = _progress.get(filename)
        if p:
            return p.to_dict()
    # text text text
    if tiles_ready(filename):
        return {"status": "completed", "progress": 100,
                "total_tiles": 0, "generated_tiles": 0,
                "current_level": -1, "error": None}
    return None


def start_generation(filename: str, file_path: str):
    """text text text text text (text text/text text text)"""
    if tiles_ready(filename):
        return

    with _progress_lock:
        if filename in _progress and _progress[filename].status == "generating":
            return  # text text text

    from app.cpu_layout import tile_executor
    tile_executor.submit(_generate_tiles, filename, file_path)


def _generate_tiles(filename: str, file_path: str):
    """text text text — text text(text text)text text text text text text text"""
    progress = TileGenProgress()
    with _progress_lock:
        _progress[filename] = progress

    tiles_dir = get_tiles_dir(filename)
    bool_completed = False

    try:
        slide = openslide.OpenSlide(file_path)

        # text text text callable (ICC → NDP LUT → raw text).
        # text text ICC text "text text text" text — transform text
        # text text text text text text.
        str_icc_hash = _slide_icc_hash(slide)
        _to_srgb, dict_color_meta = build_color_corrector(slide)
        bool_icc_applied = bool(dict_color_meta.get("icc_applied"))
        if str_icc_hash is not None and not bool_icc_applied:
            print(f"[tile_generator] WARN {filename}: ICC text text transform text text — ICC text")
        # NDP LUT text text text text text text text — text.

        # 3text stage text — text level 0 text text downsample [1, 4, 8] text text
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
        thumb_path = tiles_dir / "thumbnail.jpeg"
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        if not thumb_path.exists():
            thumb = slide.get_thumbnail((300, 300))
            thumb_rgb = _to_srgb(image_to_white_rgb(thumb))
            try:
                thumb_rgb.save(str(thumb_path), "JPEG", quality=85)
            finally:
                try:
                    thumb_rgb.close()
                except Exception:
                    pass
                try:
                    thumb.close()
                except Exception:
                    pass

        # stage text text
        for int_stage in range(STAGE_COUNT):
            (tiles_dir / str(int_stage)).mkdir(parents=True, exist_ok=True)
        stage0_dir = tiles_dir / "0"
        stage1_dir = tiles_dir / "1"
        stage2_dir = tiles_dir / "2"

        int_read_size2 = STAGE_READ_SIZE[2]   # 8192
        int_read_size1 = STAGE_READ_SIZE[1]   # 4096
        int_tile_out = TILE_SIZE_OUT          # 1024
        int_nx2 = list_stage_nx[2]
        int_ny2 = list_stage_ny[2]
        int_nx1 = list_stage_nx[1]
        int_ny1 = list_stage_ny[1]
        int_nx0 = list_stage_nx[0]
        int_ny0 = list_stage_ny[0]

        # stage 2 text text — text text level 0 text 8192x8192 text text text
        # stage 2/1/0 text text text text (69 tile / 1 read).
        for ty2 in range(int_ny2):
            for tx2 in range(int_nx2):
                progress.current_level = 2
                int_sx = tx2 * int_read_size2
                int_sy = ty2 * int_read_size2

                obj_region = slide.read_region(
                    (int_sx, int_sy), 0, (int_read_size2, int_read_size2)
                )
                obj_rgb = _to_srgb(image_to_white_rgb(obj_region))

                # ── stage 2 tile (8192 → 1024) ──
                tile_path2 = stage2_dir / f"{tx2}_{ty2}.jpeg"
                if not tile_path2.exists():
                    obj_tile2 = obj_rgb.resize(
                        (int_tile_out, int_tile_out), Image.LANCZOS
                    )
                    obj_tile2.save(
                        str(tile_path2), "JPEG", quality=settings.TILE_QUALITY
                    )
                    obj_tile2.close()
                progress.generated_tiles += 1

                # ── stage 1 sub-tiles (2x2, text 4096 → 1024) ──
                progress.current_level = 1
                for sub_ty in range(2):
                    for sub_tx in range(2):
                        tx1 = tx2 * 2 + sub_tx
                        ty1 = ty2 * 2 + sub_ty
                        if tx1 >= int_nx1 or ty1 >= int_ny1:
                            continue
                        tile_path1 = stage1_dir / f"{tx1}_{ty1}.jpeg"
                        if not tile_path1.exists():
                            int_bx = sub_tx * int_read_size1
                            int_by = sub_ty * int_read_size1
                            obj_sub = obj_rgb.crop(
                                (int_bx, int_by,
                                 int_bx + int_read_size1,
                                 int_by + int_read_size1)
                            )
                            obj_tile1 = obj_sub.resize(
                                (int_tile_out, int_tile_out), Image.LANCZOS
                            )
                            obj_tile1.save(
                                str(tile_path1), "JPEG", quality=settings.TILE_QUALITY
                            )
                            obj_tile1.close()
                            obj_sub.close()
                        progress.generated_tiles += 1

                # ── stage 0 sub-tiles (8x8, text 1024 text) ──
                progress.current_level = 0
                for sub_ty in range(8):
                    for sub_tx in range(8):
                        tx0 = tx2 * 8 + sub_tx
                        ty0 = ty2 * 8 + sub_ty
                        if tx0 >= int_nx0 or ty0 >= int_ny0:
                            continue
                        tile_path0 = stage0_dir / f"{tx0}_{ty0}.jpeg"
                        if not tile_path0.exists():
                            int_bx = sub_tx * int_tile_out
                            int_by = sub_ty * int_tile_out
                            obj_tile0 = obj_rgb.crop(
                                (int_bx, int_by,
                                 int_bx + int_tile_out,
                                 int_by + int_tile_out)
                            )
                            obj_tile0.save(
                                str(tile_path0), "JPEG", quality=settings.TILE_QUALITY
                            )
                            obj_tile0.close()
                        progress.generated_tiles += 1

                # text text text text — text text text text text
                obj_region.close()
                try:
                    obj_rgb.close()
                except Exception:
                    pass
                del obj_region, obj_rgb

        # text text — text text ICC text + text text text text
        _write_complete_marker(
            tiles_dir,
            str_icc_hash=str_icc_hash,
            bool_icc_applied=bool_icc_applied,
        )
        bool_completed = True
        progress.status = "completed"
        slide.close()

        # DB text text (text text → text text text)
        try:
            from app import slide_store
            slide_store.mark_tiles_ready_threadsafe(file_path)
        except Exception as e:
            print(f"[tile_generator] mark_tiles_ready failed ({filename}): {e}")

    except Exception as e:
        progress.status = "error"
        progress.error = str(e)
    finally:
        # text text text — text text text text text .complete text
        # text text text text. text text tiles_are_valid text
        # False text text invalidate_tiles text text text, text text
        # text 404/text text text text text text text text text.
        # thumbnail text text text text text text overwrite text text text.
        if not bool_completed and tiles_dir.exists():
            try:
                shutil.rmtree(tiles_dir, ignore_errors=True)
                print(f"[tile_generator] text text → {tiles_dir} text")
            except Exception as exc_cleanup:
                print(f"[tile_generator] cleanup text ({filename}): {exc_cleanup}")

        # text text text text text progress text
        def _cleanup():
            time.sleep(60)
            with _progress_lock:
                _progress.pop(filename, None)
        threading.Thread(target=_cleanup, daemon=True).start()
