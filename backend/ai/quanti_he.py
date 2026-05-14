"""Quanti HE model metadata and shared post-processing exports."""

from ai.yolo_postprocess import non_max_suppression, wh2xy

MODEL_NAME = "Quanti HE"
LEGACY_MODEL_NAME = "HE-Fit"

# 0~5: original H&E detection model classes.
# 6~7: epithelial post-classification classes.
CLASS_NAMES = {
    0: "Neutrophil",
    1: "Epithelial",
    2: "Lymphocyte",
    3: "Plasma",
    4: "Eosinophil",
    5: "Stromal cell",
    6: "Tumor Epithelial",
    7: "Benign Epithelial",
}

CLASS_COLORS = {
    0: "#FF4500",
    1: "#00FF00",
    2: "#0000FF",
    3: "#FFFF00",
    4: "#8A2BE2",
    5: "#808080",
    6: "#FF0000",
    7: "#00FF00",
}


__all__ = [
    "MODEL_NAME",
    "LEGACY_MODEL_NAME",
    "CLASS_NAMES",
    "CLASS_COLORS",
    "non_max_suppression",
    "wh2xy",
]
