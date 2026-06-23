"""AI result cache path helpers keyed by slide_cache_key."""

from pathlib import Path
from typing import Tuple

from app.config import settings
from app.slide_identity import slide_cache_key


def _ensure_dir(path_dir: Path) -> None:
    try:
        path_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def get_ai_cache_path(slide_path: str, tissue_type: str) -> Path:
    """Quanti HE cache path."""
    key = slide_cache_key(slide_path)
    cache_dir = Path(settings.AI_RESULTS_DIR) / "Quanti HE"
    _ensure_dir(cache_dir)
    return cache_dir / f"{key}_Quanti HE_{tissue_type}.json"


def get_pd_score_cache_path(slide_path: str, tissue_type: str) -> Path:
    """Quanti PD-L1 cache path."""
    key = slide_cache_key(slide_path)
    cache_dir = Path(settings.AI_RESULTS_DIR) / "Quanti PD-L1"
    _ensure_dir(cache_dir)
    return cache_dir / f"{key}_Quanti PD-L1_{tissue_type}.json"


def get_precise_ihc_cache_path(slide_path: str, marker: str) -> Path:
    """Quanti IHC cache path."""
    key = slide_cache_key(slide_path)
    cache_dir = Path(settings.AI_RESULTS_DIR) / "Quanti IHC"
    _ensure_dir(cache_dir)
    return cache_dir / f"{key}_Quanti IHC_{marker}.json"


def get_vs_cache_paths(slide_path: str, target_mpp: float = 2.0) -> Tuple[Path, Path]:
    """VS IHC cache paths for the result PNG and metadata JSON."""
    key = slide_cache_key(slide_path)
    cache_dir = Path(settings.AI_RESULTS_DIR) / "VS IHC"
    _ensure_dir(cache_dir)
    mpp_str = f"{target_mpp:g}".replace(".", "p")
    base_name = f"{key}_VS IHC_mpp{mpp_str}"
    new_png = cache_dir / f"{base_name}.png"
    new_meta = cache_dir / f"{base_name}.json"

    return new_png, new_meta


def get_vs_tile_dir(slide_path: str, target_mpp: float = 2.0) -> Path:
    """VS IHC tile pyramid directory."""
    png_path, _ = get_vs_cache_paths(slide_path, target_mpp)
    return png_path.parent / f"{png_path.stem}_tile"
