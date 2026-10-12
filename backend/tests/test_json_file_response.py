import asyncio
import json
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app.json_file_response import CHUNK_SIZE, JsonFileEnvelopeResponse, json_file_envelope


def test_large_file_envelope_preserves_payload(tmp_path):
    payload={'cells':[{'x':i,'label':'세포'} for i in range(12000)],'excluded_cells':[], 'score':1.2}
    path=tmp_path/'result.json';path.write_text(json.dumps(payload))
    async def run():
        app=FastAPI()
        @app.get('/result')
        async def result():return await json_file_envelope(path,{'user_name':'이름"\\','ai_mode':'Quanti HE'})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            response=await client.get('/result')
            assert response.status_code==200
            assert response.json()=={'user_name':'이름"\\','ai_mode':'Quanti HE','result':payload}
            assert response.headers['cache-control']=='no-store'
    asyncio.run(run())


def test_unrelated_request_completes_during_slow_result_read():
    async def run():
        reading=asyncio.Event();release=asyncio.Event()
        class SlowFile:
            closed=False
            sent=False
            async def read(self,size):
                assert size==CHUNK_SIZE
                if self.sent:return b''
                reading.set();await release.wait();self.sent=True
                return b'{"cells":[]}'
            async def aclose(self):self.closed=True
        file=SlowFile();app=FastAPI()
        @app.get('/result')
        async def result():return JsonFileEnvelopeResponse(file,{'mode':'test'})
        @app.get('/ping')
        async def ping():return {'ok':True}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            request=asyncio.create_task(client.get('/result'))
            try:
                await asyncio.wait_for(reading.wait(),2)
                ping=await asyncio.wait_for(client.get('/ping'),1)
                assert ping.json()=={'ok':True} and not request.done()
            finally:release.set()
            assert (await request).json()['result']=={'cells':[]}
            assert file.closed
    asyncio.run(run())


def test_file_closed_if_response_send_fails():
    async def run():
        class File:
            closed=False
            async def read(self,size):return b'{}'
            async def aclose(self):self.closed=True
        file=File();response=JsonFileEnvelopeResponse(file,{})
        async def send(message):raise OSError('disconnected')
        async def receive():await asyncio.sleep(10)
        with pytest.raises(BaseException):
            await response({'type':'http','asgi':{'spec_version':'2.4'}},receive,send)
        assert file.closed
    asyncio.run(run())


def test_missing_file_fails_before_response(tmp_path):
    async def run():
        with pytest.raises(FileNotFoundError):await json_file_envelope(tmp_path/'missing',{})
    asyncio.run(run())


def test_open_reader_keeps_snapshot_during_atomic_replace(tmp_path):
    async def run():
        path=tmp_path/'result.json';path.write_text('{"cells":[1]}')
        response=await json_file_envelope(path,{})
        newer=tmp_path/'new.json';newer.write_text('{"cells":[2]}');newer.replace(path)
        try:
            chunks=[chunk async for chunk in response.body_iterator]
            assert json.loads(b''.join(chunks))=={'result':{'cells':[1]}}
        finally:await response.file.aclose()
    asyncio.run(run())


def test_saved_result_route_preserves_metadata_and_role_checks(monkeypatch, tmp_path):
    from unittest.mock import AsyncMock
    from fastapi.testclient import TestClient
    from app import auth, slide_store
    from app.routers import ai_user_edits
    path=tmp_path/'saved.json';path.write_text('{"cells":[{"class_id":1}],"total_cells":1}')
    lookup=AsyncMock(return_value={'str_file_path':str(path),'str_user_name':'Saved user'})
    monkeypatch.setattr(slide_store,'get_user_ai_edit',lookup)
    app=FastAPI();app.include_router(ai_user_edits.router,prefix='/ai')
    app.dependency_overrides[auth.get_current_user]=lambda:{'_id':'viewer','str_role':'doctor'}
    url='/ai/user-edits/load?slide_id=s1&ai_mode=HE-Fit&user_id=u1&variant=Stomach'
    with TestClient(app) as client:
        response=client.get(url)
        assert response.status_code==200
        assert response.json()=={'ai_mode':'Quanti HE','variant':'Stomach','user_id':'u1','user_name':'Saved user','result':{'cells':[{'class_id':1}],'total_cells':1}}
        lookup.assert_awaited_with('s1','Quanti HE','Stomach','u1')
        path.unlink();assert client.get(url).status_code==404
        lookup.reset_mock()
        app.dependency_overrides[auth.get_current_user]=lambda:{'str_role':'labeler'}
        assert client.get(url).status_code==403
        lookup.assert_not_awaited()
