from types import SimpleNamespace

import pytest

from app.ai_pipelines.dedup import (
    GLOBAL_DEDUP_VERSION, cache_has_current_detection_postprocess,
)


def legacy_metadata():
    return {'input_mpp': .5, 'patch_overlap_um': 10.0,
            'global_dedup_version': GLOBAL_DEDUP_VERSION}


def test_reader_and_selection_changes_do_not_hide_saved_results():
    metadata = legacy_metadata()
    assert cache_has_current_detection_postprocess(metadata)
    # Preserve provenance rather than relabel the old result as newly inferred.
    assert 'patch_reader_version' not in metadata
    assert 'patch_selection_version' not in metadata
    assert cache_has_current_detection_postprocess({**metadata,
        'patch_reader_version': 'older-reader', 'patch_selection_version': 'older-selection'})
    assert not cache_has_current_detection_postprocess({**metadata,'global_dedup_version':'unknown'})


def test_saved_assistance_is_returned_without_backup_or_reinference(tmp_path, monkeypatch):
    from app.routers import cell_annotation as ca
    payload = {'source_ai_postprocess': legacy_metadata(),
               'annotation_ai': {'enabled': False},
               'labels': [[0, 0, 10, 10, 5, 5, '0', .9]], 'total_labels': 1}
    monkeypatch.setattr(ca, '_existing_assistance_path', lambda info:tmp_path/'untouched.json')
    monkeypatch.setattr(ca, '_expected_assistance_confidence_threshold', lambda config:None)
    monkeypatch.setattr(ca, 'preserve_previous_resolution_cache',
                        lambda path:pytest.fail('saved assistance must not be invalidated'))
    result, changed = ca._validate_assistance_payload(SimpleNamespace(), payload)
    assert result is payload
    assert result['total_labels'] == 1
    assert not changed
    assert list(tmp_path.iterdir()) == []
