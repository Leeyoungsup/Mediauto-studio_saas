"""
SlideManager — 열린 슬라이드 객체 관리 (세션 기반)
OpenSlide 객체를 캐싱하여 매 타일 요청마다 다시 열지 않도록 함
"""

import hashlib
import math
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Tuple

import openslide

# ── 3단계 타일 피라미드 ──
# 모든 stage 는 level 0 에서 읽어 downsample 팩터만큼 리사이즈하여 1024x1024 로 저장.
#   stage 0 : level0 에서 1024x1024 그대로 (downsample 1)
#   stage 1 : level0 에서 4096x4096 읽어 1024x1024 로 리사이즈 (downsample 4)
#   stage 2 : level0 에서 8192x8192 읽어 1024x1024 로 리사이즈 (downsample 8)
# TileViewer 의 STAGE_DOWNSAMPLES / STAGE_READ_SIZE 와 반드시 동일해야 한다.
STAGE_DOWNSAMPLES = [1, 4, 8]
TILE_SIZE_OUT = 1024
STAGE_READ_SIZE = [TILE_SIZE_OUT * ds for ds in STAGE_DOWNSAMPLES]  # [1024, 4096, 8192]
STAGE_COUNT = len(STAGE_DOWNSAMPLES)


# ─────────────────────────────────────────────────────────────────────────────
# Hamamatsu color correction (ICC 없는 NDPI 용 fallback)
#
# NDPI 는 ICC profile 을 임베드하지 않는 경우가 많아 OpenSlide 의 raw RGB 가
# NDP.view2 의 디스플레이 결과와 달라진다 (어둡고 노란 tone). 두 가지를 보정:
#   A) hamamatsu.Target.White.Intensity 로 white point gain (예: 255/235≈1.085)
#   B) hamamatsu.LightSource.ColorTemperature.Micro 로 Bradford CAT (CCT→D65)
# 결합된 3x3 행렬을 PIL Image.convert("RGB", matrix=...) 에 쓸 4x3 튜플로
# 리턴한다. 가우스급 정확도는 아니지만 C-optimized 경로로 1024² 에서 수 ms.
# ─────────────────────────────────────────────────────────────────────────────


def _cct_to_xyz(float_cct: float):
    """CCT(Kelvin) → normalized XYZ (Y=1).

    Planckian locus 근사 (CIE standard). 4000-25000K 범위에서 충분히 정확.
    """
    import numpy as np
    float_t = float(float_cct)
    if float_t <= 7000.0:
        float_xc = (
            -4.6070e9 / float_t**3
            + 2.9678e6 / float_t**2
            + 0.09911e3 / float_t
            + 0.244063
        )
    else:
        float_xc = (
            -2.0064e9 / float_t**3
            + 1.9018e6 / float_t**2
            + 0.24748e3 / float_t
            + 0.237040
        )
    float_yc = -3.000 * float_xc**2 + 2.870 * float_xc - 0.275
    return np.array([float_xc / float_yc, 1.0, (1.0 - float_xc - float_yc) / float_yc])


def _bradford_cat(np_src_xyz, np_dst_xyz):
    """Bradford CAT 3x3 매트릭스: src whitepoint XYZ → dst whitepoint XYZ."""
    import numpy as np
    np_m_bfd = np.array([
        [0.8951, 0.2664, -0.1614],
        [-0.7502, 1.7135, 0.0367],
        [0.0389, -0.0685, 1.0296],
    ])
    np_src_lms = np_m_bfd @ np_src_xyz
    np_dst_lms = np_m_bfd @ np_dst_xyz
    np_diag = np.diag(np_dst_lms / np_src_lms)
    return np.linalg.inv(np_m_bfd) @ np_diag @ np_m_bfd


