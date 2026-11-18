"""Read AI patches from valid level-0 viewer tiles, falling back to the source.

Both paths use the base viewer color transform (ICC or Hamamatsu NDP LUT).
Only tiles/<slide>/0 is used, never the extra NDP-fit variant ndpmatch/0.
Existing
Philips missing-tile generation is preserved; OpenSlide sources never generate
viewer tiles on the inference path.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import torch

from app.philips_proxy import is_philips_isyntax
from app.priority import wait_if_viewer_busy
from app.tile_generator import (
    generate_priority_tile_block, get_tiles_dir_for_path, image_to_white_rgb,
    read_complete_marker, source_signature_matches, COMPLETE_MARKER_VERSION,
    _slide_icc_hash,
)
from app.thread_slide_pool import get_thread_slide
from app.slide_manager import STAGE_READ_SIZE, TILE_SIZE_OUT, build_color_corrector


class AIPatchReader:
    def __init__(
        self,
        slide_id: str,
        slide_path: str,
        image_size: int,
        output_size: int = 512,
        icc_transform=None,
        wait_for_viewer: bool = True,
    ):
        self.slide_id = slide_id
        self.slide_path = slide_path
        self.image_size = int(image_size)
        self.output_size = int(output_size)
        self.icc_transform = icc_transform
        self.wait_for_viewer = wait_for_viewer
        self.is_philips = is_philips_isyntax(slide_path)
        self.level0_tiles = get_tiles_dir_for_path(slide_path) / "0"
        self._tile_cache_valid = None
        self._source_color_apply = None

    def read_tensor(self, patch_x: int, patch_y: int):
        if self.is_philips or self._has_valid_openslide_tiles():
            tensor = self._read_cached_tile_tensor(patch_x, patch_y)
            if tensor is not None:
                return tensor
        return self._read_direct_tensor(patch_x, patch_y)

    def _has_valid_openslide_tiles(self):
        # Validate once per inference reader, not once per patch. Missing or old
        # metadata means a direct read; never trust a filename alone.
        if self._tile_cache_valid is None:
            self._tile_cache_valid = False
            try:
                marker = read_complete_marker(Path(self.slide_path).name, self.slide_path)
                if marker and marker.get("version") == COMPLETE_MARKER_VERSION:
                    slide = get_thread_slide(self.slide_id, self.slide_path)
                    icc_hash = _slide_icc_hash(slide)
                    self._tile_cache_valid = (
                        source_signature_matches(marker, slide, self.slide_path)
                        and marker.get("icc_hash") == icc_hash
                        and (icc_hash is None or marker.get("icc_applied") is True)
                    )
            except Exception:
                self._tile_cache_valid = False
        return self._tile_cache_valid

    def _to_tensor(self, obj_rgb):
        patch_np = np.asarray(obj_rgb)
        patch_resized = cv2.resize(patch_np, (self.output_size, self.output_size))
        return torch.from_numpy(patch_resized.copy()).permute(2, 0, 1).float() / 255.0

    def _read_philips_tile_tensor(self, patch_x: int, patch_y: int):
        # Compatibility for the benchmark and existing callers.
        return self._read_cached_tile_tensor(patch_x, patch_y)

    def _read_cached_tile_tensor(self, patch_x: int, patch_y: int):
        if self.level0_tiles is None:
            return None
        # Patch origins include overlap and an edge-aligned final patch. They
        # are not tile-grid coordinates: crop all intersecting tiles exactly.
        tile_span = STAGE_READ_SIZE[0]
        if tile_span != TILE_SIZE_OUT or patch_x < 0 or patch_y < 0:
            return None  # Direct reader handles other coordinate layouts.
        from PIL import Image

        left, top = int(patch_x), int(patch_y)
        right, bottom = left + self.image_size, top + self.image_size
        canvas = Image.new("RGB", (self.image_size, self.image_size), "white")
        try:
            for tile_y in range(top // tile_span, (bottom - 1) // tile_span + 1):
                for tile_x in range(left // tile_span, (right - 1) // tile_span + 1):
                    path_tile = self.level0_tiles / f"{tile_x}_{tile_y}.jpeg"
                    if not path_tile.exists():
                        if not self.is_philips:
                            return None
                        if self.wait_for_viewer:
                            wait_if_viewer_busy()
                        generate_priority_tile_block(
                            Path(self.slide_path).name, self.slide_path, 0, tile_x, tile_y
                        )
                        if not path_tile.exists():
                            return None
                    tx, ty = tile_x * tile_span, tile_y * tile_span
                    x0, y0 = max(left, tx), max(top, ty)
                    x1, y1 = min(right, tx + tile_span), min(bottom, ty + tile_span)
                    with Image.open(str(path_tile)) as tile:
                        if tile.size != (TILE_SIZE_OUT, TILE_SIZE_OUT):
                            return None
                        rgb = tile.convert("RGB")
                        try:
                            crop = rgb.crop((x0 - tx, y0 - ty, x1 - tx, y1 - ty))
                            try:
                                canvas.paste(crop, (x0 - left, y0 - top))
                            finally:
                                crop.close()
                        finally:
                            rgb.close()
            # Cached tiles already have ICC/NDP correction; do not apply twice.
            return self._to_tensor(canvas)
        except (OSError, ValueError):
            # Invalid/partially written JPEGs must not abort a whole batch.
            return None
        finally:
            canvas.close()

    def _read_direct_tensor(self, patch_x: int, patch_y: int):
        patch = None
        patch_rgb = None
        try:
            if self.wait_for_viewer:
                wait_if_viewer_busy()
            local_slide = get_thread_slide(self.slide_id, self.slide_path)
            patch = local_slide.read_region(
                (int(patch_x), int(patch_y)),
                0,
                (self.image_size, self.image_size),
            )
            patch_rgb = image_to_white_rgb(patch)
            if self.is_philips:
                if self.icc_transform is not None:
                    from PIL import ImageCms
                    ImageCms.applyTransform(patch_rgb, self.icc_transform, inPlace=True)
            else:
                if self._source_color_apply is None:
                    self._source_color_apply, _ = build_color_corrector(local_slide)
                corrected = self._source_color_apply(patch_rgb)
                if corrected is not patch_rgb:
                    patch_rgb.close()
                    patch_rgb = corrected
            return self._to_tensor(patch_rgb)
        except Exception:
            return None
        finally:
            for obj in (patch_rgb, patch):
                try:
                    if obj is not None:
                        obj.close()
                except Exception:
                    pass
