"""Behavioral regression tests for KP07, KP08, KP18 and KP26."""
import asyncio
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import text
from sqlalchemy.pool import NullPool
from sqlalchemy.engine import make_url
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app import auth, audit, download_security
from app.models import create_user_document, hash_password
from app.postgres import database
from app.postgres.base import Base
from app.repositories.auth_store import get_user_store, get_session_store
from app.routers import auth as auth_routes
from app.security_policy import check_session

PASSWORD = 'Secure7!Abc'
USER = '64f000000000000000000001'


@pytest.fixture
def security_client(monkeypatch, tmp_path):
    uri = os.environ.get('SECURITY_TEST_DATABASE_URI', '')
    schema = 'security_test_' + uuid.uuid4().hex
    if uri:
        parsed = make_url(uri)
        assert parsed.host == '127.0.0.1' and parsed.database == 'knuch_security_test', 'Use only the disposable test database'
        engine = create_async_engine(uri, poolclass=NullPool, connect_args={'server_settings': {'search_path': schema}})
    else:
        engine = create_async_engine('sqlite+aiosqlite:///' + str(tmp_path / 'security.sqlite'))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, '_session_factory', factory)
    monkeypatch.setattr(database, '_connected', True)
    monkeypatch.setattr(auth_routes, 'log_audit_event', AsyncMock(return_value='audit-test-id'))
    monkeypatch.setattr(auth_routes, 'enrich_audit_with_geo', AsyncMock())
    monkeypatch.setattr(download_security, 'log_audit_event', AsyncMock(return_value='download-test-id'))
    auth.invalidate_user_cache()

    async def setup():
        async with engine.begin() as conn:
            if uri:
                await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            await conn.run_sync(Base.metadata.create_all)
        user = create_user_document('doctor01', hash_password(PASSWORD), 'Test Doctor',
                                    str_role='doctor', str_approval_status='approved', bool_is_active=True)
        user['_id'] = USER
        await get_user_store().insert(user)
    asyncio.run(setup())
    app = FastAPI()
    app.include_router(auth_routes.router, prefix='/api/auth')

    @app.get('/api/private')
    async def private(user=Depends(auth.get_current_user)):
        return {'user': user['_id']}

    @app.get('/api/media')
    async def media(user=Depends(auth.get_media_user)):
        return {'user': user['_id']}

    with TestClient(app) as client:
        yield client
    async def cleanup():
        if uri:
            async with engine.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()
    asyncio.run(cleanup())
    auth.invalidate_user_cache()


def login(client, password=PASSWORD):
    result = client.post('/api/auth/login', json={'str_login_id': 'doctor01', 'str_password': password})
    assert result.status_code == 200, result.text
    return result.json()


def headers(tokens):
    return {'Authorization': 'Bearer ' + tokens['str_access_token']}


def test_second_login_revokes_access_refresh_and_media(security_client):
    client = security_client
    first = login(client)
    ticket = client.get('/api/auth/media-ticket', headers=headers(first)).json()['str_token']
    assert client.get('/api/media', params={'mt': ticket}).status_code == 200
    second = login(client)
    assert client.get('/api/private', headers=headers(second)).status_code == 200
    assert client.get('/api/private', headers=headers(first)).status_code == 401
    assert client.post('/api/auth/refresh', json={'str_refresh_token': first['str_refresh_token']}).status_code == 401
    assert client.get('/api/media', params={'mt': ticket}).status_code == 401
    # An obsolete refresh token must not revoke the replacement login.
    assert client.get('/api/private', headers=headers(second)).status_code == 200


def test_refresh_preserves_identity_without_touching_activity(security_client):
    client = security_client
    tokens = login(client)
    before = asyncio.run(get_user_store().find_by_id(USER))['dt_last_activity_at']
    response = client.post('/api/auth/refresh', json={'str_refresh_token': tokens['str_refresh_token']})
    assert response.status_code == 200, response.text
    new = response.json()
    assert auth.decode_token(new['str_access_token'])['sid'] == auth.decode_token(tokens['str_access_token'])['sid']
    assert asyncio.run(get_user_store().find_by_id(USER))['dt_last_activity_at'] == before
    assert client.get('/api/private', headers=headers(new)).status_code == 200


def test_idle_expiry_blocks_access_refresh_media_and_activity(security_client):
    client = security_client
    tokens = login(client)
    ticket = client.get('/api/auth/media-ticket', headers=headers(tokens)).json()['str_token']
    asyncio.run(get_user_store().update_by_id(USER, {'dt_last_activity_at': datetime.now(timezone.utc)-timedelta(minutes=31)}))
    assert client.get('/api/private', headers=headers(tokens)).status_code == 401
    assert client.post('/api/auth/activity', headers=headers(tokens)).status_code == 401
    assert client.post('/api/auth/refresh', json={'str_refresh_token': tokens['str_refresh_token']}).status_code == 401
    assert client.get('/api/media', params={'mt': ticket}).status_code == 401


