"""Validate real JSON read timings, recording boundaries and storage retries."""
import asyncio
import copy
import json
import os
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.auth import get_current_user
from app import auth
from app.csrf import CSRFMiddleware
from app.config import settings
from app.postgres.base import Base
from app.postgres import database
from app.repositories.application_store import PostgresDocumentCollection
from app.routers import pd_l1_comparison as routes
from app.routers import projects
from app.project_utils import project_public_info
from app.slide_identity import slide_cache_key

HEADERS = {'X-Requested-With': 'XMLHttpRequest'}


class MemoryStore:
    def __init__(self): self.records = {}
    async def insert_one(self, record): self.records[record['_id']] = copy.deepcopy(record)
    async def find_one(self, query):
        return next((copy.deepcopy(v) for v in self.records.values() if all(v.get(k) == x for k, x in query.items())), None)
    async def update_one(self, query, update, upsert=False):
        key = next((k for k, v in self.records.items() if all(v.get(f) == x for f, x in query.items())), None)
        if key is None:
            if not upsert: return
            key = uuid.uuid4().hex
            self.records[key] = {**query, **update.get('$setOnInsert', {})}
        self.records[key].update(copy.deepcopy(update.get('$set', {})))
    def find(self, query):
        records = [copy.deepcopy(v) for v in self.records.values() if all(v.get(k) == x for k, x in query.items())]
        class Cursor:
            def sort(self, key, direction):
                records.sort(key=lambda record: record.get(key), reverse=direction < 0)
                return self
            def limit(self, *args): return self
            async def to_list(self, length): return records[:length]
        return Cursor()


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, 'is_auth_store_connected', lambda: True)
    uploads = tmp_path / 'uploads'; slides = uploads / 'project-one'; slides.mkdir(parents=True)
    file = slides / 'anonymous.svs'; file.touch()
    monkeypatch.setattr(settings, 'UPLOAD_DIR', str(uploads))
    monkeypatch.setattr(settings, 'COMPARISON_DIR', str(tmp_path / 'comparison'))
    monkeypatch.setattr(settings, 'AI_RESULTS_DIR', str(tmp_path / 'results'))
    monkeypatch.setattr(routes.slide_manager, 'get', lambda identifier: SimpleNamespace(file_path=str(file)) if identifier=='slide-one' else None)
    monkeypatch.setattr(routes, 'log_audit_event', AsyncMock(return_value='audit-record'))
    uri = os.environ.get('SECURITY_TEST_DATABASE_URI')
    engine = None; schema = 'comparison_test_' + uuid.uuid4().hex
    if uri:
        parsed = make_url(uri)
        assert parsed.host == '127.0.0.1' and parsed.database == 'knuch_security_test'
        engine = create_async_engine(uri, poolclass=NullPool, connect_args={'server_settings': {'search_path': schema}})
        monkeypatch.setattr(database, '_session_factory', async_sessionmaker(engine, expire_on_commit=False))
        async def setup():
            async with engine.begin() as conn:
                await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
                await conn.run_sync(Base.metadata.create_all)
        asyncio.run(setup())
        repository = PostgresDocumentCollection('pd_l1_comparisons')
    else:
        repository = MemoryStore()
    monkeypatch.setattr(routes, 'store', lambda: repository)
    metadata = PostgresDocumentCollection('project_infos') if engine else MemoryStore()
    monkeypatch.setattr(routes, 'get_db', lambda: SimpleNamespace(project_infos=metadata))
    monkeypatch.setattr(projects, 'get_db', lambda: SimpleNamespace(project_infos=metadata))
    monkeypatch.setattr(projects, 'is_db_connected', lambda: True)
    monkeypatch.setattr(projects, '_log_event', AsyncMock())
    path = tmp_path / 'results/Quanti PD-L1' / f'{slide_cache_key(str(file))}_Quanti PD-L1_Stomach.json'
    path.parent.mkdir(parents=True)
    from app.ai_pipelines.marker_pipeline import marker_model_runtime_metadata
    model_dir = tmp_path / 'models';model_dir.mkdir()
    monkeypatch.setattr(settings, 'MODEL_DIR', str(model_dir))
    for tissue in ('Stomach', 'Breast'):
        (model_dir / routes.PD_SCORE_CONFIG[tissue]['model_file']).write_bytes(b'fixture')
    path.write_text(json.dumps({'cells': [[1, 2, 2, .9]],
        'model_runtime': marker_model_runtime_metadata(routes.PD_SCORE_CONFIG['Stomach']),
        'pd_score': {'score_type': 'CPS', 'score': 43.2, 'class_schema':'pdl1_flat_5class'}}))
    app = FastAPI();app.add_middleware(CSRFMiddleware);app.include_router(routes.router, prefix='/comparison');app.include_router(projects.router, prefix='/projects')
    app.dependency_overrides[get_current_user] = lambda: {'_id': 'doctor-one', 'str_role': 'doctor'}
    with TestClient(app) as instance:
        instance.app_under_test = app;instance.json_path = path
        yield instance
    if engine:
        async def cleanup():
            async with engine.begin() as conn: await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await engine.dispose()
        asyncio.run(cleanup())


