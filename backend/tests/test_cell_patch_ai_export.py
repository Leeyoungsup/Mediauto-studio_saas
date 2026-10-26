import asyncio
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from app.routers import cell_annotation as ca


def setup_export(tmp_path, monkeypatch, exists=True):
    project = tmp_path / 'project'
    project.mkdir()
    slide = project / 'slide.ndpi'
    slide.touch()
    info = SimpleNamespace(file_path=str(slide))
    cache = tmp_path / 'cache'
    (cache / 'patches').mkdir(parents=True)
    (cache / 'patches' / 'patch_1.jpeg').write_bytes(b'cached-jpeg')
    patch = {'str_patch_id': 'patch_1', 'str_status': 'required',
             'str_termination_status': 'pending', 'int_x': 100, 'int_y': 200,
             'int_w': 50, 'int_h': 50}
    queries = []
    class Collection:
        def find(self, query, projection):
            queries.append(query)
            return self
        def sort(self, order): return self
        async def to_list(self, length):
            return [] if queries[-1].get('str_termination_status') else [patch]
    saved = AsyncMock(return_value={'list_cells': [{'id': 'manual'}]})
    db = SimpleNamespace(patch_annotation_status=Collection(),
                         patch_cell_annotations=SimpleNamespace(find_one=saved))
    monkeypatch.setattr(ca, '_require_db', lambda: db)
    monkeypatch.setattr(ca, 'safe_subpath', lambda _: project)
    monkeypatch.setattr(ca, '_slide_info', lambda _: info)
    monkeypatch.setattr(ca, '_cell_annotation_slide_dir', lambda _: cache)
    monkeypatch.setattr(ca, '_read_indexed_assistance', lambda *args:
                        ({'total_labels': 1, 'classes': [{'id': '0', 'name': 'Tumor'}]},
                         [(7, [105, 205, 10, 10, 110, 210, '0', .9])]) if exists else ({}, []))
    monkeypatch.setattr(ca, '_assistance_class_lookup', lambda *args: {'0': {'id': '0', 'name': 'Tumor'}})
    return queries


def test_selected_ai_exports_pending_patches_with_local_labels(tmp_path, monkeypatch):
    queries = setup_export(tmp_path, monkeypatch)
    response = asyncio.run(ca.download_termination_completed_cell_patches(
        'project', {'str_login_id': 'other_admin', 'str_role': 'admin'}, 'selected_ai'))
    try:
        with zipfile.ZipFile(response.path) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            assert manifest['total_patches'] == 1
            assert manifest['label_source'] == 'ai_assistance'
            name = next(n for n in archive.namelist() if n.endswith('/patch_1.json'))
            payload = json.loads(archive.read(name))
            assert payload['reviewed'] is False
            assert payload['termination_status'] == 'pending'
            assert payload['cells'][0]['id'] == 'assist_7'
            assert payload['cells'][0]['local_coordinates'][0] == [5, 5]
            assert payload['cells'][0]['confidence'] == .9
            assert payload['patch']['int_x'] == 100
            assert archive.read(name.replace('.json', '.jpeg')) == b'cached-jpeg'
        assert 'str_termination_status' not in queries[0]
    finally:
        Path(response.path).unlink()


def test_missing_ai_fails_without_empty_success_zip(tmp_path, monkeypatch):
    setup_export(tmp_path, monkeypatch, exists=False)
    with pytest.raises(HTTPException) as error:
        asyncio.run(ca.download_termination_completed_cell_patches(
            'project', {'str_login_id': 'other_admin', 'str_role': 'admin'}, 'selected_ai'))
    assert error.value.status_code == 409


def test_completed_export_keeps_completed_filter(tmp_path, monkeypatch):
    queries = setup_export(tmp_path, monkeypatch)
    response = asyncio.run(ca.download_termination_completed_cell_patches(
        'project', {'str_login_id': 'admin'}))
    try:
        assert queries[0]['str_termination_status'] == 'completed'
    finally:
        Path(response.path).unlink()


@pytest.mark.parametrize('mode', ['completed', 'selected_ai'])
@pytest.mark.parametrize('user', [
    {'str_login_id': 'youngseoplee', 'str_name': 'YoungSeopLee'},
    {'str_login_id': 'other', 'str_name': 'admin'},
    {'str_name': 'admin'},
])
def test_ai_export_retains_account_restriction(mode, user):
    with pytest.raises(HTTPException) as error:
        asyncio.run(ca.download_termination_completed_cell_patches(
            'project', user, mode))
    assert error.value.status_code == 403


@pytest.mark.parametrize('role', ['doctor', 'labeler', 'viewer', None])
def test_ai_export_rejects_non_admin_even_with_admin_login(role):
    with pytest.raises(HTTPException) as error:
        asyncio.run(ca.download_termination_completed_cell_patches(
            'project', {'str_login_id': 'admin', 'str_role': role}, 'selected_ai'))
    assert error.value.status_code == 403


def test_completed_export_keeps_login_restriction_for_other_admins():
    with pytest.raises(HTTPException) as error:
        asyncio.run(ca.download_termination_completed_cell_patches(
            'project', {'str_login_id': 'other_admin', 'str_role': 'admin'}, 'completed'))
    assert error.value.status_code == 403
