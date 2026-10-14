import numpy as np
import pytest
from app.ai_pipelines.scoring import PD_SCORE_CONFIG, compute_pd_score


def test_flat5_cps():
    score = compute_pd_score(np.repeat(np.arange(5), [80, 700, 20, 10, 900]), 'Stomach')
    assert score['score'] == 30
    assert score['positive_tumor'] == 20
    assert score['positive_immune'] == 10
    assert score['viable_tumor'] == 100
    assert score['class_schema'] == 'pdl1_flat_5class'
    assert PD_SCORE_CONFIG['Stomach']['exclude_classes'] == [4]


@pytest.mark.parametrize('classes,expected', [([], 0), ([1, 3, 4], 0), ([2, 3, 3], 100)])
def test_flat5_zero_and_cap(classes, expected):
    assert compute_pd_score(np.array(classes), 'Stomach')['score'] == expected


def test_lung_unchanged():
    score = compute_pd_score(np.repeat(np.arange(3), [80, 20, 900]), 'Lung')
    assert score['score'] == 20
    assert score['total_tumor'] == 100


def test_flat5_runtime(tmp_path, monkeypatch):
    from app.ai_pipelines.marker_pipeline import marker_model_runtime_metadata
    from app.config import settings
    from app.auto_ai import _expected_marker_model_runtime
    monkeypatch.setattr(settings, 'MODEL_DIR', str(tmp_path))
    (tmp_path / PD_SCORE_CONFIG['Stomach']['model_file']).write_bytes(b'fixture')
    runtime = marker_model_runtime_metadata(PD_SCORE_CONFIG['Stomach'])
    assert runtime['num_classes'] == 5
    assert runtime['class_schema'] == 'pdl1_flat_5class'
    assert _expected_marker_model_runtime('Quanti PD-L1', 'Stomach') == runtime
    assert _expected_marker_model_runtime('Quanti PD-L1', 'Lung') is None


def test_legacy_assistance_is_not_reused_after_flat5(tmp_path, monkeypatch):
    import json
    from app import auto_ai
    from app.config import settings
    from app.project_utils import normalize_annotation_ai_config
    from app.slide_identity import slide_cache_key
    from app.routers import cell_annotation
    monkeypatch.setattr(settings, 'CELL_ANNOTATION_DIR', str(tmp_path))
    monkeypatch.setattr(auto_ai, '_marker_cache_needs_refresh', lambda *args: False)
    monkeypatch.setattr(cell_annotation, '_expected_assistance_confidence_threshold', lambda *args: None)
    runtime = {'class_schema': 'pdl1_flat_5class', 'mtime_ns': 1}
    monkeypatch.setattr(auto_ai, '_expected_marker_model_runtime', lambda *args: dict(runtime))
    config = normalize_annotation_ai_config(True, 'quanti_pd_l1_stomach')
    slide = str(tmp_path / 'slide.ndpi')
    path = tmp_path / slide_cache_key(slide) / 'WSI_Labeling_assistance.json'
    path.parent.mkdir()
    payload = {'annotation_ai': config, 'labels': [], 'source_ai_postprocess': auto_ai.processing_metadata()}
    path.write_text(json.dumps(payload))
    assert auto_ai._assistance_needs_refresh(slide, config)
    payload['source_model_runtime'] = dict(runtime)
    path.write_text(json.dumps(payload))
    assert not auto_ai._assistance_needs_refresh(slide, config)
    runtime['mtime_ns'] = 2
    assert auto_ai._assistance_needs_refresh(slide, config)
    assert json.loads(path.read_text()) == payload
