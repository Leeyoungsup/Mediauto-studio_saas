"""Hamamatsu 색 보정 variant 비교 진단 (확장판 v3).

18가지 서로 다른 보정을 같은 샘플 영역에 적용해 3x6 grid 로 저장한다.
1~9:    기존 (밝기/감마/채도/대비)
10~11:  per-channel cool shift (mild/medium) — 배경까지 시프트됨
12~13:  cool + desaturate 조합
14~15:  배경 자동측정 per-channel gain (+ desaturate)
16:     Linear-light Bradford CAT (4000→5500K, str 30%) — 배경 유지
17:     White-preserving midtone cool (섀도우/하이라이트 안 건드림)
18:     #17 + saturate 0.85

사용법:
  python backend/check_correction.py [slide_path]
"""

import os
import sys
from pathlib import Path

# ── OpenSlide DLL 경로 (openslide import 전에) ──
PROJECT_ROOT = Path(__file__).parent.parent.parent
_dll_paths = [
    PROJECT_ROOT / "libs" / "openslide_lib" / "bin",
    PROJECT_ROOT / "libs",
]
for _dp in _dll_paths:
    if _dp.exists():
        os.environ["OPENSLIDE_PATH"] = str(_dp)
        break
_path_additions = [
    str(p) for p in _dll_paths
    if p.exists() and str(p) not in os.environ.get("PATH", "")
]
if _path_additions:
    os.environ["PATH"] = os.pathsep.join(_path_additions) + os.pathsep + os.environ.get("PATH", "")
for _dp in _dll_paths:
    if _dp.exists():
        try:
            os.add_dll_directory(str(_dp))
        except (AttributeError, OSError):
            pass

BACKEND_DIR = Path(__file__).parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ── 보정 유틸 ──────────────────────────────────────────────────────────────

def _apply_gain(img_rgb, float_gain):
    """각 채널 공통 scalar gain."""
    tuple_m = (
        float_gain, 0.0, 0.0, 0.0,
        0.0, float_gain, 0.0, 0.0,
        0.0, 0.0, float_gain, 0.0,
    )
    return img_rgb.convert("RGB", tuple_m)


def _apply_channel_gain(img_rgb, float_rg, float_gg, float_bg):
    """채널별 독립 gain. cool/warm shift 구현용 (배경까지 시프트됨)."""
    tuple_m = (
        float_rg, 0.0, 0.0, 0.0,
        0.0, float_gg, 0.0, 0.0,
        0.0, 0.0, float_bg, 0.0,
    )
    return img_rgb.convert("RGB", tuple_m)


def _apply_gamma(img_rgb, float_gamma):
    """LUT 기반 gamma."""
    list_lut = [min(255, max(0, int(((i / 255.0) ** float_gamma) * 255 + 0.5))) for i in range(256)]
    return img_rgb.point(list_lut * 3)


def _apply_saturate(img_rgb, float_s):
    from PIL import ImageEnhance
    return ImageEnhance.Color(img_rgb).enhance(float_s)


def _apply_contrast(img_rgb, float_c):
    from PIL import ImageEnhance
    return ImageEnhance.Contrast(img_rgb).enhance(float_c)


def _measure_bg_gain(img_rgb, float_target=252.0, float_top_pct=5.0):
    """상위 밝기 픽셀 채널별 평균에서 per-channel gain 계산."""
    import numpy as np
    np_arr = np.asarray(img_rgb, dtype=np.float32)
    np_lum = 0.2126 * np_arr[..., 0] + 0.7152 * np_arr[..., 1] + 0.0722 * np_arr[..., 2]
    float_thr = np.percentile(np_lum, 100.0 - float_top_pct)
    np_mask = np_lum >= float_thr
    np_bg = np_arr[np_mask]
    np_mean = np_bg.mean(axis=0)
    return (
        float_target / float(np_mean[0]),
        float_target / float(np_mean[1]),
        float_target / float(np_mean[2]),
    )