def measurement(**kwargs):
    return {'run_id': uuid.uuid4().hex, 'slide_id': 'slide-one', 'tissue_type': 'Stomach',
            'specialist_elapsed_ms': 120050, 'percentage': 45.5, 'grade': '2', **kwargs}


def read_json(client, **kwargs):
    return client.post('/comparison/read-json', headers=HEADERS, json={'slide_id': 'slide-one', **kwargs})


def test_read_save_reload_and_retry(client):
    result = read_json(client);assert result.status_code == 200, result.text
    ai = result.json();assert ai['ai_json_elapsed_ms'] > 0
    assert ai['ai_percentage'] == 43.2 and ai['ai_grade'] is None
    assert ai['result']['cells'] == [[1, 2, 2, .9]]
    body = measurement(ai_read_id=ai['ai_read_id'], ai_result_elapsed_ms=265.75)
    response = client.post('/comparison/records', headers=HEADERS, json=body)
    assert response.status_code == 200, response.text
    record = response.json()
    assert record['project_path'] == 'project-one'
    assert record['specialist_elapsed_ms'] == 120050 and record['ai_json_elapsed_ms'] == ai['ai_json_elapsed_ms']
    assert record['grade'] == 'CPS ≥ 10'
    assert record['grade_basis'] == 'score_bands_v1'
    assert record['ai_result_elapsed_ms'] == 265.75
    assert record['ai_timing_basis'] == 'request_to_display'
    assert 'result' not in record
    retry = client.post('/comparison/records', headers=HEADERS, json=body)
    assert retry.json()['_id'] == record['_id']
    listed = client.get('/comparison/records?slide_id=slide-one').json()['records']
    assert len(listed)==1 and listed[0]['_id']==record['_id']
    assert client.get('/comparison/records?slide_id=missing-slide').status_code==404
    assert client.post('/comparison/records', headers=HEADERS, json={**body,'grade':'3'}).status_code==409


def test_missing_json_can_record_specialist_without_zero_ai_time(client):
    client.json_path.unlink();assert read_json(client).status_code==404
    response = client.post('/comparison/records', headers=HEADERS, json=measurement())
    assert response.status_code==200
    assert response.json()['ai_json_elapsed_ms'] is None


@pytest.mark.parametrize('value', [0, -1, 86400001])
def test_invalid_elapsed_time_rejected(client, value):
    assert client.post('/comparison/records', headers=HEADERS,json=measurement(specialist_elapsed_ms=value)).status_code==422


@pytest.mark.parametrize('values', [{'percentage':-1},{'percentage':101},{'grade':''},{'grade':' '},{'grade':'bad\ngrade'}, {'ai_json_elapsed_ms':1}])
def test_invalid_or_forged_fields_rejected(client, values):
    assert client.post('/comparison/records',headers=HEADERS,json=measurement(**values)).status_code==422


def test_receipt_from_another_reader_cannot_be_attached(client):
    receipt=read_json(client).json()['ai_read_id']
    client.app_under_test.dependency_overrides[get_current_user]=lambda:{'_id':'doctor-two','str_role':'doctor'}
    assert client.post('/comparison/records',headers=HEADERS,json=measurement(ai_read_id=receipt)).status_code==400


@pytest.mark.parametrize('role',['viewer','labeler'])
def test_only_specialist_and_admin_can_save(client,role):
    client.app_under_test.dependency_overrides[get_current_user]=lambda:{'_id':'read-only','str_role':role}
    assert client.post('/comparison/records',headers=HEADERS,json=measurement()).status_code==403


