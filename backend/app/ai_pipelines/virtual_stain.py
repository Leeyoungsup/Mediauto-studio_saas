"""Virtual Stain (VS IHC) worker + tile streaming/pyramid.

routers/ai.py text text text. text SVS text text ~100 MB text text
text full canvas text text text text streaming text text (VSTileStreamer).

VS IHC text SVS text text svs_to_hamamatsu text text text text text
text — env `VS_SVS_INVERSE_CHAIN=0` text text text text.
"""

import json
import os
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from app.ai_pipelines.cache_paths import get_vs_cache_paths, get_vs_tile_dir
from app.ai_pipelines.task_state import (
    TaskCancelled,
    check_cancel,
    cleanup_cache_paths,
    update_task,
)
from app.config import settings
from app.philips_proxy import PhilipsSlideProxy, is_philips_isyntax
from app.priority import wait_if_viewer_busy
from app.resource_utils import close_safely, collect_garbage
from app.slide_manager import slide_manager

VS_MODEL_FILES = {
    "ihc_membrane": "IHC_HnE_virtual_stain_membrane.pth",
}


class VSTileStreamer:
    """VS IHC level-0 text text text.

    text (out_h, out_w) text output_acc / input_acc / weight_acc float32 text
    text text text blending text PNG text text. text SVS text 3~5 GB RAM.
    text text patch text text text text text text, text text text text text
    text text JPEG text flush text text text ~100 MB text text.

    text text text text:
      - input/output text text `patch * blend_3ch` text
      - weight text patch text text text text (input text)
      - finalize text `acc / max(weight, 1e-10)` text blend text
      - tissue_pixel_mask text text text output ↔ input text
      - roi_mask text text text text text

    finalize text: yi-major text patch text text text text, `flush_rows_up_to(done_y)`
    text text text text `done_y` text text text disk text text text text.
    """

    def __init__(self, out_w: int, out_h: int, tile_size: int,
                 tile_dir: Path, blend_3ch: np.ndarray, blend_weight: np.ndarray,
                 int_quality: int = 88):
        self.out_w = int(out_w)
        self.out_h = int(out_h)
        self.TS = int(tile_size)
        self.nx = (self.out_w + self.TS - 1) // self.TS
        self.ny = (self.out_h + self.TS - 1) // self.TS
        self.tile_dir = Path(tile_dir)
        self.int_quality = int_quality
        self.blend_3ch = blend_3ch
        self.blend_weight = blend_weight
        self.ps = int(blend_weight.shape[0])
        self.active: dict = {}  # (tx, ty) -> {'out', 'inp', 'w'}
        self.finalized_keys: set = set()
        self.int_saved_tiles = 0
        # level 0 text text text
        (self.tile_dir / '0').mkdir(parents=True, exist_ok=True)

        # finalize text pixel-level mask text output ↔ input text.
        # tissue_pixel_mask text (out_h, out_w) bool, roi_mask_u8 text (out_h, out_w) uint8.
        self._tissue_mask: Optional[np.ndarray] = None
        self._roi_mask_u8: Optional[np.ndarray] = None

    def set_finalization_masks(self, tissue_pixel_mask: np.ndarray,
                                 roi_mask_u8: Optional[np.ndarray]) -> None:
        self._tissue_mask = tissue_pixel_mask
        self._roi_mask_u8 = roi_mask_u8

    def _get_tile(self, tx: int, ty: int):
        if tx < 0 or tx >= self.nx or ty < 0 or ty >= self.ny:
            return None
        key = (tx, ty)
        if key in self.finalized_keys:
            # text finalize text text text splat → text text text text. raise text text text.
            raise RuntimeError(
                f"VSTileStreamer: tile {key} already finalized but splat called again"
            )
        tile = self.active.get(key)
        if tile is None:
            tile = {
                'out': np.zeros((self.TS, self.TS, 3), dtype=np.float32),
                'inp': np.zeros((self.TS, self.TS, 3), dtype=np.float32),
                'w':   np.zeros((self.TS, self.TS),   dtype=np.float32),
            }
            self.active[key] = tile
        return tile

    def splat(self, int_px: int, int_py: int,
              np_input_patch: np.ndarray, np_output_patch: np.ndarray) -> None:
        """text patch (input + output text) text text text text blending text.
        weight text patch text text text text."""
        ps = self.ps
        TS = self.TS
        tx0 = max(0, int_px // TS)
        ty0 = max(0, int_py // TS)
        tx1 = min(self.nx - 1, (int_px + ps - 1) // TS)
        ty1 = min(self.ny - 1, (int_py + ps - 1) // TS)
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                tile = self._get_tile(tx, ty)
                if tile is None:
                    continue
                t_left = tx * TS
                t_top = ty * TS
                # text text
                ix_s = max(int_px, t_left)
                iy_s = max(int_py, t_top)
                ix_e = min(int_px + ps, t_left + TS, self.out_w)
                iy_e = min(int_py + ps, t_top + TS, self.out_h)
                if ix_e <= ix_s or iy_e <= iy_s:
                    continue
                # patch-local
                plx = ix_s - int_px; ply = iy_s - int_py
                prx = ix_e - int_px; pry = iy_e - int_py
                # tile-local
                tlx = ix_s - t_left; tly = iy_s - t_top
                trx = ix_e - t_left; trr = iy_e - t_top
                np_b3 = self.blend_3ch[ply:pry, plx:prx]
                np_bw = self.blend_weight[ply:pry, plx:prx]
                tile['inp'][tly:trr, tlx:trx] += np_input_patch[ply:pry, plx:prx] * np_b3
                tile['out'][tly:trr, tlx:trx] += np_output_patch[ply:pry, plx:prx] * np_b3
                tile['w']  [tly:trr, tlx:trx] += np_bw

    def flush_rows_up_to(self, int_safe_y_max: int) -> None:
        """text text(`(ty+1)*TS`) text `int_safe_y_max` text text text disk text flush.
        text text patch text touch text text text text text text text text text."""
        list_keys = [k for k in self.active if (k[1] + 1) * self.TS <= int_safe_y_max]
        for key in list_keys:
            self._finalize(key)

    def flush_all(self) -> None:
        """text text text disk text flush (text text text text)."""
        for key in list(self.active.keys()):
            self._finalize(key)

    def _finalize(self, tuple_key) -> None:
        tx, ty = tuple_key
        tile = self.active.pop(tuple_key)
        self.finalized_keys.add(tuple_key)
        TS = self.TS
        # blending normalize
        np_w = np.maximum(tile['w'], 1e-10)
        np_out = (tile['out'] / np_w[..., None]).clip(0, 255).astype(np.uint8)
        np_inp = (tile['inp'] / np_w[..., None]).clip(0, 255).astype(np.uint8)
        np_uncov = tile['w'] < 0.01
        np_out[np_uncov] = 255
        np_inp[np_uncov] = 255
        # tile text text text text text text text < TS
        t_left = tx * TS
        t_top = ty * TS
        t_right = min(t_left + TS, self.out_w)
        t_bottom = min(t_top + TS, self.out_h)
        int_th = t_bottom - t_top
        int_tw = t_right - t_left
        np_out = np_out[:int_th, :int_tw].copy()
        np_inp = np_inp[:int_th, :int_tw]
        # pixel-level tissue mask: tissue text text text input pass-through text text
        if self._tissue_mask is not None:
            np_tmask = self._tissue_mask[t_top:t_bottom, t_left:t_right]
            np_out[~np_tmask] = np_inp[~np_tmask]
        # ROI text text (alpha text JPEG text 255 text text text)
        if self._roi_mask_u8 is not None:
            np_rmask = self._roi_mask_u8[t_top:t_bottom, t_left:t_right]
            np_out[np_rmask == 0] = 255
        # text text text text (text + text text text; text 404 = text text)
        if np_out.size == 0 or np_out.min() >= 248:
            return
        path_out = self.tile_dir / '0' / f'{tx}_{ty}.jpeg'
        Image.fromarray(np_out, 'RGB').save(str(path_out), 'JPEG', quality=self.int_quality)
        self.int_saved_tiles += 1


def build_vs_pyramid_from_disk(path_tile_dir: Path, int_tile_size: int,
                                 int_n_levels: int, int_level0_w: int, int_level0_h: int,
                                 int_quality: int = 88) -> list:
    """Level 0 text text disk text text text. Level 1..n-1 text on-disk 2×2 text text.
    text text: text text 1024×1024 (2×2 text merge) RGB = ~3 MB."""
    import cv2 as _cv2

    list_meta = []
    for int_lv in range(int_n_levels):
        int_lvl_w = max(1, int_level0_w // (2 ** int_lv))
        int_lvl_h = max(1, int_level0_h // (2 ** int_lv))
        int_lvl_nx = (int_lvl_w + int_tile_size - 1) // int_tile_size
        int_lvl_ny = (int_lvl_h + int_tile_size - 1) // int_tile_size

        if int_lv == 0:
            # level 0 text text text text text. count text text text text
            int_count = sum(1 for _ in (path_tile_dir / '0').glob('*.jpeg')) if (path_tile_dir / '0').exists() else 0
        else:
            path_src = path_tile_dir / str(int_lv - 1)
            path_dst = path_tile_dir / str(int_lv)
            path_dst.mkdir(parents=True, exist_ok=True)
            int_src_w = max(1, int_level0_w // (2 ** (int_lv - 1)))
            int_src_h = max(1, int_level0_h // (2 ** (int_lv - 1)))
            int_src_nx = (int_src_w + int_tile_size - 1) // int_tile_size
            int_src_ny = (int_src_h + int_tile_size - 1) // int_tile_size
            int_count = 0
            for dty in range(int_lvl_ny):
                for dtx in range(int_lvl_nx):
                    # merged 2×2 text (text text text)
                    np_merged = np.full(
                        (2 * int_tile_size, 2 * int_tile_size, 3), 255, dtype=np.uint8
                    )
                    bool_any = False
                    for dy in range(2):
                        for dx in range(2):
                            sx = 2 * dtx + dx
                            sy = 2 * dty + dy
                            if sx >= int_src_nx or sy >= int_src_ny:
                                continue
                            path_jp = path_src / f'{sx}_{sy}.jpeg'
                            if not path_jp.exists():
                                continue
                            bool_any = True
                            with Image.open(path_jp) as img_src:
                                img_rgb = img_src.convert('RGB')
                                try:
                                    np_src = np.asarray(img_rgb).copy()
                                finally:
                                    img_rgb.close()
                            ah, aw = np_src.shape[:2]
                            np_merged[dy * int_tile_size:dy * int_tile_size + ah,
                                       dx * int_tile_size:dx * int_tile_size + aw] = np_src
                    if not bool_any:
                        continue
                    np_down = _cv2.resize(np_merged, (int_tile_size, int_tile_size),
                                            interpolation=_cv2.INTER_AREA)
                    if np_down.min() >= 248:
                        continue
                    Image.fromarray(np_down, 'RGB').save(
                        str(path_dst / f'{dtx}_{dty}.jpeg'), 'JPEG', quality=int_quality
                    )
                    int_count += 1
        list_meta.append({
            "level": int_lv,
            "width": int_lvl_w,
            "height": int_lvl_h,
            "nx": int_lvl_nx,
            "ny": int_lvl_ny,
            "tile_count": int_count,
        })
    return list_meta


def generate_vs_tiles(output_canvas, tile_dir: Path,
                      tile_size: int = 512, n_levels: int = 4,
                      quality: int = 88) -> list:
    """
    output_canvas (uint8 H×W×3 text H×W×4) → 4text text JPEG text text.
    text 0 = text text, text text /2 text.
    text text text text (text text 404 → text text).
    text: [{"level":0,"width":W,"height":H,"nx":..,"ny":..,"tile_count":..}, ...]

    text text(PNG → text text) text text — text text
    VSTileStreamer text text level-0 text text build_vs_pyramid_from_disk text
    text text text.
    """
    if tile_dir.exists():
        # text text text (text text stale text)
        try:
            import shutil
            shutil.rmtree(tile_dir)
        except Exception:
            pass
    tile_dir.mkdir(parents=True, exist_ok=True)

    # RGBA → RGB (alpha=0 text text text text JPEG text)
    if output_canvas.ndim == 3 and output_canvas.shape[2] == 4:
        rgb = output_canvas[:, :, :3].copy()
        a = output_canvas[:, :, 3]
        mask = a < 255
        if mask.any():
            rgb[mask] = 255
        pil = Image.fromarray(rgb, 'RGB')
    else:
        pil = Image.fromarray(output_canvas, 'RGB')

    levels_meta: list = []
    current = pil
    for lv in range(n_levels):
        w, h = current.size
        nx = (w + tile_size - 1) // tile_size
        ny = (h + tile_size - 1) // tile_size
        level_dir = tile_dir / str(lv)
        level_dir.mkdir(parents=True, exist_ok=True)

        arr = np.asarray(current)
        count = 0
        for ty in range(ny):
            for tx in range(nx):
                left = tx * tile_size
                upper = ty * tile_size
                right = min(left + tile_size, w)
                lower = min(upper + tile_size, h)
                patch = arr[upper:lower, left:right]
                # text text text text (text text)
                if patch.size == 0:
                    continue
                if patch.min() >= 248:
                    continue
                tile_img = Image.fromarray(patch, 'RGB')
                tile_img.save(level_dir / f"{tx}_{ty}.jpeg", "JPEG",
                              quality=quality, optimize=False)
                count += 1

        levels_meta.append({
            "level": lv, "width": int(w), "height": int(h),
            "nx": int(nx), "ny": int(ny), "tile_count": int(count),
        })

        if lv < n_levels - 1:
            new_w = max(1, w // 2)
            new_h = max(1, h // 2)
            current = current.resize((new_w, new_h), Image.BILINEAR)

    return levels_meta


def run_virtual_stain(task_id: str, slide_id: str,
                      roi_polygons, stain_type: str,
                      target_mpp: float = 2.0):
    """
    Virtual staining text text.
    desktop ai/virtual_stain.py text VirtualStainWorker.run() text text text.
    Qt text text update_task() text.
    """
    list_cleanup_on_cancel = []
    slide = None
    generator = None
    try:
        import torch
        import openslide

        from ai.vs_ihc import (
            Generator, _make_blend_weight, _read_patch, VirtualStainWorker
        )

        # Pillowtext decompression-bomb text text (VS composite text text px text text text)
        Image.MAX_IMAGE_PIXELS = None

        info = slide_manager.get(slide_id)
        if not info:
            update_task(task_id, status="error", error="text text text text")
            return

        # ── ROI text text (text text; text text text text) ──
        # text/text ROI text text text text text.
        # text, text ROItext text text text text text text text text
        # text ROI text text text text.
        display_roi_polygons = roi_polygons
        roi_polygons = None  # text text text

        # ── text text ──
        # text text PNG text text text meta.json + text text text.
        # text text hit text (meta.json text) AND (level-0 text text text text).
        # text text (PNG + meta text text text X) text PNG text text text text text.
        png_path, meta_path = get_vs_cache_paths(info.file_path, target_mpp)
        tile_dir = get_vs_tile_dir(info.file_path, target_mpp)
        path_lvl0 = tile_dir / '0'

        bool_meta_ok = meta_path.exists()
        bool_tiles_ok = path_lvl0.exists() and any(path_lvl0.glob('*.jpeg'))
        bool_png_legacy = png_path.exists()

        if bool_meta_ok and (bool_tiles_ok or bool_png_legacy):
            try:
                update_task(task_id, status="running", progress=10,
                            status_msg="Loading cached virtual stain")
                with open(meta_path, 'r', encoding='utf-8') as f:
                    cached_meta = json.load(f)

                # text: PNG text text text text text text PNG → text 1text text
                if not bool_tiles_ok and bool_png_legacy:
                    try:
                        update_task(task_id, progress=30,
                                    status_msg="Upgrading legacy cache → tile pyramid...")
                        with Image.open(str(png_path)) as legacy_png:
                            if legacy_png.mode == 'RGBA':
                                bg = Image.new('RGB', legacy_png.size, (255, 255, 255))
                                try:
                                    bg.paste(legacy_png, mask=legacy_png.split()[3])
                                    legacy_arr = np.asarray(bg).copy()
                                finally:
                                    bg.close()
                            else:
                                legacy_rgb = legacy_png.convert('RGB')
                                try:
                                    legacy_arr = np.asarray(legacy_rgb).copy()
                                finally:
                                    legacy_rgb.close()
                        tile_size_px = int(cached_meta.get("tile_size", 512))
                        levels_meta = generate_vs_tiles(
                            legacy_arr, tile_dir,
                            tile_size=tile_size_px, n_levels=4,
                        )
                        cached_meta['tile_size'] = tile_size_px
                        cached_meta['levels'] = levels_meta
                        with open(meta_path, 'w', encoding='utf-8') as f:
                            json.dump(cached_meta, f)
                    except Exception as e:
                        import traceback
                        print(f"VS legacy tile upgrade failed: {e}\n{traceback.format_exc()}")

                cached_meta['image_filename'] = png_path.name
                cached_meta['cached'] = True
                if display_roi_polygons is not None:
                    cached_meta['roi_polygons'] = display_roi_polygons
                # text hit text DB text text — auto_ai text text text text text text.
                # VS IHC text list_slides_in_folder + per-mpp text text text text,
                # bool_has_result / list_variants text text text text UI text "text text" text.
                from app import slide_store
                slide_store.mark_ai_result_threadsafe(info.file_path, "VS IHC", stain_type)
                update_task(task_id, status="completed", progress=100,
                            status_msg="Loaded cached virtual stain",
                            result=cached_meta)
                return
            except Exception as e:
                print(f"VS cache load failed, running fresh: {e}")

        # ── text text text ──
        model_filename = VS_MODEL_FILES.get(stain_type)
        if not model_filename:
            update_task(task_id, status="error",
                        error=f"Unknown stain type: {stain_type}")
            return
        model_path = Path(settings.MODEL_DIR) / model_filename
        if not model_path.exists():
            update_task(task_id, status="error",
                        error=f"Virtual stain model not found: {model_path}")
            return

        update_task(task_id, status="running", progress=1,
                    status_msg="Loading virtual stain model...")

        device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        use_fp16 = (device.type == 'cuda')

        generator = Generator(3, 3).to(device)
        generator.load_state_dict(torch.load(str(model_path), map_location=device))
        generator.eval()
        if use_fp16:
            generator = generator.half()

        update_task(task_id, progress=3, status_msg="Opening slide...")

        slide_path = info.file_path
        slide = PhilipsSlideProxy(slide_path) if is_philips_isyntax(slide_path) else openslide.OpenSlide(slide_path)

        # target_mpp is provided as parameter
        patch_size = 512
        batch_size = 4

        native_mpp = float(slide.properties.get('openslide.mpp-x', 0.25))
        downsample_factor = target_mpp / native_mpp
        ps = patch_size
        overlap = ps // 4
        stride = ps - overlap
        read_size = int(ps * downsample_factor)
        read_stride = int(stride * downsample_factor)

        best_level = slide.get_best_level_for_downsample(downsample_factor)
        level_ds = slide.level_downsamples[best_level]
        level_read = int(read_size / level_ds)

        W, H = slide.dimensions

        # ROI bounds text (text → bounding box)
        roi_bounds = None
        if roi_polygons:
            xs = [p[0] for poly in roi_polygons for p in poly]
            ys = [p[1] for poly in roi_polygons for p in poly]
            roi_bounds = (
                max(0, int(min(xs))), max(0, int(min(ys))),
                min(W, int(max(xs))), min(H, int(max(ys))),
            )

        if roi_bounds:
            x_min, y_min, x_max, y_max = roi_bounds
        else:
            x_min, y_min, x_max, y_max = 0, 0, W, H

        # ROItext text text text read_sizetext text (text text text text)
        if x_max - x_min < read_size:
            cx = (x_min + x_max) // 2
            x_min = max(0, cx - read_size // 2)
            x_max = min(W, x_min + read_size)
            x_min = max(0, x_max - read_size)
        if y_max - y_min < read_size:
            cy = (y_min + y_max) // 2
            y_min = max(0, cy - read_size // 2)
            y_max = min(H, y_min + read_size)
            y_min = max(0, y_max - read_size)

        if W < read_size or H < read_size:
            update_task(task_id, status="error",
                        error=f"Slide too small for target_mpp={target_mpp} "
                              f"(needs >= {read_size}px at level-0, slide is {W}x{H}).")
            close_safely(slide)
            slide = None
            return

        pos_x = list(range(x_min, x_max - read_size + 1, read_stride))
        pos_y = list(range(y_min, y_max - read_size + 1, read_stride))
        if not pos_x:
            pos_x = [x_min]
        if not pos_y:
            pos_y = [y_min]
        if pos_x[-1] + read_size < x_max:
            pos_x.append(max(pos_x[-1] + read_stride, x_max - read_size))
        if pos_y[-1] + read_size < y_max:
            pos_y.append(max(pos_y[-1] + read_stride, y_max - read_size))

        n_px, n_py = len(pos_x), len(pos_y)
        out_w = (n_px - 1) * stride + ps
        out_h = (n_py - 1) * stride + ps
        canvas_l0_w = pos_x[-1] + read_size - x_min
        canvas_l0_h = pos_y[-1] + read_size - y_min

        update_task(task_id, progress=5, status_msg="Creating tissue mask...")

        # tissue grid text workertext text text text (text text staticmethod text text
        # text text text text) — text text text: dummy worker text text
        dummy_worker = VirtualStainWorker(
            image_path=slide_path,
            model_path=str(model_path),
            stain_type=stain_type,
            target_mpp=target_mpp,
            patch_size=patch_size,
            batch_size=batch_size,
            roi_bounds=roi_bounds,
            roi_polygons=roi_polygons,
        )
        tissue_grid, tissue_pixel_mask = dummy_worker._build_tissue_grid(
            slide, x_min, y_min, canvas_l0_w, canvas_l0_h,
            n_px, n_py, stride, ps, out_w, out_h,
        )
        tissue_total = int(tissue_grid.sum())
        update_task(task_id, progress=8,
                    status_msg=f"Grid {n_px}x{n_py}: {tissue_total} tissue patches")

        # ── text text ──
        all_patches = []
        for yi in range(n_py):
            for xi in range(n_px):
                x0 = pos_x[xi]
                y0 = pos_y[yi]
                out_of_bounds = (x0 + read_size > W) or (y0 + read_size > H)
                is_tissue = bool(tissue_grid[yi, xi]) and not out_of_bounds
                all_patches.append((xi, yi, x0, y0,
                                    xi * stride, yi * stride, is_tissue))

        # ── text text text (full canvas text) ──
        # text (out_h, out_w) output/input/weight float32 3text (~3.3GB) text text text
        # PNG text → text. text text text text text flush-row text text text.
        blend_weight = _make_blend_weight(ps, overlap)
        blend_3ch = blend_weight[:, :, None]
        tile_size_px = 512
        tile_dir = get_vs_tile_dir(info.file_path, target_mpp)
        # text text text text text
        if tile_dir.exists():
            try:
                import shutil as _shutil
                _shutil.rmtree(tile_dir)
            except Exception:
                pass
        streamer = VSTileStreamer(
            out_w=out_w, out_h=out_h, tile_size=tile_size_px,
            tile_dir=tile_dir, blend_3ch=blend_3ch, blend_weight=blend_weight,
        )
        # finalize text text text text text + ROI polygon text text
        import cv2
        np_roi_mask_u8 = None
        if roi_polygons:
            scale_x = out_w / canvas_l0_w
            scale_y = out_h / canvas_l0_h
            np_roi_mask_u8 = np.zeros((out_h, out_w), dtype=np.uint8)
            for poly_coords in roi_polygons:
                np_pts = np.array([
                    [round((x - x_min) * scale_x), round((y - y_min) * scale_y)]
                    for x, y in poly_coords
                ], dtype=np.int32)
                cv2.fillPoly(np_roi_mask_u8, [np_pts], 255)
        streamer.set_finalization_masks(tissue_pixel_mask, np_roi_mask_u8)

        tissue_count = 0
        bs = batch_size
        from app.cpu_layout import INT_AI
        io_workers = max(1, min(INT_AI, 4))
        tissue_batch = []   # [(px, py, tensor, input_np), ...]

        icc_tf = info.icc_transform

        # ── SVS → Hamamatsu raw text ──
        # env VS_SVS_INVERSE_CHAIN=0 text text text text.
        bool_svs_inv = (
            Path(slide_path).suffix.lower() == ".svs"
            and os.environ.get("VS_SVS_INVERSE_CHAIN", "1") != "0"
        )
        _svs_to_ham = None
        if bool_svs_inv:
            from app.svs_to_hamamatsu import apply_svs_to_hamamatsu_float
            _svs_to_ham = apply_svs_to_hamamatsu_float

        def _gan_flush(list_batch):
            """tissue_batch text GPU text text GAN output text → streamer.splat."""
            if not list_batch:
                return 0
            tensors = [item[2] for item in list_batch]
            batch = torch.stack(tensors).to(device, non_blocking=True)
            if use_fp16:
                batch = batch.half()
            fake_batch = generator(batch)
            fake_batch = fake_batch.float().cpu()
            fake_batch = (fake_batch * 0.5 + 0.5).clamp_(0, 1)
            for i, (int_px, int_py, _t, np_inp) in enumerate(list_batch):
                np_fake = (fake_batch[i].permute(1, 2, 0).numpy() * 255.0)
                streamer.splat(int_px, int_py, np_inp, np_fake)
            del fake_batch, batch, tensors
            return len(list_batch)

        with torch.inference_mode(), ThreadPoolExecutor(
            max_workers=io_workers,
            thread_name_prefix="ai_worker_vs",
        ) as pool:
            # Keep only a small read-ahead window. Submitting every patch at once
            # lets completed numpy regions pile up in memory during large VS IHC jobs.
            int_default_prefetch = max(io_workers * 2, bs * 2)
            try:
                int_prefetch_limit = max(1, int(os.environ.get("VS_IHC_PREFETCH_LIMIT", int_default_prefetch)))
            except ValueError:
                int_prefetch_limit = int_default_prefetch
            pending_reads = deque()
            next_patch_idx = 0

            def _submit_next_patch_read():
                nonlocal next_patch_idx
                if next_patch_idx >= len(all_patches):
                    return False
                check_cancel(task_id)
                xi, yi, x0, y0, px, py_c, is_tissue = all_patches[next_patch_idx]
                wait_if_viewer_busy()
                future = pool.submit(_read_patch, slide_path, x0, y0,
                                     best_level, level_read, ps, icc_tf, None)
                pending_reads.append((xi, yi, x0, y0, px, py_c, is_tissue, future))
                next_patch_idx += 1
                return True

            while len(pending_reads) < int_prefetch_limit and _submit_next_patch_read():
                pass

            while pending_reads:
                check_cancel(task_id)
                xi, yi, x0, y0, px, py_c, is_tissue, future = pending_reads.popleft()
                region_np = future.result()
                if len(pending_reads) < int_prefetch_limit:
                    _submit_next_patch_read()
                # text text inverse chain text (tissue text)
                if _svs_to_ham is not None and is_tissue:
                    try:
                        region_np = _svs_to_ham(region_np)
                    except Exception as e:
                        print(f"[VS IHC] svs_to_hamamatsu failed at ({x0},{y0}): {e!r}")

                if not is_tissue:
                    # GAN text — input=output=region_np text text splat.
                    streamer.splat(px, py_c, region_np, region_np)
                    del region_np
                else:
                    t = torch.from_numpy(region_np).permute(2, 0, 1)
                    t = t / 255.0 * 2.0 - 1.0
                    tissue_batch.append((px, py_c, t, region_np))

                is_end_of_row = (xi == n_px - 1)
                batch_full = len(tissue_batch) >= bs
                if tissue_batch and (batch_full or is_end_of_row):
                    tissue_count += _gan_flush(tissue_batch)
                    tissue_batch.clear()

                if is_end_of_row:
                    # text yi text text text — text text py ≥ (yi+1)*stride text text text text text text.
                    int_safe_y = (yi + 1) * stride
                    streamer.flush_rows_up_to(int_safe_y)

                    pct = 8 + int(87 * (yi + 1) / n_py)
                    update_task(task_id, progress=pct,
                                status_msg=f"Virtual staining... row {yi + 1}/{n_py} "
                                           f"({tissue_count} tissue patches)")

        if tissue_batch:
            tissue_count += _gan_flush(tissue_batch)
            tissue_batch.clear()

        check_cancel(task_id)
        update_task(task_id, progress=96, status_msg="Finalizing tiles...")
        streamer.flush_all()

        # ── On-disk text text (level 1+) ──
        update_task(task_id, progress=98, status_msg="Generating tile pyramid...")
        levels_meta = []
        try:
            levels_meta = build_vs_pyramid_from_disk(
                tile_dir, int_tile_size=tile_size_px, int_n_levels=4,
                int_level0_w=out_w, int_level0_h=out_h,
            )

            meta = {
                "stain_type": stain_type,
                "roi_origin": [int(x_min), int(y_min)],
                "canvas_l0_w": int(canvas_l0_w),
                "canvas_l0_h": int(canvas_l0_h),
                "target_mpp": target_mpp,
                "tissue_count": int(tissue_count),
                "total_patches": int(n_px * n_py),
                "image_filename": png_path.name,
                "tile_size": tile_size_px,
                "levels": levels_meta,
            }
            # meta text text (PNG text text text — text text text)
            list_cleanup_on_cancel.append(meta_path)
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f)
            print(f"VS cached: {streamer.int_saved_tiles} level-0 tiles, "
                  f"{len(levels_meta)} pyramid levels total")
            from app import slide_store
            slide_store.mark_ai_result_threadsafe(info.file_path, "VS IHC", stain_type)
        except Exception as e:
            import traceback
            print(f"VS cache save failed: {e}\n{traceback.format_exc()}")

        result_payload = {
            "stain_type": stain_type,
            "image_filename": png_path.name,
            "roi_origin": [int(x_min), int(y_min)],
            "canvas_l0_w": int(canvas_l0_w),
            "canvas_l0_h": int(canvas_l0_h),
            "target_mpp": target_mpp,
            "tissue_count": int(tissue_count),
            "total_patches": int(n_px * n_py),
            "tile_size": tile_size_px,
            "levels": levels_meta,
            "cached": False,
        }
        if display_roi_polygons is not None:
            result_payload["roi_polygons"] = display_roi_polygons
        update_task(task_id, status="completed", progress=100,
                    status_msg=f"Virtual staining complete — {tissue_count}/{n_px * n_py} patches",
                    result=result_payload)

        del generator
        close_safely(slide)
        slide = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    except TaskCancelled:
        cleanup_cache_paths(list_cleanup_on_cancel)
        update_task(task_id, status="cancelled", progress=0,
                    status_msg="Cancelled by user", error=None)
        print(f"[cancel] run_virtual_stain cancelled task={task_id}")
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
    except Exception as e:
        import traceback
        update_task(task_id, status="error",
                    error=f"Virtual staining failed: {e}\n{traceback.format_exc()}")
    finally:
        try:
            if slide is not None:
                close_safely(slide)
        except Exception:
            pass
        try:
            # VS IHC is a heavy one-shot task; close the shared handle so Windows
            # can reclaim file-cache pressure without waiting for server shutdown.
            slide_manager.close(slide_id)
        except Exception:
            pass
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        generator = None
        collect_garbage()