def _get_hamamatsu_params(slide) -> Optional[Tuple[float, int]]:
    """슬라이드에서 Hamamatsu 보정 파라미터를 추출. 실패 시 None.

    Returns:
      (float_cct, int_white_intensity) — 둘 중 하나라도 없으면 기본값 사용.
      둘 다 기본값 (D65, 255) 이면 보정 불필요 → None 리턴.
    """
    str_vendor = slide.properties.get("openslide.vendor", "")
    if str_vendor.lower() != "hamamatsu":
        return None
    str_white = slide.properties.get("hamamatsu.Target.White.Intensity")
    str_cct = slide.properties.get("hamamatsu.LightSource.ColorTemperature.Micro")
    try:
        int_white = int(float(str_white)) if str_white else 255
    except Exception:
        int_white = 255
    try:
        float_cct = float(str_cct) if str_cct else 6500.0
    except Exception:
        float_cct = 6500.0
    # 보정이 의미 있을 때만 반환 (기본값이면 no-op)
    if int_white >= 255 and 6400 <= float_cct <= 6600:
        return None
    return (float_cct, int_white)


def build_hamamatsu_matrix(float_cct: float, int_white_intensity: int):
    """Hamamatsu 보정용 PIL 4x3 매트릭스 (sRGB-encoded 공간에서 직접 적용).

    pipeline: sRGB(D65) → XYZ → Bradford(CCT→D65) → XYZ → sRGB → gain scale.
    gamma decode 는 생략 — 디스플레이 톤 보정 목적상 시각차는 미미하고
    PIL C 경로가 훨씬 빠르다.

    Returns:
      (a,b,c,d, e,f,g,h, i,j,k,l) — Image.convert("RGB", matrix=...) 인자.
    """
    import numpy as np
    np_m_srgb_to_xyz = np.array([
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ])
    np_m_xyz_to_srgb = np.linalg.inv(np_m_srgb_to_xyz)
    np_src = _cct_to_xyz(float_cct)
    np_dst = _cct_to_xyz(6500.0)
    np_cat = _bradford_cat(np_src, np_dst)
    np_m = np_m_xyz_to_srgb @ np_cat @ np_m_srgb_to_xyz
    float_gain = 255.0 / max(1.0, float(int_white_intensity))
    np_m = np_m * float_gain
    return (
        float(np_m[0, 0]), float(np_m[0, 1]), float(np_m[0, 2]), 0.0,
        float(np_m[1, 0]), float(np_m[1, 1]), float(np_m[1, 2]), 0.0,
        float(np_m[2, 0]), float(np_m[2, 1]), float(np_m[2, 2]), 0.0,
    )


def build_color_correction(slide):
    """슬라이드에 맞는 색 보정 객체를 빌드.

    우선순위:
      1) ICC profile 존재 → ImageCms transform
      2) vendor=hamamatsu + 기본 아닌 params → PIL 4x3 매트릭스 (CAT+gain)
      3) 둘 다 없으면 None (원본 그대로)

    Returns:
      (obj_correction, str_hash, bool_applied)
      - obj_correction: ICC transform 객체 또는 4x3 tuple 또는 None
      - str_hash: 캐시 무효화용 해시 (None 이면 보정 없음을 의미)
      - bool_applied: 실제로 적용 가능한 보정이 빌드됐는지
    """
    # 1) ICC profile
    try:
        obj_profile = getattr(slide, "color_profile", None)
        if obj_profile is not None:
            from PIL import ImageCms
            obj_srgb = ImageCms.createProfile("sRGB")
            obj_transform = ImageCms.buildTransform(obj_profile, obj_srgb, "RGB", "RGB")
            # 해시 — 프로파일 bytes 우선, 없으면 description
            if hasattr(obj_profile, "tobytes"):
                str_hash = hashlib.md5(obj_profile.tobytes()).hexdigest()
            else:
                str_desc = ImageCms.getProfileDescription(obj_profile) or ""
                str_hash = hashlib.md5(("desc:" + str_desc).encode("utf-8")).hexdigest()
            return (obj_transform, str_hash, True)
    except Exception as e:
        print(f"[color_correction] ICC transform 실패: {e}")

    # 2) Hamamatsu fallback
    tuple_params = _get_hamamatsu_params(slide)
    if tuple_params is not None:
        float_cct, int_white = tuple_params
        try:
            tuple_matrix = build_hamamatsu_matrix(float_cct, int_white)
            str_hash = hashlib.md5(
                f"hama:CCT={float_cct:.1f},WI={int_white}".encode("utf-8")
            ).hexdigest()
            return (tuple_matrix, str_hash, True)
        except Exception as e:
            print(f"[color_correction] Hamamatsu matrix 빌드 실패: {e}")

    # 3) 보정 없음
    return (None, None, False)


