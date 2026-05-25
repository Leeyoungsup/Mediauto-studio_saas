"""
SlideManager — text text text text (text text)
OpenSlide text text text text text text text text text
"""

import math
import os
import threading
import time
from typing import Optional, Dict, Tuple

import numpy as np
import openslide

MAX_OPEN_SLIDES = max(1, int(os.environ.get("MAX_OPEN_SLIDES", "4")))
IDLE_SLIDE_TTL_SECONDS = max(30, int(os.environ.get("IDLE_SLIDE_TTL_SECONDS", "300")))

# ── Hamamatsu NDP.view2 text text text text ──
# NDP.view2 text text gamma = 1.8 text + text Target.White.Intensity text text.
# ICC text text text Hamamatsu text text
#   v_out = 255 * (v_in / Target.White.Intensity) ^ (1/1.8)
# text text raw text NDP.view2 text text text text.
# Target.White.Intensity text text header text text text — .npy text text text text.
FLOAT_NDP_GAMMA = 1.8
FLOAT_NDP_DEFAULT_WHITE = 235.0


def _build_ndp_lut(float_raw_white: float) -> np.ndarray:
    """raw_white → 255, gamma=1.8 text 256-entry uint8 LUT."""
    if float_raw_white <= 0:
        float_raw_white = FLOAT_NDP_DEFAULT_WHITE
    np_x = np.clip(np.arange(256, dtype=np.float32) / float_raw_white, 0.0, 1.0)
    np_y = np.power(np_x, 1.0 / FLOAT_NDP_GAMMA) * 255.0
    return np.clip(np_y, 0, 255).astype(np.uint8)


def build_color_corrector(slide: "openslide.OpenSlide"):
    """OpenSlide text text text text text callable text text.

    text:
      1) ICC profile text text sRGB ImageCms transform text
      2) ICC text text vendor=hamamatsu text Target.White.Intensity + γ=1.8 LUT text
      3) text text text pass-through

    text: `(apply, dict_meta)`
      - apply(img_rgb: PIL.Image) -> PIL.Image
      - dict_meta:
          {
            "icc_applied": bool,
            "ndp_applied": bool,
            "ndp_white": float | None,
            "str_tag": "icc" | "ndp:<white>" | "raw",
          }

    text text text `SlideInfo`, `tile_generator`, `thumbnail-by-name` text text
    text text text text text text.
    """
    # 1) ICC transform
    icc_transform = None
    try:
        obj_profile = getattr(slide, "color_profile", None)
        if obj_profile is not None:
            from PIL import ImageCms
            obj_srgb = ImageCms.createProfile("sRGB")
            icc_transform = ImageCms.buildTransform(
                obj_profile, obj_srgb, "RGB", "RGB"
            )
    except Exception as e:
        print(f"[slide_manager] ICC transform text: {e}")
        icc_transform = None

    # 2) NDP LUT (ICC text vendor=hamamatsu text text)
    np_lut: Optional[np.ndarray] = None
    float_ndp_white: Optional[float] = None
    if icc_transform is None:
        str_vendor = str(slide.properties.get("openslide.vendor", "")).lower()
        if str_vendor == "hamamatsu":
            try:
                float_ndp_white = float(slide.properties.get(
                    "hamamatsu.Target.White.Intensity", FLOAT_NDP_DEFAULT_WHITE
                ))
            except (TypeError, ValueError):
                float_ndp_white = FLOAT_NDP_DEFAULT_WHITE
            np_lut = _build_ndp_lut(float_ndp_white)

    # 3) apply callable
    def _apply(img_rgb):
        if icc_transform is not None:
            try:
                from PIL import ImageCms
                return ImageCms.applyTransform(img_rgb, icc_transform)
            except Exception:
                return img_rgb
        if np_lut is not None:
            try:
                from PIL import Image
                np_img = np.asarray(img_rgb, dtype=np.uint8)
                np_out = np_lut[np_img]
                return Image.fromarray(np_out, "RGB")
            except Exception as e:
                print(f"[slide_manager] NDP LUT text text: {e}")
                return img_rgb
        return img_rgb

    dict_meta = {
        "icc_applied": icc_transform is not None,
        "ndp_applied": np_lut is not None,
        "ndp_white": float_ndp_white,
        "str_tag": (
            "icc" if icc_transform is not None
            else (f"ndp:{int(float_ndp_white)}" if np_lut is not None else "raw")
        ),
    }
    return _apply, dict_meta