def test_foreground_activity_extends_deadline_and_cannot_revive_old_session(security_client):
    client = security_client
    tokens = login(client)
    before = datetime.now(timezone.utc)-timedelta(minutes=25)
    asyncio.run(get_user_store().update_by_id(USER, {'dt_last_activity_at': before}))
    assert client.post('/api/auth/activity', headers=headers(tokens)).status_code == 200
    user = asyncio.run(get_user_store().find_by_id(USER))
    assert user['dt_last_activity_at'].replace(tzinfo=timezone.utc) > before
    assert not asyncio.run(get_user_store().touch_activity(USER, 'old-login', before))


@pytest.mark.parametrize('changed', [None, datetime.now(timezone.utc)-timedelta(days=91)])
def test_password_expiry_allows_only_recovery_and_revokes_old_tokens(security_client, changed):
    client = security_client
    asyncio.run(get_user_store().update_by_id(USER, {'dt_password_changed_at': changed}))
    tokens = login(client)
    assert tokens['bool_password_change_required'] is True
    assert client.get('/api/private', headers=headers(tokens)).json()['detail'] == 'PASSWORD_CHANGE_REQUIRED'
    assert client.get('/api/auth/me', headers=headers(tokens)).status_code == 200
    response = client.post('/api/auth/change-password', headers=headers(tokens), json={
        'str_current_password': PASSWORD, 'str_new_password': 'Changed8!Abc',
    })
    assert response.status_code == 200, response.text
    assert client.get('/api/auth/me', headers=headers(tokens)).status_code == 401
    updated = login(client, 'Changed8!Abc')
    assert not updated['bool_password_change_required']
    assert client.get('/api/private', headers=headers(updated)).status_code == 200


def test_password_minimum_and_complexity_and_no_reuse(security_client):
    client = security_client
    tokens = login(client)
    for weak in ('Aa1!abcd', 'abcdefghi', 'Abcdefgh1', PASSWORD):
        response = client.post('/api/auth/change-password', headers=headers(tokens), json={
            'str_current_password': PASSWORD, 'str_new_password': weak,
        })
        assert response.status_code in (400, 422), weak
    # Exactly nine characters satisfying all four categories is accepted.
    response = client.post('/api/auth/change-password', headers=headers(tokens), json={
        'str_current_password': PASSWORD, 'str_new_password': 'Abcde12!x',
    })
    assert response.status_code == 200


def test_five_failures_lock_even_correct_password(security_client):
    client = security_client
    for _ in range(5):
        assert client.post('/api/auth/login', json={'str_login_id': 'doctor01', 'str_password': 'WrongPassword!1'}).status_code == 401
    response = client.post('/api/auth/login', json={'str_login_id': 'doctor01', 'str_password': PASSWORD})
    assert response.status_code in (401, 403, 423, 429)
    user = asyncio.run(get_user_store().find_by_id(USER))
    assert user['bool_is_locked'] is True
    assert user['dt_locked_until'].replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)+timedelta(minutes=29)


def test_logout_revokes_current_access_and_refresh(security_client):
    client = security_client
    tokens = login(client)
    assert client.post('/api/auth/logout', headers=headers(tokens)).status_code == 200
    assert client.get('/api/private', headers=headers(tokens)).status_code == 401
    assert client.post('/api/auth/refresh', json={'str_refresh_token': tokens['str_refresh_token']}).status_code == 401


@pytest.mark.parametrize('reason', ['', ' ', 'a', 'x'*201, 'need\nexport'])
def test_download_invalid_reason_never_logs(security_client, reason):
    client = security_client
    tokens = login(client)
    response = client.post('/api/auth/download-intent', headers=headers(tokens), json={
        'str_reason': reason, 'str_filename': 'test.json',
    })
    assert response.status_code == 422
    download_security.log_audit_event.assert_not_awaited()


def test_download_reason_contains_actor_resource_and_ip(security_client):
    client = security_client
    tokens = login(client)
    response = client.post('/api/auth/download-intent', headers=headers(tokens), json={
        'str_reason': '  연구 결과 검토  ', 'str_filename': 'test.json',
    })
    assert response.status_code == 200
    args = download_security.log_audit_event.call_args.kwargs
    assert args['dict_extra']['download_reason'] == '연구 결과 검토'
    assert args['str_user_id'] == USER
    assert args['str_resource_id'] == 'test.json'
    assert args['str_ip_address']