def test_receipt_variant_and_unknown_slide_rejected(client):
    receipt=read_json(client).json()['ai_read_id']
    assert client.post('/comparison/records',headers=HEADERS,json=measurement(ai_read_id=receipt,tissue_type='Lung')).status_code==400
    assert client.post('/comparison/records',headers=HEADERS,json=measurement(slide_id='unknown')).status_code==404


@pytest.mark.parametrize('content',['{bad','{}','{"pd_score":{"score_type":"TPS","score":20}}','{"pd_score":{"score_type":"CPS","score":NaN}}'])
def test_bad_cache_is_not_a_valid_ai_measurement(client,content):
    client.json_path.write_text(content);assert read_json(client).status_code==422


def test_unauthenticated_reads_and_csrf_boundary(client):
    client.app_under_test.dependency_overrides.clear()
    assert client.get('/comparison/records?slide_id=slide-one').status_code==401
    client.app_under_test.dependency_overrides[get_current_user]=lambda:{'_id':'doctor-one','str_role':'doctor'}
    assert client.post('/comparison/records',json=measurement()).status_code==403


@pytest.mark.parametrize('duration', [0, -1, 86400001, 'NaN', 'Infinity'])
def test_invalid_display_duration_rejected(client, duration):
    response = client.post('/comparison/records', headers=HEADERS,
                           json=measurement(ai_result_elapsed_ms=duration))
    assert response.status_code == 422


def test_display_duration_requires_real_receipt(client):
    response = client.post('/comparison/records', headers=HEADERS,
                           json=measurement(ai_result_elapsed_ms=250))
    assert response.status_code == 400


def test_full_result_is_returned_but_not_duplicated_in_storage(client):
    result = read_json(client).json()
    assert result['result']['pd_score']['score'] == 43.2
    response = client.post('/comparison/records', headers=HEADERS,
                           json=measurement(ai_read_id=result['ai_read_id'], ai_result_elapsed_ms=300))
    assert response.status_code == 200
    record = response.json()
    assert record['ai_json_elapsed_ms'] == result['ai_json_elapsed_ms']
    assert record['ai_result_elapsed_ms'] == 300
    # The receipt retains summary metrics rather than all slide cells.
    assert asyncio.run(routes.store().find_one({'_id': result['ai_read_id']})).get('result') is None


@pytest.mark.parametrize('tissue,score,expected', [
    ('Stomach', 0, 'CPS < 1'), ('Stomach', .9999, 'CPS < 1'),
    ('Stomach', 1, '1 ≤ CPS < 10'), ('Stomach', 9.9999, '1 ≤ CPS < 10'),
    ('Stomach', 10, 'CPS ≥ 10'), ('Stomach', 100, 'CPS ≥ 10'),
    ('Lung', .9999, 'TPS < 1'), ('Lung', 1, '1 ≤ TPS < 50'),
    ('Lung', 49.9999, '1 ≤ TPS < 50'), ('Lung', 50, 'TPS ≥ 50'),
])
def test_grade_derived_from_percentage_not_manual_input(client, tissue, score, expected):
    response = client.post('/comparison/records', headers=HEADERS,
                           json=measurement(tissue_type=tissue, percentage=score, grade='arbitrary'))
    assert response.status_code == 200
    assert response.json()['grade'] == expected


def set_model(client, tissue, project='project-one'):
    return client.post('/projects/project/comparison-model', headers=HEADERS,
                       data={'name': project, 'tissue_type': tissue})


def test_project_model_save_reload_preserves_other_metadata(client):
    metadata = routes.get_db().project_infos
    asyncio.run(metadata.update_one({'str_project_path': 'project-one'}, {'$set': {
        'str_title': 'Keep this title', 'str_owner': 'Hospital owner',
        'list_project_ai_tasks': [{'model': 'Quanti HE', 'variant': 'Stomach'}],
    }}, upsert=True))
    response = set_model(client, 'Lung')
    assert response.status_code == 200, response.text
    info = response.json()['info']
    assert info['comparison_tissue_type'] == 'Lung'
    assert info['title'] == 'Keep this title' and info['owner'] == 'Hospital owner'
    assert info['project_ai_tasks'] == [{'model': 'Quanti HE', 'variant': 'Stomach'}]
    reloaded = project_public_info(asyncio.run(metadata.find_one({'str_project_path': 'project-one'})))
    assert reloaded == info
    assert projects._log_event.await_args.kwargs['str_action'] == 'project.comparison_model.update'


