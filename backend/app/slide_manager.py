"""
SlideManager — 열린 슬라이드 객체 관리 (세션 기반)
OpenSlide 객체를 캐싱하여 매 타일 요청마다 다시 열지 않도록 함
"""

import math
import threading
import time
from typing import Optional, Dict, Tuple

import numpy as np
import openslide

# ── Hamamatsu NDP.view2 호환 색 보정 상수 ──
# NDP.view2 는 표시 gamma = 1.8 고정 + 배경을 Target.White.Intensity 로 맞춘다.
# ICC 프로파일이 임베드되지 않은 Hamamatsu 슬라이드에 한해
#   v_out = 255 * (v_in / Target.White.Intensity) ^ (1/1.8)
# 를 적용해 raw 를 NDP.view2 와 같은 톤으로 끌어올린다.
# Target.White.Intensity 는 슬라이드 header 에서 직접 읽음 — .npy 외부 파일 의존 없음.
FLOAT_NDP_GAMMA = 1.8
FLOAT_NDP_DEFAULT_WHITE = 235.0


def _build_ndp_lut(float_raw_white: float) -> np.ndarray:
    """raw_white → 255, gamma=1.8 매핑의 256-entry uint8 LUT."""
    if float_raw_white <= 0:
        float_raw_white = FLOAT_NDP_DEFAULT_WHITE
    np_x = np.clip(np.arange(256, dtype=np.float32) / float_raw_white, 0.0, 1.0)
    np_y = np.power(np_x, 1.0 / FLOAT_NDP_GAMMA) * 255.0
    return np.clip(np_y, 0, 255).astype(np.uint8)


def build_color_corrector(slide: "openslide.OpenSlide"):
    """OpenSlide 핸들에 대해 통일된 색 보정 callable 을 구성한다.

    우선순위:
      1) ICC profile 이 있으면 sRGB ImageCms transform 적용
      2) ICC 가 없고 vendor=hamamatsu 면 Target.White.Intensity + γ=1.8 LUT 적용
      3) 둘 다 없으면 pass-through

    반환: `(apply, dict_meta)`
      - apply(img_rgb: PIL.Image) -> PIL.Image
      - dict_meta:
          {
            "icc_applied": bool,
            "ndp_applied": bool,
            "ndp_white": float | None,
            "str_tag": "icc" | "ndp:<white>" | "raw",
          }

    이 함수 하나로 `SlideInfo`, `tile_generator`, `thumbnail-by-name` 이 모두
    같은 색 보정 로직을 공유하게 된다.
    """
    # 1) ICC transform
    icc_transform = None
    try:
        obj_profile = getattr(slide, "color_profile", None)
        if obj_profile is not None:
            from PIL import ImageCms
            obj_srgb = ImageCms.createProfile("sRGB")
            icc_transform = ImageCms.buildTransform(
                obj_profile, obj_srgb, "RGB", "RGB"
            )
    except Exception as e:
        print(f"[slide_manager] ICC transform 실패: {e}")
        icc_transform = None

    # 2) NDP LUT (ICC 없고 vendor=hamamatsu 일 때만)
    np_lut: Optional[np.ndarray] = None
    float_ndp_white: Optional[float] = None
    if icc_transform is None:
        str_vendor = str(slide.properties.get("openslide.vendor", "")).lower()
        if str_vendor == "hamamatsu":
            try:
                float_ndp_white = float(slide.properties.get(
                    "hamamatsu.Target.White.Intensity", FLOAT_NDP_DEFAULT_WHITE
                ))
            except (TypeError, ValueError):
                float_ndp_white = FLOAT_NDP_DEFAULT_WHITE
            np_lut = _build_ndp_lut(float_ndp_white)

    # 3) apply callable
    def _apply(img_rgb):
        if icc_transform is not None:
            try:
                from PIL import ImageCms
                return ImageCms.applyTransform(img_rgb, icc_transform)
            except Exception:
                return img_rgb
        if np_lut is not None:
            try:
                from PIL import Image
                np_img = np.asarray(img_rgb, dtype=np.uint8)
                np_out = np_lut[np_img]
                return Image.fromarray(np_out, "RGB")
            except Exception as e:
                print(f"[slide_manager] NDP LUT 적용 실패: {e}")
                return img_rgb
        return img_rgb

    dict_meta = {
        "icc_applied": icc_transform is not None,
        "ndp_applied": np_lut is not None,
        "ndp_white": float_ndp_white,
        "str_tag": (
            "icc" if icc_transform is not None
            else (f"ndp:{int(float_ndp_white)}" if np_lut is not None else "raw")
        ),
    }
    return _apply, dict_meta


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
        self.objective_power = slide.properties.get("openslide.objective-power", "Unknown")

        self.vendor = slide.properties.get("openslide.vendor", "Unknown")

        # 통합 색 보정기 — ICC → NDP LUT → raw 우선순위.
        # AI 추론 워커들은 여전히 `icc_transform` 을 직접 받아 쓰므로 해당 속성은
        # 실제 ImageCms transform 을 담아 둔다. 뷰어/타일/썸네일 경로는
        # `apply_icc()` 를 통해 통합 callable (ICC + NDP LUT) 을 쓴다.
        self._color_apply, self._color_meta = build_color_corrector(slide)
        self.icc_transform = None
        try:
            obj_profile = getattr(slide, "color_profile", None)
            if obj_profile is not None:
                from PIL import ImageCms
                obj_srgb = ImageCms.createProfile("sRGB")
                self.icc_transform = ImageCms.buildTransform(
                    obj_profile, obj_srgb, "RGB", "RGB"
                )
        except Exception:
            self.icc_transform = None
        # NDP LUT 적용 메타는 self._color_meta 에 보존 — 노이즈 방지 위해 별도 로그 X.

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
        """RGB PIL 이미지에 색 보정 적용 (ICC → NDP LUT → raw 순)."""
        return self._color_apply(img_rgb)


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