def _build_cat_matrix(float_src_t, float_dst_t, float_strength):
    """Bradford CAT 매트릭스 (linear-RGB in/out 용).

    반환 매트릭스는 linear sRGB → linear sRGB 변환에 사용해야 함.
    gamma 인코딩 상태에서 적용하면 흰색까지 틀어짐.
    """
    import numpy as np

    def _cct_xy(float_t):
        if float_t <= 4000:
            float_x = (-0.2661239e9 / float_t**3 - 0.2343589e6 / float_t**2
                       + 0.8776956e3 / float_t + 0.179910)
        else:
            float_x = (-3.0258469e9 / float_t**3 + 2.1070379e6 / float_t**2
                       + 0.2226347e3 / float_t + 0.240390)
        if float_t <= 2222:
            float_y = (-1.1063814 * float_x**3 - 1.34811020 * float_x**2
                       + 2.18555832 * float_x - 0.20219683)
        elif float_t <= 4000:
            float_y = (-0.9549476 * float_x**3 - 1.37418593 * float_x**2
                       + 2.09137015 * float_x - 0.16748867)
        else:
            float_y = (3.0817580 * float_x**3 - 5.87338670 * float_x**2
                       + 3.75112997 * float_x - 0.37001483)
        return float_x, float_y

    def _xy_XYZ(float_x, float_y):
        return np.array([float_x / float_y, 1.0, (1.0 - float_x - float_y) / float_y])

    np_B = np.array([
        [0.8951, 0.2664, -0.1614],
        [-0.7502, 1.7135, 0.0367],
        [0.0389, -0.0685, 1.0296],
    ])
    np_B_inv = np.linalg.inv(np_B)
    np_m_rgb_xyz = np.array([
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ])
    np_m_xyz_rgb = np.linalg.inv(np_m_rgb_xyz)
    tuple_sx = _cct_xy(float_src_t)
    tuple_dx = _cct_xy(float_dst_t)
    np_Xs = _xy_XYZ(*tuple_sx)
    np_Xd = _xy_XYZ(*tuple_dx)
    np_rs = np_B @ np_Xs
    np_rd = np_B @ np_Xd
    np_cat = np_B_inv @ np.diag(np_rd / np_rs) @ np_B
    np_cat_blend = (1.0 - float_strength) * np.eye(3) + float_strength * np_cat
    return np_m_xyz_rgb @ np_cat_blend @ np_m_rgb_xyz


def _apply_linear_cat(img_rgb, np_m):
    """sRGB gamma decode → linear matrix mult → sRGB gamma encode.

    np_m 은 linear sRGB → linear sRGB 매트릭스 (_build_cat_matrix 결과).
    흰색(1.0) 이 매트릭스 특성상 거의 흰색으로 유지됨.
    """
    import numpy as np
    from PIL import Image
    np_arr = np.asarray(img_rgb, dtype=np.float32) / 255.0
    np_lin = np.where(np_arr <= 0.04045,
                      np_arr / 12.92,
                      ((np_arr + 0.055) / 1.055) ** 2.4)
    np_out = np_lin @ np_m.T
    np_out = np.clip(np_out, 0.0, 1.0)
    np_srgb = np.where(np_out <= 0.0031308,
                       np_out * 12.92,
                       1.055 * (np_out ** (1.0 / 2.4)) - 0.055)
    np_u8 = np.clip(np_srgb * 255.0 + 0.5, 0.0, 255.0).astype(np.uint8)
    return Image.fromarray(np_u8, "RGB")


def _apply_midtone_cool(img_rgb, float_kr=20.0, float_kb=20.0):
    """White-preserving midtone cool shift.

    R' = R − kr · R·(255−R)/16384
    B' = B + kb · B·(255−B)/16384
    중간톤(R≈128 / B≈128) 에서 최대 효과, 0/255 근처는 거의 0 효과.
    → 흰 배경, 검은 텍스트 유지되며 조직 색만 살짝 cool 쪽.
    """
    import numpy as np
    from PIL import Image
    np_arr = np.asarray(img_rgb, dtype=np.float32)
    np_r = np_arr[..., 0]
    np_g = np_arr[..., 1]
    np_b = np_arr[..., 2]
    np_bump_r = np_r * (255.0 - np_r) / 16384.0
    np_bump_b = np_b * (255.0 - np_b) / 16384.0
    np_r2 = np_r - float_kr * np_bump_r
    np_b2 = np_b + float_kb * np_bump_b
    np_out = np.stack([np_r2, np_g, np_b2], axis=-1)
    np_u8 = np.clip(np_out + 0.5, 0.0, 255.0).astype(np.uint8)
    return Image.fromarray(np_u8, "RGB")


def _mean_rgb(img_rgb):
    import statistics
    list_px = list(img_rgb.getdata())
    return tuple(round(statistics.mean(v[i] for v in list_px), 1) for i in range(3))


# ── 메인 ───────────────────────────────────────────────────────────────────