def test_fixed_project_model_cannot_be_bypassed_by_read_or_save(client):
    assert set_model(client, 'Lung').status_code == 200
    assert read_json(client).status_code == 409
    assert client.post('/comparison/records', headers=HEADERS, json=measurement()).status_code == 409
    # Matching expert assessments may still be recorded if AI JSON is absent.
    assert client.post('/comparison/records', headers=HEADERS,
                       json=measurement(tissue_type='Lung')).status_code == 200
    assert set_model(client, '').status_code == 200
    assert read_json(client).status_code == 200


@pytest.mark.parametrize('role', ['viewer', 'labeler'])
def test_read_only_roles_cannot_set_project_model(client, role):
    client.app_under_test.dependency_overrides[get_current_user] = lambda: {'_id':'reader', 'str_role': role}
    assert set_model(client, 'Stomach').status_code == 403


@pytest.mark.parametrize('name', ['../project-one', 'project-one/subfolder', '..'])
def test_model_setting_rejects_invalid_project_path(client, name):
    assert set_model(client, 'Lung', name).status_code == 400


def test_model_setting_rejects_unknown_model_missing_project_and_csrf(client):
    assert set_model(client, 'Quanti HE').status_code == 422
    assert set_model(client, 'Lung', 'absent-project').status_code == 404
    assert client.post('/projects/project/comparison-model', data={'name':'project-one','tissue_type':'Lung'}).status_code == 403


def test_model_setting_reports_unavailable_storage(client, monkeypatch):
    monkeypatch.setattr(projects, 'is_db_connected', lambda: False)
    assert set_model(client, 'Lung').status_code == 503


def test_breast_cps_project_model_read_and_record(client):
    stomach = json.loads(client.json_path.read_text())
    breast_path = client.json_path.with_name(client.json_path.name.replace('_Stomach.json', '_Breast.json'))
    from app.ai_pipelines.marker_pipeline import marker_model_runtime_metadata
    breast_path.write_text(json.dumps({**stomach, 'tissue_type': 'Breast',
        'model_runtime': marker_model_runtime_metadata(routes.PD_SCORE_CONFIG['Breast'])}))
    assert set_model(client, 'Breast').status_code == 200
    assert read_json(client).status_code == 409
    response = read_json(client, tissue_type='Breast')
    assert response.status_code == 200, response.text
    ai = response.json()
    assert ai['score_type'] == 'CPS' and ai['result']['tissue_type'] == 'Breast'
    saved = client.post('/comparison/records', headers=HEADERS,
                        json=measurement(tissue_type='Breast', ai_read_id=ai['ai_read_id'], ai_result_elapsed_ms=250))
    assert saved.status_code == 200, saved.text
    assert saved.json()['score_type'] == 'CPS'
    assert saved.json()['grade'] == 'CPS ≥ 10'
    assert saved.json()['tissue_type'] == 'Breast'


def test_slide_entry_timing_basis_is_preserved(client):
    ai = read_json(client).json()
    response = client.post('/comparison/records', headers=HEADERS, json=measurement(
        ai_read_id=ai['ai_read_id'], ai_result_elapsed_ms=3200,
        ai_timing_basis='slide_entry_to_display'))
    assert response.status_code == 200
    assert response.json()['ai_timing_basis'] == 'slide_entry_to_display'
    assert response.json()['ai_result_elapsed_ms'] == 3200


def test_slide_records_show_latest_assessment_for_all_accounts(client):
    repository = routes.store()
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    for identifier, user, slide, seconds in [
        ('a-old','a','slide-one',0), ('a-new','a','slide-one',1),
        ('b','b','slide-one',2), ('other-slide','a','slide-other',3),
        ('other-project','c','slide-one',4),
    ]:
        asyncio.run(repository.insert_one({'_id':identifier,'kind':'comparison',
            'project_path':'other-project' if identifier=='other-project' else 'project-one',
            'slide_id':slide,'user_id':user,'dt_created_at':now+timedelta(seconds=seconds)}))
    before = client.get('/comparison/records?slide_id=slide-one').json()['records']
    assert {record['_id'] for record in before} == {'a-new','b'}
    client.app_under_test.dependency_overrides[get_current_user] = lambda: {
        '_id':'c', 'str_role':'doctor', 'str_name':'Specialist C','str_username':'account-c'}
    saved = client.post('/comparison/records', headers=HEADERS, json=measurement())
    assert saved.status_code == 200
    after = client.get('/comparison/records?slide_id=slide-one').json()['records']
    assert len(after) == 3 and {record['user_id'] for record in after} == {'a','b','c'}
    record = next(record for record in after if record['user_id']=='c')
    assert record['user_name']=='Specialist C' and record['username']=='account-c'
    assert asyncio.run(repository.find_one({'_id':'a-old'})) is not None


