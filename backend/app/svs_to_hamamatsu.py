"""
SVS (Aperio / Leica) → Hamamatsu raw 입력 정규화.

학습 데이터가 Hamamatsu raw 로 구성되어 있어, 다른 스캐너(특히 Leica Aperio SVS)
입력을 그대로 모델에 넣으면 색공간이 달라 정확도가 저하될 수 있다. 가설:

    Leica(ICC sRGB) ≈ Hamamatsu(Stage1 + Stage2) 출력

이 가설이 맞다면 Leica(ICC) 에 **두 단계 역변환** 을 씌우면 Hamamatsu raw 에
근사한 입력이 된다.

Forward (서버에 이미 구현됨):
  - Stage 1 (slide_manager._build_ndp_lut):
        v1 = 255 * (v_raw / 235) ^ (1/1.8)
  - Stage 2 (ndp_color_match):
        c = 255 * (v1 / 247.91) ^ (1/1.094)
        out = c @ M + bias

Inverse (이 모듈):
  - Stage 2⁻¹: (out - bias) @ M⁻¹ → c   →   v1 = 247.91 * (c/255)^1.094
  - Stage 1⁻¹: v_raw = 235 * (v1/255)^1.8

사용:
    from app.svs_to_hamamatsu import apply_svs_to_hamamatsu
    np_hama_like = apply_svs_to_hamamatsu(np_icc_rgb_uint8)  # HxWx3 uint8 → uint8

검증: ai_mask_test.ipynb §5 — 6-패널 비교에서 (4) ≈ (5) 확인.
"""
from typing import Optional

import numpy as np

# ── Stage 2 상수 (ndp_color_match.py 와 동기화) ──
FLOAT_S2_GAMMA = 1.094
FLOAT_S2_WHITE = 247.91
_NP_S2_MATRIX = np.array([
    [ 1.3986, -0.1898,  0.0633],
    [ 0.0432,  1.1274, -0.034 ],
    [-0.449,  -0.0141,  0.8625],
], dtype=np.float32)
_NP_S2_BIAS = np.array([2.0654, 19.8732, 24.7427], dtype=np.float32)
_NP_S2_MATRIX_INV = np.linalg.inv(_NP_S2_MATRIX).astype(np.float32)

# ── Stage 1 상수 (slide_manager 와 동기화) ──
FLOAT_S1_GAMMA = 1.8
FLOAT_S1_WHITE = 235.0

# Stage 2 의 후반부 (gamma⁻¹) + Stage 1 전체 (gamma⁻¹) 는 모두 per-channel power curve 이므로
# 256-entry uint8 LUT 로 미리 합성해 둔다. affine⁻¹ 은 픽셀 단위 연산이 필요.
#
# 파이프라인 해석:
#   ICC RGB  → [affine⁻¹] → c (float)
#   c        → [gamma⁻¹_S2 : 247.91·(c/255)^1.094]  → v1 (float)
#   v1       → [gamma⁻¹_S1 : 235·(v1/255)^1.8]      → v_raw (uint8)
#
# gamma⁻¹_S1 ∘ gamma⁻¹_S2 가 합성 가능:
#   입력 x ∈ [0, 255] 에 대해
#   v1 = 247.91 * (x/255)^1.094
#   v_raw = 235 * (v1/255)^1.8
# 이 합성 LUT 를 미리 만들어 uint8 인덱싱으로 O(1) 적용.


def _build_combined_gamma_lut() -> np.ndarray:
    """gamma⁻¹_S2 → gamma⁻¹_S1 합성 LUT. 입력 uint8, 출력 uint8."""
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
    """ICC-applied SVS 픽셀 → Hamamatsu raw 근사 픽셀.

    Args:
        np_rgb_uint8: (H, W, 3) uint8 RGB — 이미 ICC sRGB 변환된 상태여야 함.

    Returns:
        (H, W, 3) uint8 RGB — 두 단계 역변환 적용본.
    """
    if np_rgb_uint8.dtype != np.uint8 or np_rgb_uint8.shape[-1] != 3:
        raise ValueError(
            f"apply_svs_to_hamamatsu: uint8 (H, W, 3) 필요 — got "
            f"{np_rgb_uint8.dtype}, shape {np_rgb_uint8.shape}"
        )

    int_h, int_w = np_rgb_uint8.shape[:2]
    # ── 1) affine⁻¹: (v - bias) @ M⁻¹ ──
    # float32 유지. 결과는 이론상 [0, 255] 이지만 수치 노이즈로 약간 밖으로 나갈 수 있어 clip.
    np_f = np_rgb_uint8.astype(np.float32).reshape(-1, 3)
    np_c = (np_f - _NP_S2_BIAS) @ _NP_S2_MATRIX_INV
    np_c = np.clip(np_c, 0.0, 255.0).astype(np.uint8)

    # ── 2) 합성 gamma⁻¹ (Stage2 gamma⁻¹ + Stage1 gamma⁻¹) ──
    # 두 power curve 를 단일 256-entry LUT 로 미리 합성해 두었음 → 인덱싱 한 번.
    np_lut = _get_combined_lut()
    np_v_raw = np_lut[np_c]
    return np_v_raw.reshape(int_h, int_w, 3)


def apply_svs_to_hamamatsu_float(np_rgb_float32: np.ndarray) -> np.ndarray:
    """float32 입력 편의 래퍼. ImageCms 후 .astype(np.float32) 된 배열에 바로 적용 가능.

    Args:
        np_rgb_float32: (H, W, 3) float32, 값 범위 [0, 255].

    Returns:
        (H, W, 3) float32, 값 범위 [0, 255].
    """
    np_u8 = np.clip(np_rgb_float32, 0, 255).astype(np.uint8)
    return apply_svs_to_hamamatsu(np_u8).astype(np.float32)


def is_svs_path(str_path: str) -> bool:
    """파일 확장자로 SVS 판정. Aperio/Leica 대상."""
    return str(str_path).lower().endswith(".svs")