def main():
    import openslide
    from PIL import Image, ImageDraw, ImageFont

    if len(sys.argv) >= 2:
        path_slide = Path(sys.argv[1])
    else:
        path_slide = Path("backend/uploads/IHC(PD-L1)/CODIPAI-STBX-SS-04335-I-PD-22.ndpi")

    if not path_slide.exists():
        print(f"파일 없음: {path_slide}")
        sys.exit(1)

    print(f"[*] 슬라이드: {path_slide.name}")
    slide = openslide.OpenSlide(str(path_slide))
    print(f"    dimensions: {slide.dimensions}")

    # 중앙 1024x1024 읽기
    int_w, int_h = slide.dimensions
    int_sx = max(0, int_w // 2 - 512)
    int_sy = max(0, int_h // 2 - 512)
    obj_raw = slide.read_region((int_sx, int_sy), 0, (1024, 1024)).convert("RGB")
    slide.close()

    # 배경 자동측정
    tuple_bg_gain = _measure_bg_gain(obj_raw)
    print(f"[*] 배경 자동측정 gain: "
          f"R×{tuple_bg_gain[0]:.3f}, G×{tuple_bg_gain[1]:.3f}, B×{tuple_bg_gain[2]:.3f}")

    # Linear-light Bradford CAT 매트릭스 (4000K → 5500K, 30% 강도)
    np_cat_linear = _build_cat_matrix(4000.0, 5500.0, 0.3)

    # 18개 variant 정의
    list_variants = [
        ("1. raw (보정 없음)", obj_raw),
        ("2. gain x1.085 (255/235)", _apply_gain(obj_raw, 255.0 / 235.0)),
        ("3. gain x0.92 (235/255)", _apply_gain(obj_raw, 235.0 / 255.0)),
        ("4. gamma 0.85 (midtones 밝게)", _apply_gamma(obj_raw, 0.85)),
        ("5. gamma 1.15 (midtones 어둡게)", _apply_gamma(obj_raw, 1.15)),
        ("6. saturate x0.8", _apply_saturate(obj_raw, 0.8)),
        ("7. saturate x1.2", _apply_saturate(obj_raw, 1.2)),
        ("8. contrast x1.15", _apply_contrast(obj_raw, 1.15)),
        ("9. gain1.085 + saturate0.9",
         _apply_saturate(_apply_gain(obj_raw, 255.0 / 235.0), 0.9)),
        ("10. cool mild (R0.96 / B1.04)",
         _apply_channel_gain(obj_raw, 0.96, 1.00, 1.04)),
        ("11. cool med (R0.93 / B1.07)",
         _apply_channel_gain(obj_raw, 0.93, 1.00, 1.07)),
        ("12. #10 + saturate 0.85",
         _apply_saturate(_apply_channel_gain(obj_raw, 0.96, 1.00, 1.04), 0.85)),
        ("13. #11 + sat0.75 + gain1.04",
         _apply_gain(
             _apply_saturate(_apply_channel_gain(obj_raw, 0.93, 1.00, 1.07), 0.75),
             1.04)),
        (f"14. auto-bg (R×{tuple_bg_gain[0]:.2f} G×{tuple_bg_gain[1]:.2f} B×{tuple_bg_gain[2]:.2f})",
         _apply_channel_gain(obj_raw, *tuple_bg_gain)),
        ("15. #14 + saturate 0.80",
         _apply_saturate(_apply_channel_gain(obj_raw, *tuple_bg_gain), 0.80)),
        ("16. Linear Bradford 4000→5500K str30% (white 유지)",
         _apply_linear_cat(obj_raw, np_cat_linear)),
        ("17. Midtone-only cool (kr=20, kb=20, white 유지)",
         _apply_midtone_cool(obj_raw, 20.0, 20.0)),
        ("18. #17 + saturate 0.85",
         _apply_saturate(_apply_midtone_cool(obj_raw, 20.0, 20.0), 0.85)),
    ]

    # 각 variant 평균 RGB 출력
    print(f"\n{'Variant':<55s} {'R':>7s} {'G':>7s} {'B':>7s}")
    print("-" * 80)
    for str_label, obj_img in list_variants:
        tuple_rgb = _mean_rgb(obj_img)
        print(f"{str_label:<55s} {tuple_rgb[0]:>7.1f} {tuple_rgb[1]:>7.1f} {tuple_rgb[2]:>7.1f}")

    # 3 cols × 6 rows grid
    int_cell = 400
    int_gap = 8
    int_label_h = 26
    int_cols = 3
    int_rows = 6
    int_w_grid = int_cols * int_cell + (int_cols - 1) * int_gap
    int_h_grid = int_rows * (int_cell + int_label_h) + (int_rows - 1) * int_gap
    obj_grid = Image.new("RGB", (int_w_grid, int_h_grid), (240, 240, 240))
    obj_draw = ImageDraw.Draw(obj_grid)
    try:
        obj_font = ImageFont.truetype("malgun.ttf", 13)
    except Exception:
        try:
            obj_font = ImageFont.truetype("arial.ttf", 13)
        except Exception:
            obj_font = ImageFont.load_default()

    for int_i, (str_label, obj_img) in enumerate(list_variants):
        int_r = int_i // int_cols
        int_c = int_i % int_cols
        int_x = int_c * (int_cell + int_gap)
        int_y = int_r * (int_cell + int_label_h + int_gap)
        obj_draw.rectangle(
            (int_x, int_y, int_x + int_cell, int_y + int_label_h),
            fill=(30, 30, 30),
        )
        obj_draw.text(
            (int_x + 6, int_y + 5), str_label,
            fill=(255, 255, 255), font=obj_font,
        )
        obj_img_resized = obj_img.resize((int_cell, int_cell), Image.LANCZOS)
        obj_grid.paste(obj_img_resized, (int_x, int_y + int_label_h))

    path_out = BACKEND_DIR / "compare_variants.jpeg"
    obj_grid.save(str(path_out), "JPEG", quality=92)
    print(f"\n[*] grid 이미지: {path_out}")
    print(f"    3 cols × 6 rows (18 variants), 셀 {int_cell}x{int_cell}.")
    print(f"    16, 17, 18 은 흰 배경 유지하면서 cool shift 하는 variant.")


if __name__ == "__main__":
    main()
