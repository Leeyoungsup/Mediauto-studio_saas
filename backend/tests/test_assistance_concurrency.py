import asyncio
import json
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.routers import cell_annotation as ca
from app.cpu_layout import viewer_executor


def test_assistance_filter_and_encoding_leave_event_loop_and_viewer_free(monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    main_thread = threading.get_ident()
    monkeypatch.setattr(ca, '_slide_info', lambda _: SimpleNamespace(file_path='slide.ndpi'))
    monkeypatch.setattr(ca, '_require_db', lambda: SimpleNamespace(patch_annotation_status=SimpleNamespace(
        find_one=AsyncMock(return_value={'str_status':'required'}))))
    monkeypatch.setattr(ca, '_read_assistance_file', lambda _: {'labels':[1,2], 'classes':[{'id':'tumor'}]})
    monkeypatch.setattr(ca, '_assistance_class_lookup', lambda *args: {})
    def convert(label, patch, idx, classes):
        assert threading.get_ident() != main_thread
        entered.set()
        assert release.wait(3)
        return {'id':str(idx)} if label == 1 else None
    monkeypatch.setattr(ca, '_assistance_label_to_cell', convert)
    original = ca.JSONResponse
    def response(*args, **kwargs):
        assert threading.get_ident() != main_thread
        return original(*args, **kwargs)
    monkeypatch.setattr(ca, 'JSONResponse', response)
    async def run():
        job = asyncio.create_task(ca.get_patch_labeling_assistance_cells(
            SimpleNamespace(is_disconnected=AsyncMock(return_value=False)), 'slide', 'patch'))
        try:
            for _ in range(100):
                if entered.is_set(): break
                await asyncio.sleep(.01)
            assert entered.is_set()
            assert await asyncio.wait_for(asyncio.get_running_loop().run_in_executor(viewer_executor, lambda: 'tile'), 1) == 'tile'
        finally:
            release.set()
        result = await job
        data = json.loads(result.body)
        assert data['total_labels'] == 2
        assert data['cells'] == [{'id':'1'}]
        assert data['cell_count'] == 1
    asyncio.run(run())


def test_assistance_metadata_encoding_in_worker(monkeypatch):
    main_thread = threading.get_ident()
    monkeypatch.setattr(ca, '_slide_info', lambda _: object())
    def read(_):
        assert threading.get_ident() != main_thread
        return {'labels': [1,2], 'classes': []}
    monkeypatch.setattr(ca, '_read_assistance_file', read)
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
    result = asyncio.run(ca.get_wsi_labeling_assistance(request, 'slide', False))
    assert json.loads(result.body) == {'classes': [], 'total_labels':2, 'total_model_bbox_labels':0, 'exists':True}
