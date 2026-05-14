"""Backward-compatible Quanti HE exports.

New code should import from ``ai.quanti_he`` or ``ai.yolo_postprocess``.
This module remains so older imports such as ``from ai.detection import ...``
continue to work.
"""

from ai.quanti_he import CLASS_COLORS, CLASS_NAMES
from ai.yolo_postprocess import non_max_suppression, wh2xy

__all__ = ["CLASS_NAMES", "CLASS_COLORS", "non_max_suppression", "wh2xy"]
