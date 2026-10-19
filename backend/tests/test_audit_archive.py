import asyncio
import json
import os
import stat
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.exceptions import InvalidTag
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.audit_archive import AuditArchive, decrypt_archive, retain_until
from app.auth import get_current_user
from app.routers import users

PASSWORD = 'isolated-archive-test-phrase'


def test_archive_roundtrip_keeps_original_records_and_three_year_date(tmp_path):
    record = {'_id':'test-record','str_action':'admin.role_changed',
              'dt_created_at':datetime(2024,2,29,tzinfo=timezone.utc),'str_hmac':'original-signature',
              'dict_before':{'role':'viewer'},'dict_after':{'role':'doctor'}}
    archive = AuditArchive(PASSWORD)
    try:
        archive.append([record]); archive.finish()
        assert stat.S_IMODE(archive.path.stat().st_mode) == 0o600
        assert b'original-signature' not in archive.path.read_bytes()
        target = tmp_path/'restored.jsonl'
        summary = decrypt_archive(archive.path,target,PASSWORD)
        assert summary['record_count']==1 and summary['retain_until'].startswith('2027-02-28')
        rows=[json.loads(line) for line in target.read_text().splitlines()]
        assert rows[1]['record']['str_hmac']=='original-signature'
        assert rows[1]['record']['dict_before']=={'role':'viewer'}
        assert stat.S_IMODE(target.stat().st_mode)==0o600
        with pytest.raises(ValueError,match='already exists'):decrypt_archive(archive.path,target,PASSWORD)
    finally:archive.cleanup()


@pytest.mark.parametrize('damage',['wrong-password','tampered','truncated'])
def test_failed_authentication_never_publishes_plaintext(tmp_path,damage):
    archive=AuditArchive(PASSWORD)
    try:
        archive.append([{'_id':'secret','dt_created_at':datetime.now(timezone.utc)}]);archive.finish()
        phrase=PASSWORD
        if damage=='wrong-password':phrase='incorrect-test-phrase'
        elif damage=='tampered':
            raw=bytearray(archive.path.read_bytes());raw[-20]^=1;archive.path.write_bytes(raw)
        else:archive.path.write_bytes(archive.path.read_bytes()[:-10])
        with pytest.raises((InvalidTag,ValueError)):
            decrypt_archive(archive.path,tmp_path/'output.jsonl',phrase)
        assert list(tmp_path.iterdir())==[]
    finally:archive.cleanup()


def test_archive_endpoint_exports_every_page_and_masks_passphrase(monkeypatch,tmp_path):
    app=FastAPI();app.include_router(users.router,prefix='/users')
    app.dependency_overrides[get_current_user]=lambda:{'_id':'admin-test','str_role':'admin'}
    rows=[{'_id':str(i),'str_action':'admin.role_changed','dt_created_at':datetime.now(timezone.utc)} for i in range(2001)]
    async def listing(**kw):return rows[kw['int_skip']:kw['int_skip']+kw['int_limit']]
    mock=SimpleNamespace(list=AsyncMock(side_effect=listing))
    monkeypatch.setattr(users,'get_audit_store',lambda:mock)
    log=AsyncMock();monkeypatch.setattr(users,'log_audit_event',log)
    body=users.AuditArchiveRequest(passphrase=PASSWORD)
    assert PASSWORD not in repr(body)
    with TestClient(app) as client:
        response=client.post('/users/audit-logs/archive',json={'passphrase':PASSWORD})
        assert response.status_code==200,response.text
        assert response.headers['cache-control']=='no-store'
        archive=tmp_path/'download.audit.enc';archive.write_bytes(response.content)
        summary=decrypt_archive(archive,tmp_path/'restored.jsonl',PASSWORD)
        assert summary['record_count']==2001
        assert mock.list.await_count==4
        assert log.call_args.kwargs['str_detail']=='Encrypted archive of 2001 records'
        assert PASSWORD not in repr(log.call_args)
        assert client.post('/users/audit-logs/archive',json={'passphrase':'short'}).status_code==422
        app.dependency_overrides[get_current_user]=lambda:{'_id':'viewer-test','str_role':'viewer'}
        assert client.post('/users/audit-logs/archive',json={'passphrase':PASSWORD}).status_code==403
