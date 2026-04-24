"""
타일 프리제네레이터 — 3단계 stage 피라미드를 level 0 에서 읽어 생성.

구조:
  tiles/{slide_id}/
    ├── 0/{tx}_{ty}.jpeg    ← stage 0 (downsample 1, 원본 해상도)
    ├── 1/{tx}_{ty}.jpeg    ← stage 1 (downsample 4, level0→4096px 읽어 1024 리사이즈)
    ├── 2/{tx}_{ty}.jpeg    ← stage 2 (downsample 8, level0→8192px 읽어 1024 리사이즈)
    ├── thumbnail.jpeg
    └── .complete           ← 생성 완료 마커 (JSON: 버전/ICC 해시/적용 여부)

생성 최적화:
  stage 2 타일 영역(8192x8192 at level 0) 한 번 읽으면 동일 버퍼에서
    - stage 2 tile 1개 (전체 8192→1024 리사이즈)
    - stage 1 tile 4개 (4개 4096 크롭 → 각각 1024 리사이즈)
    - stage 0 tile 64개 (8x8 그리드, 1024 크롭)
  총 69개 타일을 한 번의 read_region 으로 생성. I/O 최소화.
"""

import hashlib
import json
import math
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import openslide
from PIL import Image

from app.config import settings
from app.slide_manager import (
    STAGE_READ_SIZE,
    STAGE_COUNT,
    TILE_SIZE_OUT,
    build_color_corrector,
)

_thumb_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="thumb")

TILE_SIZE = TILE_SIZE_OUT