def apply_color_correction(img_rgb, obj_correction):
    """빌드된 보정 객체를 RGB 이미지에 적용. 객체 타입을 자동 판별.

    - tuple(12) → PIL convert("RGB", matrix=...) 경로 (Hamamatsu)
    - 그 외 (ImageCmsTransform) → ImageCms.applyTransform 경로
    """
    if obj_correction is None:
        return img_rgb
    if isinstance(obj_correction, tuple):
        try:
            return img_rgb.convert("RGB", obj_correction)
        except Exception:
            return img_rgb
    try:
        from PIL import ImageCms
        return ImageCms.applyTransform(img_rgb, obj_correction)
    except Exception:
        return img_rgb


class SlideInfo:
    """열린 슬라이드의 메타 정보"""

    def __init__(self, slide: openslide.OpenSlide, file_path: str):
        self.slide = slide
        self.file_path = file_path
        self.opened_at = time.time()
        self.last_accessed = time.time()

        # 메타데이터 캐싱
        self.dimensions = slide.dimensions
        self.level_count = slide.level_count
        self.level_dimensions = list(slide.level_dimensions)
        self.level_downsamples = list(slide.level_downsamples)

        # MPP
        mpp_x = slide.properties.get("openslide.mpp-x")
        mpp_y = slide.properties.get("openslide.mpp-y")
        if mpp_x and mpp_y:
            self.mpp_x = float(mpp_x)
            self.mpp_y = float(mpp_y)
            self.mpp = (self.mpp_x + self.mpp_y) / 2
        else:
            self.mpp_x = 0.25
            self.mpp_y = 0.25
            self.mpp = 0.25  # 기본값 (40x)

        # 추가 메타데이터
        self.vendor = slide.properties.get("openslide.vendor", "Unknown")
        self.objective_power = slide.properties.get("openslide.objective-power", "Unknown")

        # 색 보정 — ICC 있으면 ICC transform, 없고 Hamamatsu 면 CAT+gain 매트릭스.
        # 둘 다 아니면 원본 그대로 (None). build_color_correction 참조.
        obj_corr, str_hash, bool_applied = build_color_correction(slide)
        self.color_correction = obj_corr
        self.color_correction_hash = str_hash
        self.color_correction_applied = bool_applied
        # icc_transform 속성은 AI 모듈이 직접 ImageCms.applyTransform 에 넘기므로
        # "ICC 객체 또는 None" 으로 엄격히 유지. Hamamatsu 매트릭스(tuple) 는 포함 X.
        # AI 분석은 학습 시의 색 공간을 보존하기 위해 Hamamatsu fallback 을 건너뛰는 편이 안전.
        self.icc_transform = obj_corr if not isinstance(obj_corr, tuple) else None

        # 물리적 크기 (mm)
        w, h = self.dimensions
        self.physical_width_mm = w * self.mpp_x / 1000.0
        self.physical_height_mm = h * self.mpp_y / 1000.0

        # 3단계 stage 타일 피라미드 메타 (level 0 에서 고정 downsample [1,4,8])
        self.stage_downsamples = list(STAGE_DOWNSAMPLES)
        self.stage_count = STAGE_COUNT
        # 각 stage 의 픽셀 해상도 — frontend 에서 nx/ny 계산에 사용
        w0, h0 = self.dimensions
        self.stage_dimensions = [
            (max(1, math.ceil(w0 / ds)), max(1, math.ceil(h0 / ds)))
            for ds in STAGE_DOWNSAMPLES
        ]

    def get_stage(self, effective_mpp: float) -> int:
        """effective MPP 기반 stage index (0/1/2) 선택."""
        if effective_mpp < 2.0:
            return 0
        elif effective_mpp < 15.0:
            return 1
        else:
            return 2

    # 하위 호환 — 기존 /stage-level 엔드포인트용. stage index 를 그대로 반환.
    def get_stage_level(self, effective_mpp: float) -> int:
        return self.get_stage(effective_mpp)

    def touch(self):
        self.last_accessed = time.time()

    def apply_icc(self, img_rgb):
        """RGB PIL 이미지에 색 보정을 적용 (ICC 또는 Hamamatsu CAT+gain).

        이름은 하위 호환을 위해 apply_icc 로 유지하지만, 내부적으로
        ICC 없을 때 Hamamatsu fallback 도 처리한다.
        """
        return apply_color_correction(img_rgb, self.color_correction)