def test_empty_slide_records_and_missing_slide_filter(client):
    assert client.get('/comparison/records?slide_id=slide-one').json()['records'] == []
    assert client.get('/comparison/records?project_path=project-one').status_code == 422


def test_json_export_written_and_retry_does_not_duplicate(client):
    response = client.post('/comparison/records', headers=HEADERS, json=measurement())
    assert response.status_code == 200
    from pathlib import Path
    files = list(Path(settings.COMPARISON_DIR).rglob('account_*.json'))
    assert len(files) == 1
    document = json.loads(files[0].read_text())
    assert document['slide']['relative_path'] == 'project-one/anonymous.svs'
    assert document['account']['user_id'] == 'doctor-one'
    assert document['latest']['specialist_elapsed_ms'] == 120050
    assert 'request_signature' not in document['latest']


def test_json_failure_keeps_db_record_and_same_measurement_retry_repairs_file(client, monkeypatch):
    from app.comparison_files import write_comparison_json
    from pathlib import Path
    body = measurement()
    def failure(*args): raise OSError('test disk unavailable')
    monkeypatch.setattr(routes, 'write_comparison_json', failure)
    response = client.post('/comparison/records', headers=HEADERS, json=body)
    assert response.status_code == 503
    assert len(client.get('/comparison/records?slide_id=slide-one').json()['records']) == 1
    monkeypatch.setattr(routes, 'write_comparison_json', write_comparison_json)
    assert client.post('/comparison/records', headers=HEADERS, json=body).status_code == 200
    assert client.post('/comparison/records', headers=HEADERS, json=body).status_code == 200
    files = list(Path(settings.COMPARISON_DIR).rglob('account_*.json'))
    assert len(files) == 1 and len(json.loads(files[0].read_text())['measurements']) == 1


def test_completion_status_is_account_and_project_specific(client):
    assert client.get('/comparison/completed?project_path=project-one').json()['slide_ids'] == []
    assert client.post('/comparison/records', headers=HEADERS, json=measurement()).status_code == 200
    status = client.get('/comparison/completed?project_path=project-one').json()
    assert status == {'user_id':'doctor-one','slide_ids':['slide-one']}
    assert client.get('/comparison/completed?project_path=other-project').json()['slide_ids'] == []
    client.app_under_test.dependency_overrides[get_current_user] = lambda: {'_id':'doctor-two','str_role':'doctor'}
    assert client.get('/comparison/completed?project_path=project-one').json()['slide_ids'] == []
    assert client.post('/comparison/records', headers=HEADERS, json=measurement()).status_code == 200
    assert client.get('/comparison/completed?project_path=project-one').json()['slide_ids'] == ['slide-one']
    assert client.post('/comparison/records', headers=HEADERS, json=measurement()).status_code == 200
    assert client.get('/comparison/completed?project_path=project-one').json()['slide_ids'] == ['slide-one']


def test_completed_list_does_not_require_opening_slides(client, monkeypatch):
    assert client.post('/comparison/records', headers=HEADERS, json=measurement()).status_code == 200
    monkeypatch.setattr(routes.slide_manager, 'get', lambda identifier: None)
    assert client.get('/comparison/completed?project_path=project-one').json()['slide_ids'] == ['slide-one']
    assert client.get('/comparison/completed?project_path=../project-one').status_code == 400


def test_comparison_rejects_old_model_cache_without_relabeling_it(client):
    original = {'cells':[[1,2,3,.9]],'pd_score':{'score_type':'CPS','score':43.2}}
    client.json_path.write_text(json.dumps(original))
    assert read_json(client).status_code == 409
    assert json.loads(client.json_path.read_text()) == original


def test_comparison_rejects_changed_weights_runtime(client):
    result = json.loads(client.json_path.read_text())
    result['model_runtime']['mtime_ns'] -= 1
    client.json_path.write_text(json.dumps(result))
    assert read_json(client).status_code == 409
