"""KP04 capability matrix, KP09 admin network enforcement, encryption key validation."""
import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException, Depends
from fastapi.testclient import TestClient

from app import auth, encryption
from app.admin_network import AdminNetworkMiddleware
from app.permissions import CAPABILITY_ROLES, check_capability
from app.config import settings
from app.routers import users, projects, admin_settings


@pytest.mark.parametrize('capability,allowed', list(CAPABILITY_ROLES.items()))
@pytest.mark.parametrize('role', ['admin', 'doctor', 'labeler', 'viewer', 'unknown', ''])
def test_permission_matrix_has_no_implicit_grants(capability, allowed, role):
    if role in allowed:
        check_capability(role, capability)
    else:
        with pytest.raises(HTTPException) as exc:
            check_capability(role, capability)
        assert exc.value.status_code == 403


def test_unknown_capability_is_denied_even_to_admin():
    with pytest.raises(HTTPException):
        check_capability('admin', 'not-configured')


@pytest.mark.parametrize('path', ['/admin', '/admin.html', '/api/admin/settings', '/api/users',
                                  '/api/users/audit-logs', '/api/users/create', '/api/slides/open-local'])
@pytest.mark.parametrize('peer,allowed', [('192.168.0.1', True), ('192.168.0.255', True),
                                        ('127.0.0.1', True), ('::1', True),
                                        ('::ffff:192.168.0.10', True), ('192.168.1.10', False),
                                        ('203.0.113.10', False), ('::ffff:203.0.113.10', False)])
def test_admin_network_pages_and_api_ignore_forged_headers(path, peer, allowed):
    called = []
    async def app(scope, receive, send):
        called.append(True)
        await send({'type': 'http.response.start', 'status': 204, 'headers': []})
        await send({'type': 'http.response.body', 'body': b''})
    async def run():
        messages=[]
        async def receive(): return {'type': 'http.request', 'body': b''}
        async def send(msg): messages.append(msg)
        scope={'type':'http', 'path':path, 'method':'GET', 'client':(peer,1234),
               'headers':[(b'x-forwarded-for',b'192.168.0.5'),(b'x-real-ip',b'127.0.0.1')]}
        await AdminNetworkMiddleware(app)(scope,receive,send)
        return messages[0]['status']
    assert asyncio.run(run()) == (204 if allowed else 403)
    assert bool(called) == allowed


@pytest.mark.parametrize('value', ['', '0.0.0.0/0', '::/0', 'invalid'])
def test_unsafe_admin_network_configuration_fails_closed(value):
    with pytest.raises(ValueError):AdminNetworkMiddleware(None, value)


@pytest.mark.parametrize('path', ['/api/users/me', '/api/users/me/preferences', '/api/slides/projects', '/api/auth/me'])
def test_administrator_network_policy_does_not_block_self_service(path):
    from app.admin_network import administrator_path
    assert not administrator_path(path)


@pytest.mark.parametrize('role', ['doctor','labeler','viewer'])
@pytest.mark.parametrize('prefix,router,path', [('/api/users', users.router, '/create'),
                                              ('/api/admin', admin_settings.router, '/settings')])
def test_non_admins_cannot_call_management_api(role, prefix, router, path):
    app=FastAPI();app.include_router(router,prefix=prefix)
    app.dependency_overrides[auth.get_current_user]=lambda:{'_id':'tester','str_role':role}
    with TestClient(app) as client:
        response=client.get(prefix+path) if path=='/settings' else client.post(prefix+path,json={})
    assert response.status_code==403


@pytest.mark.parametrize('role', ['labeler','viewer'])
@pytest.mark.parametrize('path', ['/project/create','/project/update','/project/rename','/project/move-folder','/project/delete'])
def test_labeler_and_viewer_cannot_bypass_project_ui(role,path):
    app=FastAPI();app.include_router(projects.router,prefix='/api/slides')
    app.dependency_overrides[auth.get_current_user]=lambda:{'_id':'tester','str_role':role}
    with TestClient(app) as client:
        assert client.post('/api/slides'+path,data={}).status_code==403


@pytest.mark.parametrize('raw', [b'1', b'1'*16, b'1'*31, b'1'*33])
def test_non_256_bit_keys_are_rejected_instead_of_padded_or_truncated(monkeypatch,raw):
    monkeypatch.setattr(settings,'FIELD_ENCRYPTION_KEY',base64.urlsafe_b64encode(raw).decode())
    with pytest.raises(ValueError):encryption.encrypt_field('protected data')


def test_invalid_base64_key_is_rejected(monkeypatch):
    monkeypatch.setattr(settings,'FIELD_ENCRYPTION_KEY','not valid base64!')
    with pytest.raises(ValueError):encryption.encrypt_field('protected data')


def test_authenticated_encryption_roundtrip_and_tamper_rejection(monkeypatch):
    import os
    from cryptography.exceptions import InvalidTag
    monkeypatch.setattr(settings,'FIELD_ENCRYPTION_KEY',base64.urlsafe_b64encode(os.urandom(32)).decode())
    cipher=encryption.encrypt_field('검증 데이터')
    assert encryption.decrypt_field(cipher)=='검증 데이터'
    changed=bytearray(base64.urlsafe_b64decode(cipher));changed[-1]^=1
    with pytest.raises(InvalidTag):encryption.decrypt_field(base64.urlsafe_b64encode(changed).decode())
