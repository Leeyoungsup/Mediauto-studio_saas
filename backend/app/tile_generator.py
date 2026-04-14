"""
타일 프리제네레이터 — 슬라이드 열 때 모든 레벨의 JPEG 타일을 디스크에 미리 생성
뷰어는 정적 파일만 서빙하므로 서버 CPU 부하 제로

구조:
  tiles/{slide_id}/
    ├── 0/{tx}_{ty}.jpeg   ← level 0 (최고 해상도)
    ├── 1/{tx}_{ty}.jpeg
    ├── ...
    ├── thumbnail.jpeg
    └── .complete           ← 생성 완료 마커
"""

import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import openslide

from app.config import settings

_thumb_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="thumb")

TILE_SIZE = settings.TILE_SIZE


# ── 진행 상태 ──

class TileGenProgress:
    __slots__ = ("total_tiles", "generated_tiles", "current_level", "status", "error")

    def __init__(self):
        self.total_tiles = 0
        self.generated_tiles = 0
        self.current_level = -1
        self.status = "pending"  # pending | generating | completed | error
        self.error = None

    @property
    def progress(self):
        if self.total_tiles == 0:
            return 0
        return min(100, int(self.generated_tiles / self.total_tiles * 100))

    def to_dict(self):
        return {
            "status": self.status,
            "progress": self.progress,
            "total_tiles": self.total_tiles,
            "generated_tiles": self.generated_tiles,
            "current_level": self.current_level,
            "error": self.error,
        }


_progress: dict[str, TileGenProgress] = {}
_progress_lock = threading.Lock()


def get_tiles_dir(filename: str) -> Path:
    """원본 파일명 기반 타일 디렉토리 (확장자 제외)"""
    stem = Path(filename).stem
    return Path(settings.TILES_DIR) / stem


def tiles_ready(filename: str) -> bool:
    """타일 생성이 완료되었는지 확인"""
    return (get_tiles_dir(filename) / ".complete").exists()


def get_progress(filename: str) -> Optional[dict]:
    """진행 상태 반환 (없으면 None)"""
    with _progress_lock:
        p = _progress.get(filename)
        if p:
            return p.to_dict()
    # 이미 완료된 경우
    if tiles_ready(filename):
        return {"status": "completed", "progress": 100,
                "total_tiles": 0, "generated_tiles": 0,
                "current_level": -1, "error": None}
    return None


def start_generation(filename: str, file_path: str):
    """백그라운드 스레드에서 타일 생성 시작 (이미 완료/진행 중이면 무시)"""
    if tiles_ready(filename):
        return

    with _progress_lock:
        if filename in _progress and _progress[filename].status == "generating":
            return  # 이미 진행 중

    thread = threading.Thread(
        target=_generate_tiles,
        args=(filename, file_path),
        daemon=True,
    )
    thread.start()


def _generate_tiles(filename: str, file_path: str):
    """타일 생성 워커 — 낮은 해상도(높은 레벨)부터 생성하여 뷰어가 빠르게 볼 수 있도록"""
    progress = TileGenProgress()
    with _progress_lock:
        _progress[filename] = progress

    tiles_dir = get_tiles_dir(filename)

    try:
        slide = openslide.OpenSlide(file_path)

        # ICC profile → sRGB transform (있으면 픽셀 한 번 변환 후 plain JPEG 저장)
        icc_transform = None
        try:
            obj_profile = getattr(slide, "color_profile", None)
            if obj_profile is not None:
                from PIL import ImageCms
                obj_srgb = ImageCms.createProfile("sRGB")
                icc_transform = ImageCms.buildTransform(obj_profile, obj_srgb, "RGB", "RGB")
        except Exception as e:
            print(f"[tile_generator] ICC transform 실패 ({filename}): {e}")

        def _to_srgb(img_rgb):
            if icc_transform is None:
                return img_rgb
            try:
                from PIL import ImageCms
                return ImageCms.applyTransform(img_rgb, icc_transform)
            except Exception:
                return img_rgb

        # 뷰어가 실제 사용하는 stage level 만 프리생성 (중복 제거)
        # SlideInfo._setup_level_stages 와 동일 로직
        int_total = slide.level_count
        if int_total == 1:
            list_stage_levels = [0]
        elif int_total == 2:
            list_stage_levels = [0, 1]
        elif int_total == 3:
            list_stage_levels = [0, 1, 2]
        else:
            float_step = (int_total - 1) / 3.0
            list_stage_levels = sorted(set([
                0,
                int(round(float_step)),
                int(round(float_step * 2)),
                min(int_total - 1, int(round(float_step * 3))),
            ]))

        # 각 레벨 타일 수 합산
        list_level_layout = []
        int_total_tiles = 0
        for int_level in list_stage_levels:
            lw, lh = slide.level_dimensions[int_level]
            int_nx = (lw + TILE_SIZE - 1) // TILE_SIZE
            int_ny = (lh + TILE_SIZE - 1) // TILE_SIZE
            list_level_layout.append((int_level, int_nx, int_ny,
                                      slide.level_downsamples[int_level]))
            int_total_tiles += int_nx * int_ny

        progress.total_tiles = int_total_tiles
        progress.status = "generating"

        # 썸네일 먼저 생성
        thumb_path = tiles_dir / "thumbnail.jpeg"
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        if not thumb_path.exists():
            thumb = slide.get_thumbnail((300, 300))
            _to_srgb(thumb.convert("RGB")).save(str(thumb_path), "JPEG", quality=85)

        # 거친 레벨(높은 인덱스)부터 → 뷰어가 첫 화면을 빠르게 채울 수 있게
        for int_level, int_nx, int_ny, float_ds in reversed(list_level_layout):
            progress.current_level = int_level
            level_dir = tiles_dir / str(int_level)
            level_dir.mkdir(parents=True, exist_ok=True)

            for ty in range(int_ny):
                for tx in range(int_nx):
                    tile_path = level_dir / f"{tx}_{ty}.jpeg"
                    if not tile_path.exists():
                        x = int(tx * TILE_SIZE * float_ds)
                        y = int(ty * TILE_SIZE * float_ds)
                        tile = slide.read_region((x, y), int_level, (TILE_SIZE, TILE_SIZE))
                        _to_srgb(tile.convert("RGB")).save(
                            str(tile_path), "JPEG", quality=settings.TILE_QUALITY
                        )
                    progress.generated_tiles += 1

        # 완료 마커
        (tiles_dir / ".complete").touch()
        progress.status = "completed"
        slide.close()

        # DB 플래그 마킹 (백그라운드 스레드 → 메인 루프로 스케줄)
        try:
            from app import slide_store
            slide_store.mark_tiles_ready_threadsafe(file_path)
        except Exception as e:
            print(f"[tile_generator] mark_tiles_ready failed ({filename}): {e}")

    except Exception as e:
        progress.status = "error"
        progress.error = str(e)
    finally:
        # 완료 후 일정 시간 뒤 progress 정리
        def _cleanup():
            time.sleep(60)
            with _progress_lock:
                _progress.pop(filename, None)
        threading.Thread(target=_cleanup, daemon=True).start()
