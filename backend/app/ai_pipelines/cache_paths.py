"""AI result cache path helpers with legacy-name migration."""

from pathlib import Path
from typing import Tuple

from app.config import settings


def _ensure_dir(path_dir: Path) -> None:
    try:
        path_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def _move_first_existing(list_src: list[Path], path_dst: Path, str_label: str) -> None:
    if path_dst.exists():
        return
    for path_src in list_src:
        if not path_src.exists() or path_src.resolve() == path_dst.resolve():
            continue
        try:
            path_src.replace(path_dst)
            return
        except Exception as e:
            print(f"[ai] {str_label} legacy migration failed ({path_src.name}): {e}")


def get_ai_cache_path(slide_path: str, tissue_type: str) -> Path:
    """Quanti HE cache path."""
    p = Path(slide_path)
    cache_dir = Path(settings.AI_RESULTS_DIR) / "Quanti HE"
    _ensure_dir(cache_dir)
    new_path = cache_dir / f"{p.stem}_Quanti HE_{tissue_type}.json"
    _move_first_existing([
        Path(settings.AI_RESULTS_DIR) / "HE-Fit" / f"{p.stem}_HE-Fit_{tissue_type}.json",
        Path(settings.AI_RESULTS_DIR) / f"{p.stem}_HE-Fit_{tissue_type}.json",
        Path(settings.AI_RESULTS_DIR) / f"{p.stem}_Quanti HE_{tissue_type}.json",
    ], new_path, "Quanti HE")
    return new_path


def get_pd_score_cache_path(slide_path: str, tissue_type: str) -> Path:
    """Quanti PD-L1 cache path."""
    p = Path(slide_path)
    cache_dir = Path(settings.AI_RESULTS_DIR) / "Quanti PD-L1"
    _ensure_dir(cache_dir)
    new_path = cache_dir / f"{p.stem}_Quanti PD-L1_{tissue_type}.json"
    _move_first_existing([
        Path(settings.AI_RESULTS_DIR) / "PD-Score" / f"{p.stem}_PD-Score_{tissue_type}.json",
        Path(settings.AI_RESULTS_DIR) / f"{p.stem}_PD-Score_{tissue_type}.json",
    ], new_path, "Quanti PD-L1")
    return new_path


def get_precise_ihc_cache_path(slide_path: str, marker: str) -> Path:
    """Quanti IHC cache path."""
    p = Path(slide_path)
    cache_dir = Path(settings.AI_RESULTS_DIR) / "Quanti IHC"
    _ensure_dir(cache_dir)
    new_path = cache_dir / f"{p.stem}_Quanti IHC_{marker}.json"
    _move_first_existing([
        Path(settings.AI_RESULTS_DIR) / "Precise-IHC" / f"{p.stem}_Precise-IHC_{marker}.json",
        Path(settings.AI_RESULTS_DIR) / f"{p.stem}_Precise-IHC_{marker}.json",
    ], new_path, "Quanti IHC")
    return new_path


def get_vs_cache_paths(slide_path: str, target_mpp: float = 2.0) -> Tuple[Path, Path]:
    """VS IHC cache paths for the result PNG and metadata JSON."""
    p = Path(slide_path)
    cache_dir = Path(settings.AI_RESULTS_DIR) / "VS IHC"
    _ensure_dir(cache_dir)
    mpp_str = f"{target_mpp:g}".replace(".", "p")
    base_name = f"{p.stem}_VS IHC_mpp{mpp_str}"
    new_png = (cache_dir / base_name).with_suffix(".png")
    new_meta = (cache_dir / base_name).with_suffix(".json")
    new_tile = cache_dir / f"{base_name}_tile"

    legacy_bases = (
        base_name,
        f"{p.stem}_VS-IHC_mpp{mpp_str}",
        f"{p.stem}_VS-IHC_ihc_membrane_mpp{mpp_str}",
    )
    legacy_dirs = (
        Path(settings.AI_RESULTS_DIR),
        Path(settings.AI_RESULTS_DIR) / "VS-IHC",
        cache_dir,
    )
    for legacy_base in legacy_bases:
        for legacy_parent in legacy_dirs:
            legacy_png = (legacy_parent / legacy_base).with_suffix(".png")
            legacy_meta = (legacy_parent / legacy_base).with_suffix(".json")
            legacy_tile = legacy_parent / f"{legacy_base}_tile"
            _move_first_existing([legacy_png], new_png, "VS IHC")
            _move_first_existing([legacy_meta], new_meta, "VS IHC")
            if legacy_tile.exists() and not new_tile.exists():
                try:
                    legacy_tile.replace(new_tile)
                except Exception as e:
                    print(f"[ai] VS IHC legacy tile dir migration failed: {e}")

    return new_png, new_meta


def get_vs_tile_dir(slide_path: str, target_mpp: float = 2.0) -> Path:
    """VS IHC tile pyramid directory."""
    png_path, _ = get_vs_cache_paths(slide_path, target_mpp)
    return png_path.parent / f"{png_path.stem}_tile"
