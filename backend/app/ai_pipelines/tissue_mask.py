"""조직 마스크 생성 — γ 전처리 + H-DAB 분리 + Otsu + 텍스처 조합.

routers/ai.py 의 _run_detection / _run_marker_detection_pipeline 가 공유.
큰 슬라이드의 검출 영역을 미리 좁혀 GPU 추론 비용을 줄인다.
"""

import numpy as np

# ── tissue_mask 감마 전처리 상수 ──
# 썸네일에 v_out = 255 * (v_in/255) ^ γ 를 적용한 뒤 H-DAB/Otsu/텍스처 파이프라인을 돌린다.
# γ 가 커질수록 배경 피크가 더 많이 내려가 definite_bg 제외 범위가 좁아져 옅은 조직까지
# 포획된다. ai_mask_test.ipynb 스윕 결과 γ=4.0 이 옅은 stroma/조직 경계까지 확실히
# 잡으면서 실제 운용 슬라이드에서 과잉 포함이 허용 범위 내에 머무는 값으로 확인됨.
FLOAT_TISSUE_MASK_GAMMA = 4.0
_NP_TISSUE_MASK_GAMMA_LUT = np.clip(
    np.power(np.arange(256, dtype=np.float32) / 255.0,
             FLOAT_TISSUE_MASK_GAMMA) * 255.0,
    0, 255,
).astype(np.uint8)


def create_tissue_mask(slide, icc_transform=None):
    """조직 마스크 생성 — γ 전처리 후 H-DAB 분리 → (Hem ∪ DAB ∪ 텍스처) − 확실한 배경.

    단일 Hematoxylin Otsu 만으로는 DAB 가 강하게 덮인 영역(H 가 억제됨)이나
    염색이 거의 없지만 구조가 있는 조직이 빠질 수 있음. 따라서:
      0) 썸네일에 γ=4.0 감마 전처리 — 배경 피크를 내려 definite_bg 제외를 덜 공격적으로
      1) H-DAB color deconvolution (Ruifrok & Johnston 2001) → H / DAB 채널 분리
      2) 각 채널 Otsu → 염색 영역 검출
      3) 국소 표준편차(텍스처) Otsu → 무염색 조직 보완
      4) Union 후, 확실한 유리 배경(그레이 히스토그램 최고 피크의 95% 이상) 강제 제외

    icc_transform 이 주어지면 썸네일에 적용해 다른 AI 경로와 색상 일관성 유지.
    """
    import cv2

    try:
        downsample = 128
        thumbnail = slide.get_thumbnail((
            slide.dimensions[0] // downsample,
            slide.dimensions[1] // downsample,
        ))
        if icc_transform is not None:
            from PIL import ImageCms
            thumbnail = thumbnail.convert('RGB')
            ImageCms.applyTransform(thumbnail, icc_transform, inPlace=True)
        thumbnail = np.array(thumbnail)
        if len(thumbnail.shape) == 3:
            rgb = thumbnail[:, :, :3]
        else:
            rgb = cv2.cvtColor(thumbnail, cv2.COLOR_GRAY2RGB)

        # ── 감마 전처리 (γ=4.0) ──
        # rgb 는 uint8 이므로 LUT 인덱싱 한 번이면 끝. 하위 단계 모두 γ 적용본을 본다.
        rgb = _NP_TISSUE_MASK_GAMMA_LUT[rgb]

        # ── H-DAB color deconvolution (Ruifrok & Johnston, 2001) ──
        stain_matrix = np.array([
            [0.650, 0.704, 0.286],   # Hematoxylin
            [0.268, 0.570, 0.776],   # DAB
            [0.711, 0.423, 0.500],   # Residual
        ], dtype=np.float64)
        stain_matrix = stain_matrix / np.linalg.norm(stain_matrix, axis=1, keepdims=True)
        deconv_matrix = np.linalg.inv(stain_matrix)

        rgb_f = np.maximum(rgb.astype(np.float64), 1.0)
        od = -np.log(rgb_f / 255.0)
        h, w = rgb.shape[:2]
        stain_od = (od.reshape(-1, 3) @ deconv_matrix.T).reshape(h, w, 3)

        hematoxylin_od = np.clip(stain_od[:, :, 0], 0, None)
        dab_od = np.clip(stain_od[:, :, 1], 0, None)

        hem_max = max(np.percentile(hematoxylin_od, 99.5), 0.01)
        dab_max = max(np.percentile(dab_od, 99.5), 0.01)
        hem_u8 = np.clip(hematoxylin_od / hem_max * 255, 0, 255).astype(np.uint8)
        dab_u8 = np.clip(dab_od / dab_max * 255, 0, 255).astype(np.uint8)

        _, hem_mask = cv2.threshold(hem_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        _, dab_mask = cv2.threshold(dab_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # ── 텍스처(국소 std) — 무염색이지만 구조 있는 조직 보완 ──
        np_gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        gray_f = np_gray.astype(np.float32)
        ksize = (15, 15)
        local_mean = cv2.blur(gray_f, ksize)
        local_sq_mean = cv2.blur(gray_f ** 2, ksize)
        local_std = np.sqrt(np.maximum(local_sq_mean - local_mean ** 2, 0))
        std_scaled = np.clip(local_std * 10, 0, 255).astype(np.uint8)
        _, texture_mask = cv2.threshold(
            std_scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        # ── 확실한 유리 배경 제거 (히스토그램 상단 피크의 95% 이상) ──
        hist = cv2.calcHist([np_gray], [0], None, [256], [0, 256]).flatten()
        bg_peak = int(np.argmax(hist[128:]) + 128)
        definite_bg = (np_gray >= int(bg_peak * 0.95))

        mask = (hem_mask > 0) | (dab_mask > 0) | (texture_mask > 0)
        mask[definite_bg] = False
        mask = (mask.astype(np.uint8)) * 255

        # 조각난 마스크를 넓게 CLOSE 해서 인접 조직 조각들을 하나로 묶음
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

        # ── 외곽 컨투어만 뽑아 솔리드로 채움 ──
        # → 내부 구멍(염색 옅어서 빠진 세포 간극)도 전부 tissue 로 포함
        # → 작은 면적 컨투어는 노이즈로 간주해 드랍
        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        filled = np.zeros_like(mask)
        int_min_area = max(int(h * w * 0.0005), 50)  # 썸네일 면적의 0.05% 이상
        for cnt in contours:
            if cv2.contourArea(cnt) < int_min_area:
                continue
            cv2.drawContours(filled, [cnt], -1, 255, thickness=cv2.FILLED)
        mask = filled

        target_w = slide.dimensions[0] // 64
        target_h = slide.dimensions[1] // 64
        mask = cv2.resize(mask, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
        return mask
    except Exception:
        w, h = slide.dimensions
        return np.ones((h // 64, w // 64), dtype=np.uint8) * 255
