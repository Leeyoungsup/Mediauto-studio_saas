from types import SimpleNamespace
import pytest
from app.ai_pipelines.marker_pipeline import _capture_marker_source, _validate_marker_source_unchanged


def test_snapshot_survives_viewer_handle_closure(tmp_path):
    path = tmp_path / 'slide.ndpi'
    path.write_bytes(b'original')
    class Handle:
        closed = False
        @property
        def dimensions(self):
            if self.closed: raise RuntimeError('closed')
            return (100, 200)
        @property
        def level_dimensions(self):
            if self.closed: raise RuntimeError('closed')
            return [(100, 200)]
        @property
        def properties(self):
            if self.closed: raise RuntimeError('closed')
            return {'openslide.vendor': 'hamamatsu'}
    handle = Handle()
    info = SimpleNamespace(slide=handle, file_path=str(path))
    snapshot = _capture_marker_source(info)
    handle.closed = True
    _validate_marker_source_unchanged(snapshot, str(path))
    assert snapshot['dimensions'] == [100, 200]
    assert snapshot['vendor'] == 'hamamatsu'
    with pytest.raises(ValueError, match='Cannot read'):
        _capture_marker_source(info)
    path.write_bytes(b'replaced slide')
    with pytest.raises(ValueError, match='changed during analysis'):
        _validate_marker_source_unchanged(snapshot, str(path))