# .complete marker schema version. Bump when the on-disk tile format changes
# in a way that requires regeneration.
# v2: 3단계 stage 피라미드 (level 0 리샘플링) — 이전 level-index 기반 타일 무효화
# v3: Hamamatsu NDP.view2 호환 gamma=1.8 + Target.White.Intensity LUT 도입 —
#     이전 raw-pass-through 타일은 색감이 달라 자동 재생성 필요.
COMPLETE_MARKER_VERSION = 3
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

        # 통합 색 보정 callable (ICC → NDP LUT → raw 우선순위).
        # 마커에 기록할 ICC 해시는 "소스에 존재한 프로파일" 기준 — transform 빌드
        # 실패와 무관하게 환경 변경 감지가 되도록.
        str_icc_hash = _slide_icc_hash(slide)
        _to_srgb, dict_color_meta = build_color_corrector(slide)
        bool_icc_applied = bool(dict_color_meta.get("icc_applied"))
        bool_ndp_applied = bool(dict_color_meta.get("ndp_applied"))
        if str_icc_hash is not None and not bool_icc_applied:
            print(f"[tile_generator] WARN {filename}: ICC 프로파일 존재하지만 transform 빌드 실패 — ICC 미적용")
        if bool_ndp_applied:
            print(
                f"[tile_generator] {filename}: NDP LUT 적용 — "
                f"white={dict_color_meta['ndp_white']:.1f}, gamma=1.8"
            )

        # 3단계 stage 피라미드 — 모두 level 0 에서 읽어 downsample [1, 4, 8] 로 생성
        int_w0, int_h0 = slide.dimensions

        # 각 stage 의 타일 그리드 (nx, ny) 계산
        list_stage_nx = []
        list_stage_ny = []
        int_total_tiles = 0
        for int_stage in range(STAGE_COUNT):
            int_scene_tile = STAGE_READ_SIZE[int_stage]
            int_nx = max(1, math.ceil(int_w0 / int_scene_tile))
            int_ny = max(1, math.ceil(int_h0 / int_scene_tile))
            list_stage_nx.append(int_nx)
            list_stage_ny.append(int_ny)
            int_total_tiles += int_nx * int_ny

        progress.total_tiles = int_total_tiles
        progress.status = "generating"

        # 썸네일 먼저 생성
        thumb_path = tiles_dir / "thumbnail.jpeg"
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        if not thumb_path.exists():
            thumb = slide.get_thumbnail((300, 300))
            _to_srgb(thumb.convert("RGB")).save(str(thumb_path), "JPEG", quality=85)

        # stage 디렉토리 준비
        for int_stage in range(STAGE_COUNT):
            (tiles_dir / str(int_stage)).mkdir(parents=True, exist_ok=True)
        stage0_dir = tiles_dir / "0"
        stage1_dir = tiles_dir / "1"
        stage2_dir = tiles_dir / "2"

        int_read_size2 = STAGE_READ_SIZE[2]   # 8192
        int_read_size1 = STAGE_READ_SIZE[1]   # 4096
        int_tile_out = TILE_SIZE_OUT          # 1024
        int_nx2 = list_stage_nx[2]
        int_ny2 = list_stage_ny[2]
        int_nx1 = list_stage_nx[1]
        int_ny1 = list_stage_ny[1]
        int_nx0 = list_stage_nx[0]
        int_ny0 = list_stage_ny[0]

        # stage 2 그리드 순회 — 각 스텝마다 level 0 에서 8192x8192 한 번 읽어
        # stage 2/1/0 타일을 모두 파생 저장한다 (69 tile / 1 read).
        for ty2 in range(int_ny2):
            for tx2 in range(int_nx2):
                progress.current_level = 2
                int_sx = tx2 * int_read_size2
                int_sy = ty2 * int_read_size2

                obj_region = slide.read_region(
                    (int_sx, int_sy), 0, (int_read_size2, int_read_size2)
                )
                obj_rgb = _to_srgb(obj_region.convert("RGB"))

                # ── stage 2 tile (8192 → 1024) ──
                tile_path2 = stage2_dir / f"{tx2}_{ty2}.jpeg"
                if not tile_path2.exists():
                    obj_tile2 = obj_rgb.resize(
                        (int_tile_out, int_tile_out), Image.LANCZOS
                    )
                    obj_tile2.save(
                        str(tile_path2), "JPEG", quality=settings.TILE_QUALITY
                    )
                progress.generated_tiles += 1

                # ── stage 1 sub-tiles (2x2, 각 4096 → 1024) ──
                progress.current_level = 1
                for sub_ty in range(2):
                    for sub_tx in range(2):
                        tx1 = tx2 * 2 + sub_tx
                        ty1 = ty2 * 2 + sub_ty
                        if tx1 >= int_nx1 or ty1 >= int_ny1:
                            continue
                        tile_path1 = stage1_dir / f"{tx1}_{ty1}.jpeg"
                        if not tile_path1.exists():
                            int_bx = sub_tx * int_read_size1
                            int_by = sub_ty * int_read_size1
                            obj_sub = obj_rgb.crop(
                                (int_bx, int_by,
                                 int_bx + int_read_size1,
                                 int_by + int_read_size1)
                            )
                            obj_tile1 = obj_sub.resize(
                                (int_tile_out, int_tile_out), Image.LANCZOS
                            )
                            obj_tile1.save(
                                str(tile_path1), "JPEG", quality=settings.TILE_QUALITY
                            )
                        progress.generated_tiles += 1

                # ── stage 0 sub-tiles (8x8, 각 1024 그대로) ──
                progress.current_level = 0
                for sub_ty in range(8):
                    for sub_tx in range(8):
                        tx0 = tx2 * 8 + sub_tx
                        ty0 = ty2 * 8 + sub_ty
                        if tx0 >= int_nx0 or ty0 >= int_ny0:
                            continue
                        tile_path0 = stage0_dir / f"{tx0}_{ty0}.jpeg"
                        if not tile_path0.exists():
                            int_bx = sub_tx * int_tile_out
                            int_by = sub_ty * int_tile_out
                            obj_tile0 = obj_rgb.crop(
                                (int_bx, int_by,
                                 int_bx + int_tile_out,
                                 int_by + int_tile_out)
                            )
                            obj_tile0.save(
                                str(tile_path0), "JPEG", quality=settings.TILE_QUALITY
                            )
                        progress.generated_tiles += 1

                # 큰 버퍼 즉시 해제 — 다음 스텝 전 메모리 확보
                obj_region.close()
                del obj_region, obj_rgb

        # 완료 마커 — 현재 슬라이드의 ICC 해시 + 실제 적용 여부 기록
        _write_complete_marker(
            tiles_dir,
            str_icc_hash=str_icc_hash,
            bool_icc_applied=bool_icc_applied,
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
