"""OpenSlide-compatible adapter for ordinary JPEG slide images.

JPEG files do not contain objective-power or physical pixel-size metadata and
cannot normally be opened by OpenSlide.  MeDIAuto treats uploaded JPG/JPEG
files as 20x images with a fixed 0.5 micrometers-per-pixel calibration.
"""

from __future__ import annotations

import io
import math
import threading
from pathlib import Path

from PIL import Image


FIXED_RASTER_OBJECTIVE_POWER = 20.0
FIXED_RASTER_MPP = 0.5
_RASTER_EXTENSIONS = {".jpg", ".jpeg"}


def is_fixed_magnification_raster(file_path: str | Path) -> bool:
    """Return True for raster formats that use the fixed 20x calibration."""

    return Path(file_path).suffix.lower() in _RASTER_EXTENSIONS


class RasterSlideProxy:
    """Small subset of the OpenSlide API backed by a Pillow JPEG image."""

    def __init__(self, file_path: str | Path):
        self.file_path = str(Path(file_path))
        self._lock = threading.RLock()
        self._closed = False

        obj_image = Image.open(self.file_path)
        try:
            obj_image.load()
            self._image = obj_image.convert("RGB")
            self._icc_bytes = obj_image.info.get("icc_profile")
        finally:
            obj_image.close()

        self.dimensions = tuple(int(v) for v in self._image.size)
        if self.dimensions[0] <= 0 or self.dimensions[1] <= 0:
            self._image.close()
            raise ValueError("JPEG image has invalid dimensions")

        self.level_downsamples = self._build_level_downsamples(self.dimensions)
        self.level_dimensions = [
            (
                max(1, int(math.ceil(self.dimensions[0] / float_downsample))),
                max(1, int(math.ceil(self.dimensions[1] / float_downsample))),
            )
            for float_downsample in self.level_downsamples
        ]
        self.level_count = len(self.level_dimensions)
        self.mpp = FIXED_RASTER_MPP
        self.vendor = "jpeg"
        self.data_envelope_rectangles = [
            (0, self.dimensions[0] - 1, 0, self.dimensions[1] - 1),
        ]
        self.associated_images = {}

        try:
            stat = Path(self.file_path).stat()
            str_quickhash = f"jpeg:{int(stat.st_size)}:{int(stat.st_mtime_ns)}"
        except OSError:
            str_quickhash = ""
        self.properties = {
            "openslide.vendor": self.vendor,
            "openslide.mpp-x": str(FIXED_RASTER_MPP),
            "openslide.mpp-y": str(FIXED_RASTER_MPP),
            "openslide.objective-power": str(int(FIXED_RASTER_OBJECTIVE_POWER)),
            "openslide.quickhash-1": str_quickhash,
            "mediauto.source-format": "JPEG",
            "mediauto.magnification-assumption": "fixed-20x",
        }

        self.color_profile = None
        if self._icc_bytes:
            try:
                from PIL import ImageCms

                self.color_profile = ImageCms.ImageCmsProfile(io.BytesIO(self._icc_bytes))
            except Exception:
                self.color_profile = None

    @staticmethod
    def _build_level_downsamples(dimensions: tuple[int, int]) -> list[float]:
        list_downsamples = [1.0]
        int_width, int_height = dimensions
        while max(
            math.ceil(int_width / list_downsamples[-1]),
            math.ceil(int_height / list_downsamples[-1]),
        ) > 1024:
            list_downsamples.append(list_downsamples[-1] * 2.0)
        return list_downsamples

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("JPEG slide is closed")

    def get_best_level_for_downsample(self, downsample: float) -> int:
        self._ensure_open()
        float_target = max(1.0, float(downsample or 1.0))
        # Match OpenSlide's practical behavior: use the highest-resolution
        # level that does not exceed the requested downsample.
        int_best = 0
        for int_level, float_level_ds in enumerate(self.level_downsamples):
            if float_level_ds > float_target:
                break
            int_best = int_level
        return int_best

    def read_region(
        self,
        location: tuple[int, int],
        level: int,
        size: tuple[int, int],
    ) -> Image.Image:
        """Return an RGBA region using OpenSlide's level-0 location semantics."""

        self._ensure_open()
        int_level = int(level)
        if int_level < 0 or int_level >= self.level_count:
            raise ValueError(f"Invalid JPEG pyramid level: {level}")

        int_out_w = max(0, int(size[0]))
        int_out_h = max(0, int(size[1]))
        if int_out_w == 0 or int_out_h == 0:
            return Image.new("RGBA", (int_out_w, int_out_h), (0, 0, 0, 0))

        float_ds = float(self.level_downsamples[int_level])
        int_x0 = int(location[0])
        int_y0 = int(location[1])
        int_x1 = int_x0 + int(math.ceil(int_out_w * float_ds))
        int_y1 = int_y0 + int(math.ceil(int_out_h * float_ds))
        int_src_w, int_src_h = self.dimensions

        int_ix0 = max(0, int_x0)
        int_iy0 = max(0, int_y0)
        int_ix1 = min(int_src_w, int_x1)
        int_iy1 = min(int_src_h, int_y1)
        obj_output = Image.new("RGBA", (int_out_w, int_out_h), (0, 0, 0, 0))
        if int_ix0 >= int_ix1 or int_iy0 >= int_iy1:
            return obj_output

        with self._lock:
            self._ensure_open()
            obj_crop = self._image.crop((int_ix0, int_iy0, int_ix1, int_iy1))
        try:
            int_scaled_w = max(1, int(round((int_ix1 - int_ix0) / float_ds)))
            int_scaled_h = max(1, int(round((int_iy1 - int_iy0) / float_ds)))
            if obj_crop.size != (int_scaled_w, int_scaled_h):
                obj_scaled = obj_crop.resize(
                    (int_scaled_w, int_scaled_h), Image.Resampling.LANCZOS,
                )
            else:
                obj_scaled = obj_crop
            try:
                int_dest_x = max(0, int(round((int_ix0 - int_x0) / float_ds)))
                int_dest_y = max(0, int(round((int_iy0 - int_y0) / float_ds)))
                obj_output.paste(obj_scaled, (int_dest_x, int_dest_y))
            finally:
                if obj_scaled is not obj_crop:
                    obj_scaled.close()
        finally:
            obj_crop.close()
        return obj_output

    def get_thumbnail(self, size: tuple[int, int]) -> Image.Image:
        self._ensure_open()
        with self._lock:
            self._ensure_open()
            obj_thumb = self._image.copy()
        obj_thumb.thumbnail(
            (max(1, int(size[0])), max(1, int(size[1]))),
            Image.Resampling.LANCZOS,
        )
        return obj_thumb

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._image.close()

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback):
        self.close()
