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
from app.slide_identity import slide_cache_key

HEADERS = {'X-Requested-With': 'XMLHttpRequest'}


class MemoryStore:
    def __init__(self): self.records = {}
    async def insert_one(self, record): self.records[record['_id']] = copy.deepcopy(record)
    async def find_one(self, query):
        return next((copy.deepcopy(v) for v in self.records.values() if all(v.get(k) == x for k, x in query.items())), None)
    def find(self, query):
        records = [copy.deepcopy(v) for v in self.records.values() if all(v.get(k) == x for k, x in query.items())]
        class Cursor:
            def sort(self, *args): return self
            def limit(self, *args): return self
            async def to_list(self, length): return records[:length]
        return Cursor()


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, 'is_auth_store_connected', lambda: True)
    uploads = tmp_path / 'uploads'; slides = uploads / 'project-one'; slides.mkdir(parents=True)
    file = slides / 'anonymous.svs'; file.touch()
    monkeypatch.setattr(settings, 'UPLOAD_DIR', str(uploads))
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
    path = tmp_path / 'results/Quanti PD-L1' / f'{slide_cache_key(str(file))}_Quanti PD-L1_Stomach.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'cells': [[1, 2, 3, .9]], 'pd_score': {'score_type': 'CPS', 'score': 43.2}}))
    app = FastAPI();app.add_middleware(CSRFMiddleware);app.include_router(routes.router, prefix='/comparison')
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
    assert ai['result']['cells'] == [[1, 2, 3, .9]]
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
    listed = client.get('/comparison/records?project_path=project-one').json()['records']
    assert len(listed)==1 and listed[0]['_id']==record['_id']
    assert client.get('/comparison/records?project_path=other-project').json()['records']==[]
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
    assert client.get('/comparison/records?project_path=project-one').status_code==401
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