# ── 3text text text ──
# text stage text level 0 text text downsample text text 1024x1024 text text.
#   stage 0 : level0 text 1024x1024 text (downsample 1)
#   stage 1 : level0 text 4096x4096 text 1024x1024 text text (downsample 4)
#   stage 2 : level0 text 8192x8192 text 1024x1024 text text (downsample 8)
# TileViewer text STAGE_DOWNSAMPLES / STAGE_READ_SIZE text text text text.
STAGE_DOWNSAMPLES = [1, 4, 8]
TILE_SIZE_OUT = 1024
STAGE_READ_SIZE = [TILE_SIZE_OUT * ds for ds in STAGE_DOWNSAMPLES]  # [1024, 4096, 8192]
STAGE_COUNT = len(STAGE_DOWNSAMPLES)


class SlideInfo:
    """text text text text"""

    def __init__(self, slide: openslide.OpenSlide, file_path: str):
        self.slide = slide
        self.file_path = file_path
        self.opened_at = time.time()
        self.last_accessed = time.time()

        # text text
        self.dimensions = slide.dimensions
        self.level_count = slide.level_count
        self.level_dimensions = list(slide.level_dimensions)
        self.level_downsamples = list(slide.level_downsamples)

        # MPP
        mpp_x = slide.properties.get("openslide.mpp-x")
        mpp_y = slide.properties.get("openslide.mpp-y")
        if mpp_x and mpp_y:
            self.mpp_x = float(mpp_x)
            self.mpp_y = float(mpp_y)
            self.mpp = (self.mpp_x + self.mpp_y) / 2
        else:
            self.mpp_x = 0.25
            self.mpp_y = 0.25
            self.mpp = 0.25  # text (40x)

        # text text
        self.objective_power = slide.properties.get("openslide.objective-power", "Unknown")

        self.vendor = slide.properties.get("openslide.vendor", "Unknown")

        # text text text — ICC → NDP LUT → raw text.
        # AI text text text `icc_transform` text text text text text text
        # text ImageCms transform text text text. text/text/text text
        # `apply_icc()` text text text callable (ICC + NDP LUT) text text.
        self._color_apply, self._color_meta = build_color_corrector(slide)
        self.icc_transform = None
        try:
            obj_profile = getattr(slide, "color_profile", None)
            if obj_profile is not None:
                from PIL import ImageCms
                obj_srgb = ImageCms.createProfile("sRGB")
                self.icc_transform = ImageCms.buildTransform(
                    obj_profile, obj_srgb, "RGB", "RGB"
                )
        except Exception:
            self.icc_transform = None
        # NDP LUT text text self._color_meta text text — text text text text text X.

        # text text (mm)
        w, h = self.dimensions
        self.physical_width_mm = w * self.mpp_x / 1000.0
        self.physical_height_mm = h * self.mpp_y / 1000.0

        # 3text stage text text text (level 0 text text downsample [1,4,8])
        self.stage_downsamples = list(STAGE_DOWNSAMPLES)
        self.stage_count = STAGE_COUNT
        # text stage text text text — frontend text nx/ny text text
        w0, h0 = self.dimensions
        self.stage_dimensions = [
            (max(1, math.ceil(w0 / ds)), max(1, math.ceil(h0 / ds)))
            for ds in STAGE_DOWNSAMPLES
        ]

    def get_stage(self, effective_mpp: float) -> int:
        """effective MPP text stage index (0/1/2) text."""
        if effective_mpp < 2.0:
            return 0
        elif effective_mpp < 15.0:
            return 1
        else:
            return 2

    # text text — text /stage-level text. stage index text text text.
    def get_stage_level(self, effective_mpp: float) -> int:
        return self.get_stage(effective_mpp)

    def touch(self):
        self.last_accessed = time.time()

    def apply_icc(self, img_rgb):
        """RGB PIL text text text text (ICC → NDP LUT → raw text)."""
        return self._color_apply(img_rgb)


