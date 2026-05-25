"""
SVS (Aperio / Leica) → Hamamatsu raw text text.

text text Hamamatsu raw text text text, text text(text Leica Aperio SVS)
text text text text text text text text text text. text:

    Leica(ICC sRGB) ≈ Hamamatsu(Stage1 + Stage2) text

text text text Leica(ICC) text **text text text** text text Hamamatsu raw text
text text text.

Forward (text text text):
  - Stage 1 (slide_manager._build_ndp_lut):
        v1 = 255 * (v_raw / 235) ^ (1/1.8)
  - Stage 2 (ndp_color_match):
        c = 255 * (v1 / 247.91) ^ (1/1.094)
        out = c @ M + bias

Inverse (text text):
  - Stage 2⁻¹: (out - bias) @ M⁻¹ → c   →   v1 = 247.91 * (c/255)^1.094
  - Stage 1⁻¹: v_raw = 235 * (v1/255)^1.8

text:
    from app.svs_to_hamamatsu import apply_svs_to_hamamatsu
    np_hama_like = apply_svs_to_hamamatsu(np_icc_rgb_uint8)  # HxWx3 uint8 → uint8

text: ai_mask_test.ipynb §5 — 6-text text (4) ≈ (5) text.
"""
from typing import Optional

import numpy as np

# ── Stage 2 text (ndp_color_match.py text text) ──
FLOAT_S2_GAMMA = 1.094
FLOAT_S2_WHITE = 247.91
_NP_S2_MATRIX = np.array([
    [ 1.3986, -0.1898,  0.0633],
    [ 0.0432,  1.1274, -0.034 ],
    [-0.449,  -0.0141,  0.8625],
], dtype=np.float32)
_NP_S2_BIAS = np.array([2.0654, 19.8732, 24.7427], dtype=np.float32)
_NP_S2_MATRIX_INV = np.linalg.inv(_NP_S2_MATRIX).astype(np.float32)

# ── Stage 1 text (slide_manager text text) ──
FLOAT_S1_GAMMA = 1.8
FLOAT_S1_WHITE = 235.0

# Stage 2 text text (gamma⁻¹) + Stage 1 text (gamma⁻¹) text text per-channel power curve text
# 256-entry uint8 LUT text text text text. affine⁻¹ text text text text text.
#
# text text:
#   ICC RGB  → [affine⁻¹] → c (float)
#   c        → [gamma⁻¹_S2 : 247.91·(c/255)^1.094]  → v1 (float)
#   v1       → [gamma⁻¹_S1 : 235·(v1/255)^1.8]      → v_raw (uint8)
#
# gamma⁻¹_S1 ∘ gamma⁻¹_S2 text text text:
#   text x ∈ [0, 255] text text
#   v1 = 247.91 * (x/255)^1.094
#   v_raw = 235 * (v1/255)^1.8
# text text LUT text text text uint8 text O(1) text.


def _build_combined_gamma_lut() -> np.ndarray:
    """gamma⁻¹_S2 → gamma⁻¹_S1 text LUT. text uint8, text uint8."""
    np_x = np.arange(256, dtype=np.float32)
    np_v1 = np.power(np_x / 255.0, FLOAT_S2_GAMMA) * FLOAT_S2_WHITE
    np_v1 = np.clip(np_v1, 0.0, 255.0)
    np_v_raw = np.power(np_v1 / 255.0, FLOAT_S1_GAMMA) * FLOAT_S1_WHITE
    return np.clip(np_v_raw, 0.0, 255.0).astype(np.uint8)


_NP_COMBINED_GAMMA_LUT: Optional[np.ndarray] = None


def _get_combined_lut() -> np.ndarray:
    global _NP_COMBINED_GAMMA_LUT
    if _NP_COMBINED_GAMMA_LUT is None:
        _NP_COMBINED_GAMMA_LUT = _build_combined_gamma_lut()
    return _NP_COMBINED_GAMMA_LUT


def apply_svs_to_hamamatsu(np_rgb_uint8: np.ndarray) -> np.ndarray:
    """ICC-applied SVS text → Hamamatsu raw text text.

    Args:
        np_rgb_uint8: (H, W, 3) uint8 RGB — text ICC sRGB text text text.

    Returns:
        (H, W, 3) uint8 RGB — text text text text.
    """
    if np_rgb_uint8.dtype != np.uint8 or np_rgb_uint8.shape[-1] != 3:
        raise ValueError(
            f"apply_svs_to_hamamatsu: uint8 (H, W, 3) text — got "
            f"{np_rgb_uint8.dtype}, shape {np_rgb_uint8.shape}"
        )

    int_h, int_w = np_rgb_uint8.shape[:2]
    # ── 1) affine⁻¹: (v - bias) @ M⁻¹ ──
    # float32 text. text text [0, 255] text text text text text text text text clip.
    np_f = np_rgb_uint8.astype(np.float32).reshape(-1, 3)
    np_c = (np_f - _NP_S2_BIAS) @ _NP_S2_MATRIX_INV
    np_c = np.clip(np_c, 0.0, 255.0).astype(np.uint8)

    # ── 2) text gamma⁻¹ (Stage2 gamma⁻¹ + Stage1 gamma⁻¹) ──
    # text power curve text text 256-entry LUT text text text text → text text text.
    np_lut = _get_combined_lut()
    np_v_raw = np_lut[np_c]
    return np_v_raw.reshape(int_h, int_w, 3)


def apply_svs_to_hamamatsu_float(np_rgb_float32: np.ndarray) -> np.ndarray:
    """float32 text text text. ImageCms text .astype(np.float32) text text text text text.

    Args:
        np_rgb_float32: (H, W, 3) float32, text text [0, 255].

    Returns:
        (H, W, 3) float32, text text [0, 255].
    """
    np_u8 = np.clip(np_rgb_float32, 0, 255).astype(np.uint8)
    return apply_svs_to_hamamatsu(np_u8).astype(np.float32)


def is_svs_path(str_path: str) -> bool:
    """text text SVS text. Aperio/Leica text."""
    return str(str_path).lower().endswith(".svs")
