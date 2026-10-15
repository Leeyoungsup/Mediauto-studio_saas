"""Breast CPS uses its own weights/cache with the existing CPS cell semantics."""
import numpy as np
import pytest
from app.ai_pipelines.scoring import PD_SCORE_CONFIG, compute_pd_score
from app.ai_pipelines.cache_paths import get_pd_score_cache_path
from app.config import settings
from app.project_utils import normalize_annotation_ai_config, cell_annotation_classes_for_ai


@pytest.mark.parametrize('classes,expected', [([0,0,0,2,3,3,4],75), ([2,3,3],100), ([1,3,4],0), ([],0)])
def test_breast_score_matches_stomach(classes, expected):
    cells = np.array(classes, dtype=int)
    breast = compute_pd_score(cells, 'Breast')
    assert breast == compute_pd_score(cells, 'Stomach')
    assert breast['score_type'] == 'CPS' and breast['score'] == expected


def test_breast_cache_and_annotation_use_correct_model(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'AI_RESULTS_DIR', str(tmp_path))
    path = str(tmp_path/'anonymous.svs')
    assert get_pd_score_cache_path(path, 'Breast') != get_pd_score_cache_path(path, 'Stomach')
    assert get_pd_score_cache_path(path, 'Breast').name.endswith('_Quanti PD-L1_Breast.json')
    assert normalize_annotation_ai_config(True, 'quanti_pd_l1_breast')['variant'] == 'Breast'
    assert cell_annotation_classes_for_ai(True, 'quanti_pd_l1_breast') == cell_annotation_classes_for_ai(True, 'quanti_pd_l1_stomach')
    breast = PD_SCORE_CONFIG['Breast']
    assert breast['model_file'] == 'PDL1_BR_CPS_detection.pt'
    assert breast['num_classes'] == 5 and breast['exclude_classes'] == [4]
    assert breast['class_names'] is not PD_SCORE_CONFIG['Stomach']['class_names']
