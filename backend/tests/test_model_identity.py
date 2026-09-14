from app.ai_pipelines.model_identity import model_identity
import json

from app.config import settings
from app import auto_ai
from app.ai_pipelines.cache_paths import get_vs_cache_paths
from app.ai_pipelines.virtual_stain import VS_MODEL_FILES


def test_replaced_weights_invalidate_identity_even_when_same_size(tmp_path):
    path = tmp_path / "model.pth"
    path.write_bytes(b"weights-a")
    before = model_identity(path)
    assert model_identity(path) == before
    replacement = tmp_path / "replacement.pth"
    replacement.write_bytes(b"weights-b")
    replacement.replace(path)
    assert model_identity(path) != before


def test_auto_worker_rejects_missing_or_outdated_model_provenance(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "AI_RESULTS_DIR", str(tmp_path / "results"))
    monkeypatch.setattr(settings, "MODEL_DIR", str(tmp_path))
    path = tmp_path / VS_MODEL_FILES["ihc_membrane"]
    path.write_bytes(b"original")
    slide = str(tmp_path / "slide.svs")
    png, metadata = get_vs_cache_paths(slide, 2.0)
    png.write_bytes(b"synthetic-presence-marker")
    metadata.write_text(json.dumps({"stain_type": "ihc_membrane"}))
    assert not auto_ai._vs_cache_exists(slide, 2.0)
    metadata.write_text(json.dumps({"stain_type": "ihc_membrane", "model_identity": model_identity(path)}))
    assert auto_ai._vs_cache_exists(slide, 2.0)
    replacement = tmp_path / "new.pth"
    replacement.write_bytes(b"replaced")
    replacement.replace(path)
    assert not auto_ai._vs_cache_exists(slide, 2.0)
    metadata.write_text("[]")
    assert not auto_ai._vs_cache_exists(slide, 2.0)
