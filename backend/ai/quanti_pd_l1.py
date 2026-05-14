"""Quanti PD-L1 model facade."""

from app.ai_pipelines.scoring import PD_SCORE_CONFIG, compute_pd_score
from ai.yolo_postprocess import non_max_suppression, wh2xy

MODEL_NAME = "Quanti PD-L1"
LEGACY_MODEL_NAME = "PD-Score"

__all__ = [
    "MODEL_NAME",
    "LEGACY_MODEL_NAME",
    "PD_SCORE_CONFIG",
    "compute_pd_score",
    "non_max_suppression",
    "wh2xy",
]