class SlideManager:
    """text text text (thread-safe).

    Generation counter:
        text slide_id text text text text generation text text. close() text text
        text slide_id text generation text +1 text. text text thread-local
        text text text (app.thread_slide_pool) text generation text text
        stale text text text text text leak text text.
    """

    def __init__(self):
        self._slides: Dict[str, SlideInfo] = {}
        self._generations: Dict[str, int] = {}
        self._lock = threading.Lock()

    def _close_info_locked(self, slide_id: str, info: SlideInfo) -> None:
        self._generations[slide_id] = self._generations.get(slide_id, 0) + 1
        try:
            info.slide.close()
        except Exception:
            pass

    def _evict_idle_locked(self, exclude_slide_id: str = "") -> None:
        """Close idle or least-recently-used OpenSlide handles."""
        float_now = time.time()
        for str_sid, info in list(self._slides.items()):
            if str_sid == exclude_slide_id:
                continue
            if info.last_accessed + IDLE_SLIDE_TTL_SECONDS <= float_now:
                self._slides.pop(str_sid, None)
                self._close_info_locked(str_sid, info)

        while len(self._slides) > MAX_OPEN_SLIDES:
            list_candidates = [
                (str_sid, info)
                for str_sid, info in self._slides.items()
                if str_sid != exclude_slide_id
            ]
            if not list_candidates:
                break
            str_evict_id, info_evict = min(list_candidates, key=lambda item: item[1].last_accessed)
            self._slides.pop(str_evict_id, None)
            self._close_info_locked(str_evict_id, info_evict)

    def open(self, slide_id: str, file_path: str) -> SlideInfo:
        """text text (text text text text)"""
        with self._lock:
            if slide_id in self._slides:
                info = self._slides[slide_id]
                info.touch()
                self._evict_idle_locked(exclude_slide_id=slide_id)
                return info

            slide = openslide.OpenSlide(file_path)
            info = SlideInfo(slide, file_path)
            self._slides[slide_id] = info
            # text open text generation 0 text (text text text)
            self._generations.setdefault(slide_id, 0)
            self._evict_idle_locked(exclude_slide_id=slide_id)
            return info

    def get(self, slide_id: str) -> Optional[SlideInfo]:
        """text text text"""
        with self._lock:
            info = self._slides.get(slide_id)
            if info:
                info.touch()
                self._evict_idle_locked(exclude_slide_id=slide_id)
            return info

    def get_generation(self, slide_id: str) -> int:
        """text slide_id text text generation. thread-local text text text."""
        with self._lock:
            return self._generations.get(slide_id, 0)

    def close(self, slide_id: str):
        """text text — generation text bump text text thread-local text text."""
        with self._lock:
            info = self._slides.pop(slide_id, None)
            if info:
                self._close_info_locked(slide_id, info)

    def close_all(self):
        """text text text — text generation bump."""
        with self._lock:
            for str_sid in list(self._slides.keys()):
                self._generations[str_sid] = self._generations.get(str_sid, 0) + 1
            for info in self._slides.values():
                try:
                    info.slide.close()
                except Exception:
                    pass
            self._slides.clear()

    def list_slides(self):
        """text text text"""
        with self._lock:
            return {
                sid: {
                    "file_path": info.file_path,
                    "dimensions": info.dimensions,
                    "level_count": info.level_count,
                    "mpp": info.mpp,
                }
                for sid, info in self._slides.items()
            }


# text
slide_manager = SlideManager()
