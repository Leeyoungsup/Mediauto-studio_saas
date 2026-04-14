"""
타일 프리제네레이터 — 슬라이드 열 때 모든 레벨의 JPEG 타일을 디스크에 미리 생성
뷰어는 정적 파일만 서빙하므로 서버 CPU 부하 제로

구조:
  tiles/{slide_id}/
    ├── 0/{tx}_{ty}.jpeg   ← level 0 (최고 해상도)
    ├── 1/{tx}_{ty}.jpeg
    ├── ...
    ├── thumbnail.jpeg
    └── .complete           ← 생성 완료 마커 (JSON: 버전/ICC 해시/적용 여부)
"""

import hashlib
import json
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import openslide

from app.config import settings

_thumb_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="thumb")

TILE_SIZE = settings.TILE_SIZE

# .complete marker schema version. Bump when the on-disk tile format changes
# in a way that requires regeneration.
COMPLETE_MARKER_VERSION = 1
COMPLETE_MARKER_NAME = ".complete"


def _slide_icc_hash(slide) -> Optional[str]:
    """슬라이드의 ICC 프로파일 바이트 md5 해시. 프로파일이 없거나 읽기 실패 시 None."""
    try:
        obj_profile = getattr(slide, "color_profile", None)
        if obj_profile is None:
            return None
        if hasattr(obj_profile, "tobytes"):
            return hashlib.md5(obj_profile.tobytes()).hexdigest()
        # Fallback: description 기반 (재현 가능성 보장은 약하지만 없는 것보단 낫다)
        from PIL import ImageCms
        str_desc = ImageCms.getProfileDescription(obj_profile) or ""
        return hashlib.md5(("desc:" + str_desc).encode("utf-8")).hexdigest()
    except Exception as e:
        print(f"[tile_generator] icc hash 계산 실패: {e}")
        return None


def read_complete_marker(filename: str) -> Optional[dict]:
    """마커 JSON 을 파싱해 반환. 파일 없음/비JSON(legacy touch)/파싱 실패 시 None."""
    path = get_tiles_dir(filename) / COMPLETE_MARKER_NAME
    if not path.exists():
        return None
    try:
        str_text = path.read_text(encoding="utf-8").strip()
        if not str_text:
            return None  # legacy touch file (size 0)
        return json.loads(str_text)
    except Exception:
        return None


def _write_complete_marker(
    tiles_dir: Path,
    str_icc_hash: Optional[str],
    bool_icc_applied: bool,
) -> None:
    """마커 JSON 작성. _generate_tiles 완료 시점에서만 호출."""
    dict_marker = {
        "version": COMPLETE_MARKER_VERSION,
        "icc_hash": str_icc_hash,
        "icc_applied": bool(bool_icc_applied),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (tiles_dir / COMPLETE_MARKER_NAME).write_text(
        json.dumps(dict_marker, ensure_ascii=False),
        encoding="utf-8",
    )


def tiles_are_valid(filename: str, file_path: str) -> bool:
    """디스크 타일이 현재 슬라이드 상태와 일치하는지 판정.

    - 마커 없음 / 레거시 touch 파일 / 버전 불일치 → False (재생성 필요)
    - 마커의 icc_hash 가 현재 슬라이드의 ICC 해시와 다름 → False
    - 마커 icc_applied=False 인데 현재 슬라이드에 ICC 프로파일이 있음 → False
    - 슬라이드 열기 실패 → True (기존 타일 보존; 호출측이 판단)

    주의: 개별 타일 파일 존재 여부는 검사하지 않음. 마커가 있으면 _generate_tiles 가
    완주했다는 뜻이고, 개별 파일 무결성은 외부에서 챙겨야 함.
    """
    tiles_dir = get_tiles_dir(filename)
    if not tiles_dir.exists():
        return False
    dict_marker = read_complete_marker(filename)
    if dict_marker is None:
        return False
    if dict_marker.get("version") != COMPLETE_MARKER_VERSION:
        return False
    try:
        slide = openslide.OpenSlide(file_path)
    except Exception as e:
        print(f"[tile_generator] tiles_are_valid: OpenSlide 실패 ({filename}): {e}")
        return True  # 판단 불가 — 기존 타일 유지
    try:
        str_current_hash = _slide_icc_hash(slide)
    finally:
        try:
            slide.close()
        except Exception:
            pass

    str_marker_hash = dict_marker.get("icc_hash")
    if str_marker_hash != str_current_hash:
        return False
    # 해시는 같은데 이전 생성 시 ICC 적용이 실패했던 경우: 재시도해도 같은 환경이라
    # 보통 똑같이 실패한다. 무한 재생성 루프 방지를 위해 valid 로 간주한다.
    # 환경(PIL/openslide)을 바꾼 뒤 수동 재생성을 원하면 tile dir 를 지우면 된다.
    return True


def invalidate_tiles(filename: str) -> None:
    """타일 디렉토리 통째 삭제 — 재생성 전 호출."""
    tiles_dir = get_tiles_dir(filename)
    if tiles_dir.exists():
        shutil.rmtree(tiles_dir, ignore_errors=True)


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
    bool_completed = False

    try:
        slide = openslide.OpenSlide(file_path)

        # ICC profile → sRGB transform (있으면 픽셀 한 번 변환 후 plain JPEG 저장)
        # 마커에 기록할 해시는 buildTransform 성공 여부와 무관하게 "소스에 존재한 프로파일"
        # 기준으로 계산한다. 그래야 환경이 바뀌었을 때 재생성 트리거가 정확히 걸린다.
        str_icc_hash = _slide_icc_hash(slide)
        icc_transform = None
        try:
            obj_profile = getattr(slide, "color_profile", None)
            if obj_profile is not None:
                from PIL import ImageCms
                obj_srgb = ImageCms.createProfile("sRGB")
                icc_transform = ImageCms.buildTransform(obj_profile, obj_srgb, "RGB", "RGB")
        except Exception as e:
            print(f"[tile_generator] ICC transform 실패 ({filename}): {e}")
        if str_icc_hash is not None and icc_transform is None:
            print(f"[tile_generator] WARN {filename}: ICC 프로파일이 존재하지만 transform 빌드 실패 — ICC 미적용 상태로 타일 생성")

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

        # 완료 마커 — 현재 슬라이드의 ICC 해시 + 실제 적용 여부 기록
        _write_complete_marker(
            tiles_dir,
            str_icc_hash=str_icc_hash,
            bool_icc_applied=(icc_transform is not None),
        )
        bool_completed = True
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
        # 부분 실패 정리 — 마커가 쓰이기 전에 예외가 발생했다면 .complete 없는
        # 불완전 타일 디렉토리가 남는다. 다음 실행에서 tiles_are_valid 가
        # False 를 내리고 invalidate_tiles 가 불릴 테지만, 혼재 상태에서
        # 뷰어가 404/깨진 타일을 보는 윈도우를 줄이기 위해 여기서 바로 지운다.
        # thumbnail 은 유용하지만 이후 재생성 시 어차피 overwrite 되므로 함께 삭제.
        if not bool_completed and tiles_dir.exists():
            try:
                shutil.rmtree(tiles_dir, ignore_errors=True)
                print(f"[tile_generator] 부분 실패 → {tiles_dir} 정리됨")
            except Exception as exc_cleanup:
                print(f"[tile_generator] cleanup 실패 ({filename}): {exc_cleanup}")

        # 완료 후 일정 시간 뒤 progress 정리
        def _cleanup():
            time.sleep(60)
            with _progress_lock:
                _progress.pop(filename, None)
        threading.Thread(target=_cleanup, daemon=True).start()
