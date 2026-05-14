"""VS IHC model facade.

The heavy virtual-stain implementation remains in ``ai.virtual_stain`` for
backward compatibility with the original desktop module name.
"""

from ai.virtual_stain import Generator, VirtualStainWorker, _make_blend_weight, _read_patch

MODEL_NAME = "VS IHC"
LEGACY_MODEL_NAME = "VS-IHC"

__all__ = [
    "MODEL_NAME",
    "LEGACY_MODEL_NAME",
    "Generator",
    "VirtualStainWorker",
    "_make_blend_weight",
    "_read_patch",
]
