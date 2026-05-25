"""
NDP.view2 text text text 2text text — Hamamatsu text.

color_match_analysis.ipynb text MeDIAuto Studio text (text 1text text
γ=1.8 / white=235 text text text text) text NDP.view2 text 5text text text
text text text text text. RMSE 4.21.

text:
    v_stored (γ=1.8/w=235 text text text text)
      →  gamma(γ=1.094, w=247.91)           # per-channel power curve
      →  affine 3×3 matmul + bias            # text text text + text text
      →  v_ndp_matched  (NDP.view2 text)

text frontend/js/color-correction.js text NDP_FIT text text. text text text text.
"""
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

# ── text text ──
FLOAT_NDP_FIT_GAMMA = 1.094
FLOAT_NDP_FIT_WHITE = 247.91

# row = input channel (R/G/B), col = output channel
NP_NDP_FIT_MATRIX = np.array([
    [ 1.3986, -0.1898,  0.0633],
    [ 0.0432,  1.1274, -0.034 ],
    [-0.449,  -0.0141,  0.8625],
], dtype=np.float32)
NP_NDP_FIT_BIAS = np.array([2.0654, 19.8732, 24.7427], dtype=np.float32)

# ── Gamma LUT (256-entry) text text + text ──
_np_gamma_lut: Optional[np.ndarray] = None


def _get_gamma_lut() -> np.ndarray:
    global _np_gamma_lut
    if _np_gamma_lut is not None:
        return _np_gamma_lut
    np_x = np.clip(
        np.arange(256, dtype=np.float32) / FLOAT_NDP_FIT_WHITE,
        0.0, 1.0,
    )
    np_y = np.power(np_x, 1.0 / FLOAT_NDP_FIT_GAMMA) * 255.0
    _np_gamma_lut = np.clip(np_y, 0, 255).astype(np.uint8)
    return _np_gamma_lut


def apply_ndp_fit_to_array(np_img_uint8: np.ndarray) -> np.ndarray:
    """uint8 RGB ndarray (H, W, 3) → NDP-matched uint8 ndarray.

    in-place text — text text text. text Image.fromarray text text text text.
    """
    if np_img_uint8.dtype != np.uint8 or np_img_uint8.shape[-1] != 3:
        raise ValueError(
            f"apply_ndp_fit_to_array: uint8 (H, W, 3) text — got "
            f"{np_img_uint8.dtype}, shape {np_img_uint8.shape}"
        )
    np_lut = _get_gamma_lut()
    # 1) per-channel gamma LUT
    np_gamma = np_lut[np_img_uint8]  # (H, W, 3) uint8
    # 2) affine: out[c] = sum_k v_k * M[k,c] + bias[c]
    np_f = np_gamma.astype(np.float32)
    np_out = np.einsum('...k,kc->...c', np_f, NP_NDP_FIT_MATRIX) + NP_NDP_FIT_BIAS
    np_out = np.clip(np_out, 0, 255).astype(np.uint8)
    return np_out


def apply_ndp_fit(obj_img_rgb: Image.Image) -> Image.Image:
    """RGB PIL.Image → NDP-matched RGB PIL.Image (text text)."""
    np_img = np.asarray(obj_img_rgb, dtype=np.uint8)
    np_out = apply_ndp_fit_to_array(np_img)
    return Image.fromarray(np_out, "RGB")


def convert_jpeg_file(path_src: Path, path_dst: Path, int_quality: int = 85) -> bool:
    """JPEG text text text JPEG text text. text text True."""
    try:
        with Image.open(str(path_src)) as obj_img:
            obj_rgb = obj_img.convert("RGB")
        obj_out = apply_ndp_fit(obj_rgb)
        path_dst.parent.mkdir(parents=True, exist_ok=True)
        obj_out.save(str(path_dst), "JPEG", quality=int_quality)
        return True
    except Exception as e:
        print(f"[ndp_color_match] convert_jpeg_file failed ({path_src} → {path_dst}): {e}")
        return False


def is_hamamatsu_slide(dict_properties) -> bool:
    """openslide.properties text dict text vendor=hamamatsu text."""
    try:
        str_vendor = str(dict_properties.get("openslide.vendor", "")).lower()
    except Exception:
        return False
    return str_vendor == "hamamatsu"
