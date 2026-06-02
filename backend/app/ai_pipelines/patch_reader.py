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
from app.tile_generator import generate_priority_tile_block, get_tiles_dir, image_to_white_rgb
from app.thread_slide_pool import get_thread_slide


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
        self.level0_tiles = get_tiles_dir(Path(slide_path).name) / "0" if self.is_philips else None

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
        tile_x = int(patch_x) // self.image_size
        tile_y = int(patch_y) // self.image_size
        path_tile = self.level0_tiles / f"{tile_x}_{tile_y}.jpeg"
        if not path_tile.exists():
            if self.wait_for_viewer:
                wait_if_viewer_busy()
            generate_priority_tile_block(
                Path(self.slide_path).name,
                self.slide_path,
                0,
                tile_x,
                tile_y,
            )
            if not path_tile.exists():
                return None
        from PIL import Image

        with Image.open(str(path_tile)) as obj_tile:
            obj_rgb = obj_tile.convert("RGB")
            try:
                # Viewer tile cache is already in display RGB, so do not apply ICC again.
                return self._to_tensor(obj_rgb)
            finally:
                obj_rgb.close()

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
