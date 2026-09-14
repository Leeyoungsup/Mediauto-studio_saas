"""Exercise activity logs through HTTP while keeping all writes in test storage."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import activity_audit, auth
from app.config import settings
from app.routers import annotation_storage, slides, cell_annotation, users, ai_user_edits


@pytest.fixture
def audit_client(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'UPLOAD_DIR', str(tmp_path))
    monkeypatch.setattr(settings, 'ANNOTATIONS_DIR', str(tmp_path / 'annotations'))
    monkeypatch.setattr(settings, 'AI_RESULTS_DIR', str(tmp_path / 'results'))
    audit = AsyncMock()
    monkeypatch.setattr(activity_audit, 'log_audit_event', audit)
    monkeypatch.setattr(slides, 'log_audit_event', audit)
    app = FastAPI()
    for router in (slides.router, annotation_storage.router):
        app.include_router(router, prefix='/api/slides')
    app.include_router(cell_annotation.router, prefix='/api/cell-annotation')
    app.include_router(users.router, prefix='/api/users')
    app.include_router(ai_user_edits.router, prefix='/api/ai')
    app.dependency_overrides[auth.get_current_user] = lambda: {
        '_id': 'test-user', 'str_login_id': 'test-doctor', 'str_role': 'admin',
    }
    with TestClient(app, headers={'User-Agent': 'audit-test'}) as client:
        yield client, audit, tmp_path


def test_tissue_save_and_conflict_log_revisions_without_annotation_body(audit_client, monkeypatch):
    client, audit, root = audit_client
    monkeypatch.setattr(annotation_storage.slide_manager, 'get',
                        lambda _: SimpleNamespace(file_path=str(root / 'slide.svs')))
    url = '/api/slides/test/annotations'
    revision = client.get(url + '/load').headers['etag']
    first = client.post(url + '/save', headers={'If-Match': revision},
                        data={'data': '[{"memo":"private note","coordinates":[[1,2]]}]'})
    assert first.status_code == 200
    event = audit.call_args.kwargs
    assert event['str_action'] == 'annotation.save'
    assert event['str_user_id'] == 'test-user'
    assert event['str_user_agent'] == 'audit-test'
    assert event['str_resource_id'] == 'test'
    assert event['dict_before'] == {'revision': revision}
    assert event['dict_after']['revision'] == first.json()['revision']
    assert event['dict_after']['count'] == 1
    assert 'private note' not in json.dumps(event)
    assert 'coordinates' not in json.dumps(event)
    conflict = client.post(url + '/save', headers={'If-Match': revision}, data={'data': '[]'})
    assert conflict.status_code == 409
    event = audit.call_args.kwargs
    assert event['str_action'] == 'annotation.save.failed'
    assert event['dict_extra']['dict_context']['http_status'] == 409
    assert event['dict_after'] is None


def test_upload_start_complete_and_chunk_failures_correlate(audit_client, monkeypatch):
    client, audit, root = audit_client
    (root / 'project').mkdir()
    monkeypatch.setattr(slides, '_open_and_generate', AsyncMock(return_value={'slide_id': 'test-slide'}))
    started = client.post('/api/slides/upload/start', data={'filename': 'slide.svs'})
    assert started.status_code == 200
    upload_id = started.json()['upload_id']
    assert audit.call_args.kwargs['str_resource_id'] == upload_id
    assert audit.call_args.kwargs['str_action'] == 'slide.upload_started'
    chunk = client.post('/api/slides/upload/chunk', data={'upload_id': upload_id, 'chunk_index': 0},
                        files={'chunk': ('chunk', b'synthetic-slide')})
    assert chunk.status_code == 200
    assert audit.await_count == 1  # No log per successful chunk.
    completed = client.post('/api/slides/upload/complete', data={
        'upload_id': upload_id, 'filename': 'slide.svs', 'total_chunks': 1, 'path': 'project'})
    assert completed.status_code == 200
    assert audit.await_count == 2  # Existing completion event is not duplicated.
    event = audit.call_args.kwargs
    assert event['str_action'] == 'slide.upload'
    assert event['dict_extra']['str_upload_id'] == upload_id
    assert event['dict_extra']['int_size_bytes'] == len(b'synthetic-slide')
    failed = client.post('/api/slides/upload/chunk', data={'upload_id': upload_id, 'chunk_index': 1},
                         files={'chunk': ('chunk', b'data')})
    assert failed.status_code == 404
    assert audit.call_args.kwargs['str_action'] == 'slide.upload_chunk.failed'
    assert audit.call_args.kwargs['dict_extra']['dict_context']['upload_id'] == upload_id


@pytest.mark.parametrize('endpoint,data,action', [
    ('start', {'filename': 'unsupported.exe'}, 'slide.upload_started.failed'),
    ('complete', {'upload_id': 'missing', 'filename': 'slide.svs', 'total_chunks': 1}, 'slide.upload.failed'),
])
def test_upload_rejections_are_not_successes(audit_client, endpoint, data, action):
    client, audit, _ = audit_client
    assert client.post('/api/slides/upload/' + endpoint, data=data).status_code in (400, 404)
    assert audit.await_count == 1
    assert audit.call_args.kwargs['str_action'] == action
    assert audit.call_args.kwargs['dict_after'] is None


def test_audit_store_failure_preserves_save_and_reports_server_error(audit_client, caplog):
    client, audit, root = audit_client
    audit.side_effect = RuntimeError('audit unavailable')
    response = client.post('/api/slides/upload/start', data={'filename': 'test.svs'})
    assert response.status_code == 200
    assert (root / ('_chunks_' + response.json()['upload_id'])).is_dir()
    assert 'Activity audit write failed (slide.upload_started)' in caplog.text


def test_cell_save_and_status_change_log_summary(audit_client, monkeypatch):
    client, audit, _ = audit_client
    patch = {'str_patch_id': 'p', 'str_patch_key': 'p', 'int_x': 0, 'int_y': 0,
             'str_status': 'required', 'str_review_status': 'pending', 'str_termination_status': 'pending'}
    db = SimpleNamespace(
        patch_annotation_status=SimpleNamespace(find_one=AsyncMock(return_value=patch), update_one=AsyncMock()),
        patch_cell_annotations=SimpleNamespace(update_one=AsyncMock()))
    monkeypatch.setattr(cell_annotation, '_require_db', lambda: db)
    monkeypatch.setattr(cell_annotation, '_slide_info', lambda _: SimpleNamespace(mpp=0.5, dimensions=(2048, 2048)))
    monkeypatch.setattr(cell_annotation, '_schedule_cell_annotation_export', lambda _: None)
    saved = client.post('/api/cell-annotation/s/patches/p/cells', json={'cells': [{'x': 10, 'y': 20}]})
    assert saved.status_code == 200
    event = audit.call_args.kwargs
    assert event['str_action'] == 'cell_annotation.cells_save'
    assert event['dict_after']['cell_count'] == 1
    assert event['dict_extra']['dict_context']['patch_id'] == 'p'
    assert 'list_cells' not in json.dumps(event)
    changed = client.put('/api/cell-annotation/s/patches/p/status', json={'status': 'reviewed'})
    assert changed.status_code == 200
    event = audit.call_args.kwargs
    assert event['str_action'] == 'cell_annotation.status_update'
    assert event['dict_before']['str_status'] == 'required'
    assert event['dict_after']['str_review_status'] == 'reviewed'


@pytest.mark.parametrize('category', ['annotation', 'upload'])
def test_admin_activity_categories_include_new_events(audit_client, monkeypatch, category):
    client, _, _ = audit_client
    audit_store = SimpleNamespace(list=AsyncMock(return_value=[]), count=AsyncMock(return_value=7))
    monkeypatch.setattr(users, 'get_audit_store', lambda: audit_store)
    monkeypatch.setattr(users, 'get_user_store', lambda: SimpleNamespace(
        find_by_id=AsyncMock(return_value={'_id': 'test-user'})))
    response = client.get('/api/users/test-user/activity', params={'str_category': category})
    assert response.status_code == 200
    assert response.json()['dict_counts'][category] == 7
    assert response.json()['dict_counts']['all'] == 7
    filters = audit_store.list.call_args.kwargs
    if category == 'annotation':
        assert 'annotation.save' in filters['list_actions']
        assert 'cell_annotation.status_update.failed' in filters['list_actions']
    else:
        assert filters['str_action_prefix'] == 'slide.upload'


def test_ai_user_edit_save_and_delete_are_logged(audit_client, monkeypatch):
    from app import slide_store
    client, audit, root = audit_client
    monkeypatch.setattr(ai_user_edits.slide_manager, 'get', lambda _: SimpleNamespace(file_path=str(root / 'slide.svs')))
    monkeypatch.setattr(slide_store, 'upsert_user_ai_edit', AsyncMock())
    monkeypatch.setattr(slide_store, 'delete_user_ai_edit', AsyncMock(return_value={'str_file_path': ''}))
    response = client.post('/api/ai/save-result', data={
        'slide_id': 's', 'result': '{"cells":[{"x":1,"y":2}]}', 'ai_mode': 'Quanti HE'})
    assert response.status_code == 200
    assert audit.call_args.kwargs['str_action'] == 'ai.annotation_save'
    assert audit.call_args.kwargs['dict_after']['total_cells'] == 1
    response = client.delete('/api/ai/user-edits', params={'slide_id': 's', 'ai_mode': 'Quanti HE'})
    assert response.status_code == 200
    assert audit.call_args.kwargs['str_action'] == 'ai.annotation_delete'
