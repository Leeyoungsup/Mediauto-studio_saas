from types import SimpleNamespace

import numpy as np
import pytest

from app.ai_pipelines import tissue_mask as tm
from app.ai_pipelines.dedup import processing_metadata, cache_has_current_detection_postprocess


def test_envelopes_are_filtered_by_tissue_and_roi(monkeypatch):
    slide = SimpleNamespace(dimensions=(400, 200),
                            data_envelope_rectangles=[(0, 199, 0, 199)])
    mask = np.zeros((2, 4), dtype=np.uint8)
    mask[0, 0] = 255  # tissue inside envelope
    mask[1, 1] = 255  # tissue inside envelope, outside selected ROI
    mask[0, 3] = 255  # tissue outside envelope
    calls = []
    def make_mask(slide, icc_transform=None):
        calls.append(icc_transform)
        return mask
    monkeypatch.setattr(tm, 'create_tissue_mask', make_mask)
    coords, source = tm.build_valid_patch_list(slide, 400, 200, 100, mpp=.5,
        roi_polygons=[[(0, 0), (200, 0), (200, 100), (0, 100)]], icc_transform='icc')
    assert coords == [(0, 0)]
    assert source == 'data_envelope+tissue_mask'
    assert calls == ['icc']


@pytest.mark.parametrize('envelopes', [[], [(0, 100, 0, 64)]])
def test_actual_mask_scale_keeps_partial_pixel_at_slide_edge(monkeypatch, envelopes):
    slide = SimpleNamespace(dimensions=(101, 65), data_envelope_rectangles=envelopes)
    mask = np.zeros((3, 7), dtype=np.uint8)
    mask[-1, -1] = 255
    monkeypatch.setattr(tm, 'create_tissue_mask', lambda *a, **k: mask)
    coords, _ = tm.build_valid_patch_list(slide, 101, 65, 32, mpp=.5)
    assert (69, 33) in coords
    assert (0, 0) not in coords


def test_blank_envelope_has_no_patches(monkeypatch):
    slide = SimpleNamespace(dimensions=(128, 128), data_envelope_rectangles=[(0, 127, 0, 127)])
    monkeypatch.setattr(tm, 'create_tissue_mask', lambda *a, **k: np.zeros((2, 2), dtype=np.uint8))
    assert tm.build_valid_patch_list(slide, 128, 128, 64)[0] == []


def test_failed_mask_retains_candidates_and_logs(monkeypatch, caplog):
    slide = SimpleNamespace(dimensions=(128, 128), data_envelope_rectangles=[(0, 63, 0, 63)])
    def fail(*a, **k):
        raise RuntimeError('thumbnail unavailable')
    monkeypatch.setattr(tm, 'render_pyramid_thumbnail', fail)
    coords, _ = tm.build_valid_patch_list(slide, 128, 128, 64)
    assert coords == [(0, 0)]
    assert 'Tissue mask failed' in caplog.text


def test_old_selection_cache_remains_readable_without_reinference():
    current = processing_metadata()
    assert cache_has_current_detection_postprocess(current)
    del current['patch_selection_version']
    assert cache_has_current_detection_postprocess(current)