@pytest.mark.parametrize('result', [None, RuntimeError('database unavailable')])
def test_download_audit_failure_blocks_export(security_client, monkeypatch, result):
    client = security_client
    tokens = login(client)
    mock = AsyncMock(side_effect=result) if isinstance(result, Exception) else AsyncMock(return_value=result)
    monkeypatch.setattr(download_security, 'log_audit_event', mock)
    response = client.post('/api/auth/download-intent', headers=headers(tokens), json={
        'str_reason': '연구 결과 검토', 'str_filename': 'test.json',
    })
    assert response.status_code == 503


def test_legacy_tokens_and_cache_cannot_bypass_security(security_client):
    client = security_client
    tokens = login(client)
    legacy = auth.create_access_token(USER, 'doctor')
    assert client.get('/api/private', headers={'Authorization': 'Bearer '+legacy}).status_code == 401
    assert client.get('/api/private', headers=headers(tokens)).status_code == 200
    asyncio.run(get_user_store().update_by_id(USER, {'bool_is_active': False}))
    assert client.get('/api/private', headers=headers(tokens)).status_code == 403


def test_concurrent_logins_leave_only_one_usable_session(security_client):
    client = security_client
    with ThreadPoolExecutor(max_workers=4) as pool:
        tokens = list(pool.map(lambda _: login(client), range(4)))
    results = [client.get('/api/private', headers=headers(item)).status_code for item in tokens]
    assert results.count(200) == 1
    assert results.count(401) == 3


def test_concurrent_failures_are_counted_atomically(security_client):
    # Exercise the actual store concurrently, without depending on HTTP scheduling.
    async def fail_together():
        deadline = datetime.now(timezone.utc) + timedelta(minutes=30)
        return await asyncio.gather(*(get_user_store().record_failed_login(USER, 5, deadline) for _ in range(5)))
    results = asyncio.run(fail_together())
    assert sorted(results) == [1, 2, 3, 4, 5]
    user = asyncio.run(get_user_store().find_by_id(USER))
    assert user['bool_is_locked'] and user['int_failed_login_attempts'] == 5


def test_download_reason_is_persisted_in_real_audit_store(security_client, monkeypatch):
    monkeypatch.setattr(download_security, 'log_audit_event', audit.log_audit_event)
    audit.reset_audit_chain_cache()
    client = security_client
    tokens = login(client)
    response = client.post('/api/auth/download-intent', headers=headers(tokens), json={
        'str_reason': '연구용 검토', 'str_filename': 'review.json',
    })
    assert response.status_code == 200, response.text
    from app.repositories.operational_store import get_audit_store
    records = asyncio.run(get_audit_store().list())
    record = next(row for row in records if row['str_action'] == 'file.download_requested')
    assert record['download_reason'] == '연구용 검토'
    assert audit.verify_log_hmac(record)[0] is True
    audit.reset_audit_chain_cache()


def test_zip_export_requires_reason_before_route_runs(security_client):
    from app.routers import cell_annotation
    client = security_client
    client.app.include_router(cell_annotation.router, prefix='/api/cell-annotation')
    tokens = login(client)
    response = client.get('/api/cell-annotation/projects/test/termination-export', headers=headers(tokens))
    assert response.status_code == 422
    download_security.log_audit_event.assert_not_awaited()


def test_zip_export_audit_failure_prevents_filesystem_work(security_client, monkeypatch):
    from app.routers import cell_annotation
    client = security_client
    client.app.include_router(cell_annotation.router, prefix='/api/cell-annotation')
    tokens = login(client)
    asyncio.run(get_user_store().update_by_id(USER, {'str_login_id': 'youngseoplee'}))
    monkeypatch.setattr(download_security, 'log_audit_event', AsyncMock(return_value=None))
    from unittest.mock import Mock
    filesystem = Mock(side_effect=AssertionError('No file generation before audit'))
    monkeypatch.setattr(cell_annotation, 'safe_subpath', filesystem)
    response = client.get('/api/cell-annotation/projects/test/termination-export', params={'reason': '연구 검토'}, headers=headers(tokens))
    assert response.status_code == 503
    filesystem.assert_not_called()


def test_registration_and_admin_creation_enforce_nine_characters(security_client, monkeypatch):
    from app.routers import users
    client = security_client
    client.app.include_router(users.router, prefix='/api/users')
    monkeypatch.setattr(users, 'log_audit_event', AsyncMock(return_value='audit-id'))
    tokens = login(client)
    asyncio.run(get_user_store().update_by_id(USER, {'str_role': 'admin'}))
    body = {'str_login_id': 'newdoctor', 'str_password': 'Abc1!xyz', 'str_name': 'Test User'}
    assert client.post('/api/auth/register', json=body).status_code == 422
    assert client.post('/api/users/create', json=body, headers=headers(tokens)).status_code == 422
    body['str_password'] = 'Abc12!xyz'
    assert client.post('/api/users/create', json=body, headers=headers(tokens)).status_code == 200
