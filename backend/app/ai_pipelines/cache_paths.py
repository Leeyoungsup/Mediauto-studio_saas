"""AI 결과 캐시 경로 helpers — 모델별 디렉터리 + 레거시 마이그레이션.

routers/ai.py 에 흩어져 있던 경로 계산 함수를 한 곳에 모은다.
모든 함수는 디스크에 폴더를 (없으면) 만들고 레거시 경로의 결과물을 신규
위치로 자동 이동시킨다. 경로 계산은 순수 함수지만 `cache_dir.mkdir` /
`legacy.replace(new)` 부수효과가 있어 호출 자체에 의미가 있다.
"""

from pathlib import Path
from typing import Tuple

from app.config import settings


def get_ai_cache_path(slide_path: str, tissue_type: str) -> Path:
    """HE-Fit 결과 캐시: ai_results/HE-Fit/{slide_stem}_HE-Fit_{tissue_type}.json

    레거시 경로 (ai_results/{slide_stem}_HE-Fit_{tissue_type}.json) 가 있으면
    새 위치로 자동 이동한다.
    """
    p = Path(slide_path)
    cache_dir = Path(settings.AI_RESULTS_DIR) / "HE-Fit"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    new_path = cache_dir / f"{p.stem}_HE-Fit_{tissue_type}.json"
    legacy_path = Path(settings.AI_RESULTS_DIR) / f"{p.stem}_HE-Fit_{tissue_type}.json"
    if not new_path.exists() and legacy_path.exists():
        try:
            legacy_path.replace(new_path)
        except Exception as e:
            print(f"[ai] HE-Fit legacy migration failed: {e}")
    return new_path


def get_pd_score_cache_path(slide_path: str, tissue_type: str) -> Path:
    """PD-Score 결과 캐시: ai_results/PD-Score/{slide_stem}_PD-Score_{tissue_type}.json"""
    p = Path(slide_path)
    cache_dir = Path(settings.AI_RESULTS_DIR) / "PD-Score"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return cache_dir / f"{p.stem}_PD-Score_{tissue_type}.json"


def get_precise_ihc_cache_path(slide_path: str, marker: str) -> Path:
    """Precise-IHC 결과 캐시: ai_results/Precise-IHC/{slide_stem}_Precise-IHC_{marker}.json"""
    p = Path(slide_path)
    cache_dir = Path(settings.AI_RESULTS_DIR) / "Precise-IHC"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return cache_dir / f"{p.stem}_Precise-IHC_{marker}.json"


def get_vs_cache_paths(slide_path: str, target_mpp: float = 2.0) -> Tuple[Path, Path]:
    """Virtual stain 결과 캐시: ai_results/VS-IHC/{slide_stem}_VS-IHC_mpp{p}.{png|json}

    타일 피라미드는 sibling 폴더: ..._tile/{level}/{tx}_{ty}.jpeg

    마이그레이션 2단계:
      1) 레거시 `ai_results/` 루트 → `ai_results/VS-IHC/`
      2) stain_type (`_ihc_membrane`) 제거 — VS-IHC 가 단일 모델로 통합됨
    """
    p = Path(slide_path)
    cache_dir = Path(settings.AI_RESULTS_DIR) / "VS-IHC"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    mpp_str = f"{target_mpp:g}".replace(".", "p")
    base_name = f"{p.stem}_VS-IHC_mpp{mpp_str}"
    new_png = (cache_dir / base_name).with_suffix(".png")
    new_meta = (cache_dir / base_name).with_suffix(".json")
    new_tile = cache_dir / f"{base_name}_tile"

    # ── 1) stain_type suffix 마이그레이션 (membrane 파일 → 새 이름) ──
    old_stain_base = f"{p.stem}_VS-IHC_ihc_membrane_mpp{mpp_str}"
    old_stain_png = (cache_dir / old_stain_base).with_suffix(".png")
    old_stain_meta = (cache_dir / old_stain_base).with_suffix(".json")
    old_stain_tile = cache_dir / f"{old_stain_base}_tile"
    for src, dst in ((old_stain_png, new_png), (old_stain_meta, new_meta)):
        if src.exists() and not dst.exists():
            try:
                src.replace(dst)
            except Exception as e:
                print(f"[ai] VS stain-suffix migration failed ({src.name}): {e}")
    if old_stain_tile.exists() and not new_tile.exists():
        try:
            old_stain_tile.replace(new_tile)
        except Exception as e:
            print(f"[ai] VS stain-suffix tile dir migration failed: {e}")

    # ── 2) ai_results 루트 레거시 (새/구 이름 둘 다 체크) ──
    legacy_dir = Path(settings.AI_RESULTS_DIR)
    for legacy_base in (base_name, old_stain_base):
        legacy_png = (legacy_dir / legacy_base).with_suffix(".png")
        legacy_meta = (legacy_dir / legacy_base).with_suffix(".json")
        legacy_tile = legacy_dir / f"{legacy_base}_tile"
        for src, dst in ((legacy_png, new_png), (legacy_meta, new_meta)):
            if src.exists() and not dst.exists():
                try:
                    src.replace(dst)
                except Exception as e:
                    print(f"[ai] VS legacy migration failed ({src.name}): {e}")
        if legacy_tile.exists() and not new_tile.exists():
            try:
                legacy_tile.replace(new_tile)
            except Exception as e:
                print(f"[ai] VS legacy tile dir migration failed: {e}")
    return new_png, new_meta


def get_vs_tile_dir(slide_path: str, target_mpp: float = 2.0) -> Path:
    """VS 타일 피라미드 폴더: {png_parent}/{png_stem}_tile/"""
    png_path, _ = get_vs_cache_paths(slide_path, target_mpp)
    return png_path.parent / f"{png_path.stem}_tile"