class SlideManager:
    """열린 슬라이드 관리자 (thread-safe).

    Generation counter:
        각 slide_id 에 대해 단조 증가 generation 을 유지한다. close() 가 호출되면
        해당 slide_id 의 generation 이 +1 된다. 워커 스레드가 thread-local
        핸들을 재사용할 때 (app.thread_slide_pool) 이 generation 을 비교해
        stale 이면 자기 핸들을 닫고 재오픈해 leak 을 방지한다.
    """

    def __init__(self):
        self._slides: Dict[str, SlideInfo] = {}
        self._generations: Dict[str, int] = {}
        self._lock = threading.Lock()

    def open(self, slide_id: str, file_path: str) -> SlideInfo:
        """슬라이드 열기 (이미 열려있으면 캐시 반환)"""
        with self._lock:
            if slide_id in self._slides:
                info = self._slides[slide_id]
                info.touch()
                return info

            slide = openslide.OpenSlide(file_path)
            info = SlideInfo(slide, file_path)
            self._slides[slide_id] = info
            # 최초 open 시 generation 0 부여 (이미 있으면 유지)
            self._generations.setdefault(slide_id, 0)
            return info

    def get(self, slide_id: str) -> Optional[SlideInfo]:
        """열린 슬라이드 가져오기"""
        with self._lock:
            info = self._slides.get(slide_id)
            if info:
                info.touch()
            return info

    def get_generation(self, slide_id: str) -> int:
        """주어진 slide_id 의 현재 generation. thread-local 핸들 무효화 판정용."""
        with self._lock:
            return self._generations.get(slide_id, 0)

    def close(self, slide_id: str):
        """슬라이드 닫기 — generation 을 bump 하여 모든 thread-local 핸들을 무효화."""
        with self._lock:
            self._generations[slide_id] = self._generations.get(slide_id, 0) + 1
            info = self._slides.pop(slide_id, None)
            if info:
                try:
                    info.slide.close()
                except Exception:
                    pass

    def close_all(self):
        """모든 슬라이드 닫기 — 전체 generation bump."""
        with self._lock:
            for str_sid in list(self._slides.keys()):
                self._generations[str_sid] = self._generations.get(str_sid, 0) + 1
            for info in self._slides.values():
                try:
                    info.slide.close()
                except Exception:
                    pass
            self._slides.clear()

    def list_slides(self):
        """열린 슬라이드 목록"""
        with self._lock:
            return {
                sid: {
                    "file_path": info.file_path,
                    "dimensions": info.dimensions,
                    "level_count": info.level_count,
                    "mpp": info.mpp,
                }
                for sid, info in self._slides.items()
            }


# 싱글톤
slide_manager = SlideManager()
