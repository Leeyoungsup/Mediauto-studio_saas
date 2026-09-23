import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app import auto_ai, database, slide_store
from app.config import settings
from app.project_utils import normalize_annotation_ai_config
from app.slide_identity import slide_cache_key


def test_explicit_folder_scoring_does_not_hide_project_assistance(tmp_path, monkeypatch):
    slide = tmp_path / 'slide.ndpi'
    slide.touch()
    doc = {'str_rel_path': 'IHC(HER2)', 'str_full_path': str(slide), 'str_filename': slide.name, 'bool_tiles_ready': True}
    project = {'str_project_path': 'IHC(HER2)', 'bool_annotation_ai_enabled': True,
               'str_annotation_ai_key': 'ihc_membrane_breast'}

    class Collection:
        def __init__(self, items): self.items = items
        async def find(self, *args):
            for item in self.items: yield item

    db = SimpleNamespace(
        folder_ai_configs=Collection([{'str_rel_path':'IHC(HER2)', 'bool_enabled':True,
                                      'list_tasks':[{'model':'Quanti IHC','variant':'HER2'}]}]),
        project_infos=Collection([project]), slides=Collection([doc]))
    monkeypatch.setattr(database, 'is_db_connected', lambda: True)
    monkeypatch.setattr(database, 'get_db', lambda: db)
    monkeypatch.setattr(slide_store, 'repair_folder_ai_config_paths', AsyncMock(return_value=0))
    monkeypatch.setattr(slide_store, 'list_slides_in_folder', AsyncMock(return_value={slide.name:doc}))
    monkeypatch.setattr(slide_store, 'list_slides_missing_variant', AsyncMock(return_value=[]))
    monkeypatch.setattr(auto_ai, 'is_system_idle', lambda: True)
    monkeypatch.setattr(auto_ai, 'SCAN_STALE_CACHES', False)
    monkeypatch.setattr(auto_ai, '_expected_marker_model_runtime', lambda *args: None)
    monkeypatch.setattr(auto_ai, '_should_yield_for_active_tile_generation', AsyncMock(return_value=False))
    monkeypatch.setattr(auto_ai, '_should_defer_slide_for_pending_tiles', AsyncMock(return_value=False))
    monkeypatch.setattr(auto_ai, '_assistance_needs_refresh', lambda *args: True)
    run = AsyncMock()
    monkeypatch.setattr(auto_ai, '_run_auto_inference', run)
    asyncio.run(auto_ai._scan_and_infer_once())
    assert run.await_count == 1
    assert run.call_args.args[2] == 'IHC_MEMBRANE_BREAST'
    assert run.call_args.kwargs['dict_annotation_ai']['key'] == 'ihc_membrane_breast'


def test_assistance_artifact_not_inferred_from_scoring_cache(tmp_path, monkeypatch):
    from app.routers import cell_annotation
    monkeypatch.setattr(settings, 'CELL_ANNOTATION_DIR', str(tmp_path))
    monkeypatch.setattr(auto_ai, '_marker_cache_needs_refresh', lambda *args: False)
    monkeypatch.setattr(cell_annotation, '_expected_assistance_confidence_threshold', lambda *args: None)
    config = normalize_annotation_ai_config(True, 'ihc_membrane')
    slide = str(tmp_path / 'slide.ndpi')
    assert auto_ai._assistance_needs_refresh(slide, config)
    path = tmp_path / slide_cache_key(slide) / 'WSI_Labeling_assistance.json'
    path.parent.mkdir()
    payload = {'annotation_ai': config, 'labels': [], 'source_ai_postprocess': auto_ai.processing_metadata()}
    path.write_text(json.dumps(payload))
    assert not auto_ai._assistance_needs_refresh(slide, config)
    payload['annotation_ai'] = {'key': 'different-model'}
    path.write_text(json.dumps(payload))
    before = path.read_bytes()
    assert auto_ai._assistance_needs_refresh(slide, config)
    assert path.read_bytes() == before
    path.write_text('broken json')
    assert auto_ai._assistance_needs_refresh(slide, config)
    assert path.read_text() == 'broken json'


def test_auto_dispatch_calls_assistance_saver(tmp_path, monkeypatch):
    from app.routers import ai, cell_annotation
    from app.slide_manager import slide_manager
    slide = str(tmp_path / 'slide.ndpi')
    config = normalize_annotation_ai_config(True, 'ihc_membrane')
    monkeypatch.setattr(slide_manager, 'get', lambda *args: SimpleNamespace(file_path=slide))
    monkeypatch.setattr(auto_ai, 'check_idle_and_reserve', lambda *args: True)
    calls = []
    monkeypatch.setattr(cell_annotation, '_run_labeling_assistance_task', lambda *args: calls.append(args))
    asyncio.run(auto_ai._run_auto_inference(slide, 'Quanti IHC', 'HER2', dict_annotation_ai=config))
    assert len(calls) == 1
    assert calls[0][2:] == (slide, config)


def test_disabled_annotation_project_has_no_tasks():
    assert auto_ai._annotation_project_configs({'bool_annotation_ai_enabled':False}, {'folder'}) == []
