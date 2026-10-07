import json
from pathlib import Path
import subprocess

import pytest
from app import assistance_cache_metadata as metadata


def payload():
    return {'annotation_ai': {'key': 'ihc', 'note': 'escaped "labels": [ text'},
            'source_ai_postprocess': {'global_dedup_version': 'v10'},
            'assistance_confidence_threshold': .5,
            'labels': [[1, 2, 3, 'other']] * 15000}


def test_large_current_layout_reads_bounded_bytes(tmp_path, monkeypatch):
    path = tmp_path / 'cache.json'
    data = payload()
    path.write_text(json.dumps(data), encoding='utf-8')
    sizes = []
    original = Path.open

    class Reader:
        def __init__(self, file): self.file = file
        def __enter__(self): return self
        def __exit__(self, *args): self.file.close()
        def seek(self, *args): return self.file.seek(*args)
        def read(self, size=-1):
            assert size >= 0
            sizes.append(size)
            return self.file.read(size)

    monkeypatch.setattr(Path, 'open', lambda *a, **kw: Reader(original(*a, **kw)))
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('Unexpected legacy parse'))
    result = metadata.read_assistance_metadata(path)
    assert result == metadata._summary(data)
    assert sum(sizes) <= metadata.WINDOW + 128


def test_legacy_metadata_after_labels_uses_isolated_process(tmp_path):
    data = payload()
    reordered = {'labels': data.pop('labels'), **data}
    path = tmp_path / 'legacy.json'
    path.write_text(json.dumps(reordered))
    assert metadata.read_assistance_metadata(path) == metadata._summary(reordered)


@pytest.mark.parametrize('value', [[], None, 'not-an-array'])
def test_small_labels_type_is_preserved(tmp_path, value):
    path = tmp_path / 'small.json'
    data = payload()
    data['labels'] = value
    path.write_text(json.dumps(data))
    result = metadata.read_assistance_metadata(path)
    assert isinstance(result['labels'], list) == isinstance(value, list)


def test_truncated_large_cache_is_not_accepted(tmp_path):
    path = tmp_path / 'broken.json'
    path.write_text(json.dumps(payload())[:-20])
    with pytest.raises(ValueError):
        metadata.read_assistance_metadata(path)


def test_large_header_compatibility(tmp_path):
    data = payload()
    data['annotation_ai']['note'] = 'x' * (metadata.WINDOW + 1)
    path = tmp_path / 'header.json'
    path.write_text(json.dumps(data))
    assert metadata.read_assistance_metadata(path) == metadata._summary(data)
