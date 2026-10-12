"""Missing requested tiles finish before serving; valid cache bypasses work."""
import asyncio
import logging
import io
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.routers import tiles
from app.tile_generator import _mark_blank_tile
from app import tile_generator
from app.access_logging import SuccessfulTileAccessFilter


class Connected:
    async def is_disconnected(self): return False


class Disconnected:
    async def is_disconnected(self): return True


def save_tile(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with Image.new('RGB', (32, 32), (120, 30, 80)) as image: image.save(path, 'JPEG')


@pytest.fixture
def context(monkeypatch, tmp_path):
    info = SimpleNamespace(file_path='/fake/slide.svs', slide=SimpleNamespace(dimensions=(65536,65536)), apply_icc=lambda image:image)
    monkeypatch.setattr(tiles.slide_manager,'get',lambda _:info)
    monkeypatch.setattr(tiles,'get_tiles_dir_for_path',lambda _:tmp_path)
    monkeypatch.setattr(tiles,'tiles_marker_matches_file',lambda *args:False)
    monkeypatch.setattr(tiles,'notify_viewer_activity',lambda:None)
    monkeypatch.setattr(tiles,'request_priority_tile',lambda *args:None)
    monkeypatch.setattr(tiles,'get_thread_slide',lambda *args:info.slide)
    return info,tmp_path/'1/2_3.jpeg'


def test_present_tile_bypasses_full_viewer_queue(context,monkeypatch):
    info,path=context;save_tile(path)
    def forbidden(*args,**kwargs):raise AssertionError('A cache hit must not generate or wait for a worker')
    monkeypatch.setattr(tiles,'generate_priority_single_tile',forbidden)
    monkeypatch.setattr(tiles,'_find_and_open',forbidden)
    class OccupiedPool:
        def submit(self,*args):raise AssertionError('Cached tiles must bypass the queue')
    monkeypatch.setattr(tiles,'viewer_executor',OccupiedPool())
    response=asyncio.run(tiles.get_tile(Connected(),'slide',1,2,3,{}))
    assert response.status_code==200 and response.path==str(path)


@pytest.mark.parametrize('philips',[False,True])
def test_slow_missing_tile_finishes_before_response(context,monkeypatch,philips):
    info,path=context
    if philips:info.file_path='/fake/slide.i2syntax'
    def generate(*args,**kwargs):time.sleep(.8);save_tile(path);return True
    monkeypatch.setattr(tiles,'generate_priority_single_tile',generate)
    response=asyncio.run(tiles.get_tile(Connected(),'slide',1,2,3,{}))
    assert response.status_code==200 and path.exists()
    with Image.open(response.path) as image:assert image.format=='JPEG'


def test_concurrent_requests_generate_one_tile(context,monkeypatch):
    _,path=context;calls=[]
    def generate(*args,**kwargs):calls.append(1);time.sleep(.2);save_tile(path);return True
    monkeypatch.setattr(tiles,'generate_priority_single_tile',generate)
    async def run():
        results=await asyncio.gather(*(tiles.get_tile(Connected(),'slide',1,2,3,{}) for _ in range(6)))
        assert all(r.status_code==200 for r in results)
    asyncio.run(run());assert len(calls)==1
    assert str(path.resolve()) not in tiles._TILE_GENERATIONS


def test_missing_tile_waits_in_busy_queue_instead_of_503(context,monkeypatch):
    _,path=context;release=threading.Event();started=threading.Event()
    def occupy():started.set();release.wait(2)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(occupy);assert started.wait(1)
        monkeypatch.setattr(tiles,'viewer_executor',pool)
        monkeypatch.setattr(tiles,'generate_priority_single_tile',lambda *args,**kwargs:(save_tile(path) or True))
        async def run():
            task=asyncio.create_task(tiles.get_tile(Connected(),'slide',1,2,3,{}))
            await asyncio.sleep(.2);assert not task.done()
            release.set();assert (await task).status_code==200
        try:asyncio.run(run())
        finally:release.set()


def test_one_disconnected_client_does_not_cancel_shared_tile(context,monkeypatch):
    _,path=context;calls=[]
    def generate(*args,**kwargs):calls.append(1);time.sleep(.3);save_tile(path);return True
    monkeypatch.setattr(tiles,'generate_priority_single_tile',generate)
    async def run():
        results=await asyncio.gather(tiles.get_tile(Disconnected(),'slide',1,2,3,{}),tiles.get_tile(Connected(),'slide',1,2,3,{}),return_exceptions=True)
        assert isinstance(results[0],HTTPException) and results[0].status_code==499
        assert results[1].status_code==200
    asyncio.run(run());assert len(calls)==1 and path.exists()


def test_generation_failure_is_not_silenced_as_a_blank_success(context,monkeypatch):
    _,path=context
    def failed(*args,**kwargs):raise RuntimeError('Reader failed')
    monkeypatch.setattr(tiles,'generate_priority_single_tile',failed)
    with pytest.raises(HTTPException) as error:asyncio.run(tiles.get_tile(Connected(),'slide',1,2,3,{}))
    assert error.value.status_code==500 and not path.exists()


def test_blank_generation_returns_valid_white_image(context,monkeypatch):
    _,path=context
    monkeypatch.setattr(tiles,'generate_priority_single_tile',lambda *args,**kwargs:(_mark_blank_tile(path) or True))
    response=asyncio.run(tiles.get_tile(Connected(),'slide',1,2,3,{}))
    assert response.status_code==200 and response.media_type=='image/jpeg'


def test_actual_generator_saves_jpeg_before_http_serving(context,monkeypatch):
    _,path=context;reads=[]
    monkeypatch.setattr(tile_generator,'get_tiles_dir_for_path',lambda _:path.parent.parent)
    def region(slide, origin, size, output):
        reads.append(origin)
        return Image.new('RGB', output, (120,30,80))
    monkeypatch.setattr(tile_generator,'read_region_for_output',region)
    app=FastAPI();app.include_router(tiles.router,prefix='/api/tiles')
    app.dependency_overrides[tiles.get_media_user]=lambda:{'_id':'test'}
    with TestClient(app) as client:
        first=client.get('/api/tiles/slide/1/2/3.jpeg')
        assert first.status_code==200 and path.exists()
        with Image.open(io.BytesIO(first.content)) as image:
            assert image.format=='JPEG' and image.size==(tile_generator.TILE_SIZE_OUT,tile_generator.TILE_SIZE_OUT)
        second=client.get('/api/tiles/slide/1/2/3.jpeg')
        assert second.status_code==200 and second.content==first.content
    assert reads==[(8192,12288)]


@pytest.mark.parametrize('x,y',[(-1,0),(0,-1),(999,0)])
def test_bad_coordinates_do_not_trigger_generation(context,monkeypatch,x,y):
    monkeypatch.setattr(tiles,'generate_priority_single_tile',lambda *args,**kwargs:pytest.fail('Invalid coordinates generated'))
    with pytest.raises(HTTPException) as error:asyncio.run(tiles.get_tile(Connected(),'slide',1,x,y,{}))
    assert error.value.status_code==400


@pytest.mark.parametrize('status,visible',[(200,False),(304,False),(401,True),(403,True),(499,True),(500,True),(503,True)])
def test_only_successful_tile_access_logs_are_quiet(status,visible):
    record=logging.LogRecord('uvicorn.access',logging.INFO,'',0,'%s %s %s %s %s',('127.0.0.1','GET','/api/tiles/slide/1/2/3.jpeg?mt=opaque','1.1',status),None)
    assert SuccessfulTileAccessFilter().filter(record)==visible


def test_other_access_logs_remain_visible():
    record=logging.LogRecord('uvicorn.access',logging.INFO,'',0,'%s %s %s %s %s',('127.0.0.1','POST','/api/auth/activity','1.1',405),None)
    assert SuccessfulTileAccessFilter().filter(record)
