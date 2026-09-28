"""Shared AI patch reading helpers.

The AI pipelines should not care whether a slide is backed by OpenSlide or the
Philips Python 3.7 bridge.  This module keeps that difference in one place:
normal slides use the thread-local slide pool, while Philips slides reuse the
generated level-0 tile cache and only generate a missing 8192 block when needed.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import torch

from app.philips_proxy import is_philips_isyntax
from app.priority import wait_if_viewer_busy
from app.tile_generator import generate_priority_tile_block, get_tiles_dir_for_path, image_to_white_rgb
from app.thread_slide_pool import get_thread_slide
from app.slide_manager import STAGE_READ_SIZE, TILE_SIZE_OUT


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
        self.level0_tiles = get_tiles_dir_for_path(slide_path) / "0" if self.is_philips else None

    def read_tensor(self, patch_x: int, patch_y: int):
        if self.is_philips:
            tensor = self._read_philips_tile_tensor(patch_x, patch_y)
            if tensor is not None:
                return tensor
        return self._read_direct_tensor(patch_x, patch_y)

    def _to_tensor(self, obj_rgb):
        patch_np = np.asarray(obj_rgb)
        patch_resized = cv2.resize(patch_np, (self.output_size, self.output_size))
        return torch.from_numpy(patch_resized.copy()).permute(2, 0, 1).float() / 255.0

    def _read_philips_tile_tensor(self, patch_x: int, patch_y: int):
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
            # Cached tiles already have display ICC correction applied.
            return self._to_tensor(canvas)
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
            if self.icc_transform is not None:
                from PIL import ImageCms

                ImageCms.applyTransform(patch_rgb, self.icc_transform, inPlace=True)
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
