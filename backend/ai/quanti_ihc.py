"""Quanti IHC model facade."""

from app.ai_pipelines.scoring import (
    PRECISE_IHC_CONFIG,
    compute_allred_score,
    compute_her2_score,
    compute_ki67_score,
)
from ai.yolo_postprocess import non_max_suppression, wh2xy

MODEL_NAME = "Quanti IHC"
LEGACY_MODEL_NAME = "Precise-IHC"

__all__ = [
    "MODEL_NAME",
    "LEGACY_MODEL_NAME",
    "PRECISE_IHC_CONFIG",
    "compute_allred_score",
    "compute_her2_score",
    "compute_ki67_score",
    "non_max_suppression",
    "wh2xy",
]
