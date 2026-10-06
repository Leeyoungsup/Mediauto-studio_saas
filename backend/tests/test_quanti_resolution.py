"""Check physical fields and WSI coordinates through the actual Quanti pipelines."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import torch
from PIL import Image

from app.ai_pipelines.resolution import quanti_patch_size, preserve_previous_resolution_cache
from app.ai_pipelines.dedup import processing_metadata, cache_has_current_detection_postprocess


@pytest.mark.parametrize('mpp', [None, 0, -1, float('nan'), float('inf')])
def test_invalid_mpp_rejected(mpp):
    with pytest.raises(ValueError, match='MPP'):
        quanti_patch_size(mpp)


@pytest.mark.parametrize('mpp', [0.25, 0.5, 1.0, 0.243])
@pytest.mark.parametrize('kind', ['he', 'ihc'])
def test_physical_field_and_overlay_coordinates(tmp_path, monkeypatch, mpp, kind):
    from app.ai_pipelines import detection, marker_pipeline, patch_reader
    from ai.nets import nn
    from ai import yolo_postprocess
    from app import slide_store
    pipeline = detection if kind == 'he' else marker_pipeline
    filename = 'HnE_detection.pt' if kind == 'he' else 'marker.pt'
    (tmp_path / filename).write_bytes(b'test weights placeholder; model is mocked')
    monkeypatch.setattr(pipeline.settings, 'MODEL_DIR', str(tmp_path))
    model = MagicMock()
    model.to.return_value = model
    monkeypatch.setattr(nn, 'yolo_v11_m', lambda *args: model)
    monkeypatch.setattr(torch, 'load', lambda *args, **kwargs: {'model_state_dict': {}})
    monkeypatch.setattr(torch.cuda, 'is_available', lambda: False)
    # A detection away from patch edges; coordinates are in model input pixels.
    monkeypatch.setattr(yolo_postprocess, 'non_max_suppression',
                        lambda *args, **kwargs: [torch.tensor([[100., 120., 140., 160., .99, 1.]])])
    reads = []
    def read_region(origin, level, size):
        reads.append((origin, level, size))
        return Image.new('RGB', size, 'white')
    slide = SimpleNamespace(read_region=read_region)
    info = SimpleNamespace(slide=slide, file_path=str(tmp_path/'slide.ndpi'),
                           dimensions=(10000, 10000), mpp=mpp, icc_transform=None)
    monkeypatch.setattr(pipeline.slide_manager, 'get', lambda *args: info)
    monkeypatch.setattr(patch_reader, 'get_thread_slide', lambda *args: slide)
    monkeypatch.setattr(patch_reader, 'wait_if_viewer_busy', lambda: None)
    patch_sizes = []
    def patches(*args, **kwargs):
        patch_sizes.append(args[3])
        return [(123, 257)], 'test'
    monkeypatch.setattr(pipeline, 'build_valid_patch_list', patches)
    monkeypatch.setattr(pipeline, 'check_cancel', lambda *args: None)
    monkeypatch.setattr(pipeline, 'is_cancel_requested', lambda *args: False)
    monkeypatch.setattr(pipeline, 'slide_source_signature', lambda *args: {})
    monkeypatch.setattr(slide_store, 'mark_ai_result_threadsafe', lambda *args: None)
    updates = []
    monkeypatch.setattr(pipeline, 'update_task', lambda *args, **kw: updates.append(kw))
    path = tmp_path/'result.json'
    old_cache = json.dumps({'cells': [], 'patch_overlap_um': 10,
                           'global_dedup_version': 'quanti-overlap-10um-edge3um-spatial-nms-v9'})
    path.write_text(old_cache)
    monkeypatch.setattr(pipeline, 'source_signature_matches', lambda *args: True)
    if kind == 'he':
        monkeypatch.setattr(pipeline, 'get_ai_cache_path', lambda *args: path)
        pipeline.run_detection('task', 'slide', None, 'Other')
    else:
        config = dict(model_file=filename, num_classes=2, class_names={0:'Other',1:'Cell'},
                      class_colors={0:'#fff',1:'#000'}, score_type='test')
        pipeline.run_marker_detection_pipeline('task', 'slide', None, config, path,
                                               lambda cls: {}, 'test_score', {}, 'Quanti IHC/HER2')
    assert updates[-1].get('status') == 'completed', updates[-1]
    result = updates[-1]['result']
    assert result['total_cells'] == 1
    origin, level, size = reads[0]
    assert origin == (123, 257) and level == 0
    assert size == (patch_sizes[0], patch_sizes[0])
    # Whole-pixel rounding is at most half a source pixel over a 256 µm field.
    assert abs(size[0]*mpp - 256.) <= mpp/2 + 1e-9
    cell = result['cells'][0]
    scale = size[0]/512
    assert cell[:2] == pytest.approx([123+120*scale, 257+140*scale], abs=.0051)
    assert cell[4:8] == pytest.approx([123+100*scale,257+120*scale,123+140*scale,257+160*scale], abs=.0051)
    assert result['input_mpp'] == .5
    assert json.loads(path.read_text())['input_mpp'] == .5
    assert path.with_name(path.name+'.before-quanti-mpp05.bak').read_text() == old_cache


def test_old_cache_rejected_and_preserved(tmp_path):
    current = processing_metadata()
    assert cache_has_current_detection_postprocess(current)
    old = {**current, 'global_dedup_version': 'quanti-overlap-10um-edge3um-spatial-nms-v9'}
    assert not cache_has_current_detection_postprocess(old)
    path = tmp_path/'result.json'
    path.write_text(json.dumps(old))
    original = path.read_bytes()
    preserve_previous_resolution_cache(path)
    assert path.read_bytes() == original
    path.write_text('new result')
    preserve_previous_resolution_cache(path)
    assert path.with_name(path.name+'.before-quanti-mpp05.bak').read_bytes() == original


@pytest.mark.parametrize('tissue,filename', [('Breast','HnE_BR_segmentation.pt'), ('Stomach','HnE_ST_segmentation.pt')])
def test_he_segmentation_input_and_output_coordinates(tmp_path, monkeypatch, tissue, filename):
    import sys
    import numpy as np
    from app.ai_pipelines import detection, stil_scoring
    (tmp_path/filename).write_bytes(b'test placeholder')
    monkeypatch.setattr(detection.settings, 'MODEL_DIR', str(tmp_path))
    captured = []
    class Segmenter:
        def __init__(self, **kwargs):
            captured.append(kwargs)
            self.output_mpp = kwargs['output_mpp']
            self.class_names = {}
        def predict_wsi(self, *args, **kwargs):
            # Tissue segmentation has its own input MPP and output mask scale.
            return np.array([[2,3]], dtype=np.uint8), {'region_offset': (100,200)}
    monkeypatch.setitem(sys.modules, 'ai.epithelial_classifier', SimpleNamespace(WSISegmentationModel=Segmenter))
    monkeypatch.setattr(detection, 'update_task', lambda *args, **kw: None)
    monkeypatch.setattr(detection, 'build_seg_overlays', lambda *args, **kw: {})
    monkeypatch.setattr(stil_scoring, 'compute_stil_score', lambda *args, **kw: {})
    monkeypatch.setattr(torch.cuda, 'is_available', lambda: False)
    classes = np.array([1,1])
    result = detection.run_epithelial_classification(
        'task', None, 'slide.ndpi', SimpleNamespace(mpp=.5,icc_transform=None),
        np.array([102.,110.]), np.array([202.,202.]), classes, np.array([.99,.99]),
        tissue, None, 'cpu')
    assert result is not None
    assert captured[0]['model_mpp'] == 1.0
    assert captured[0]['output_mpp'] == 4.
    assert classes.tolist() == [7,6]
