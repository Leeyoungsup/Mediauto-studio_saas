import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app import tile_janitor, database, slide_store
from app.config import settings


@pytest.mark.parametrize('block_at', ['inspect', 'remove'])
def test_filesystem_work_does_not_block_web_loop(tmp_path, monkeypatch, block_at):
    entered, release = threading.Event(), threading.Event()
    main_thread = threading.get_ident()
    threads = []
    folder = tmp_path / 'tiles'
    folder.mkdir()
    (folder / 'tile.jpeg').write_bytes(b'123')

    class Slides:
        async def find(self, *args):
            yield {'str_filename': 'slide.ndpi', 'str_full_path': '/slide.ndpi',
                   'str_rel_path': 'project'}

    monkeypatch.setattr(settings, 'TILE_CACHE_QUOTA_BYTES', 1)
    monkeypatch.setattr(database, 'is_db_connected', lambda: True)
    monkeypatch.setattr(database, 'get_db', lambda: SimpleNamespace(slides=Slides()))
    monkeypatch.setattr(tile_janitor, '_active_tile_keys', lambda: set())

    def wait_at(stage):
        threads.append(threading.get_ident())
        if stage == block_at:
            entered.set()
            assert release.wait(4)

    def inspect(*args):
        wait_at('inspect')
        return folder, 3, 0

    def remove(path):
        wait_at('remove')
        return True

    monkeypatch.setattr(tile_janitor, '_inspect_tiles', inspect)
    monkeypatch.setattr(tile_janitor, '_remove_tiles', remove)
    mark = AsyncMock()
    monkeypatch.setattr(slide_store, 'mark_tiles_ready', mark)

    async def run():
        task = asyncio.create_task(tile_janitor.run_janitor_once())
        try:
            for _ in range(100):
                if entered.is_set(): break
                await asyncio.sleep(.01)
            assert entered.is_set()
            assert not task.done()
            mark.assert_not_awaited()
            await asyncio.sleep(.02)  # unrelated requests can execute here
        finally:
            release.set()
        await task

    asyncio.run(run())
    assert all(t != main_thread for t in threads)
    mark.assert_awaited_once_with('project', 'slide.ndpi', False)


def test_newly_active_slide_is_not_deleted(tmp_path, monkeypatch):
    folder = tmp_path / 'active'
    folder.mkdir()
    monkeypatch.setattr(tile_janitor, '_active_tile_keys', lambda: {'active'})
    assert not tile_janitor._remove_tiles(folder)
    assert folder.exists()


def test_failed_removal_is_not_silently_counted(tmp_path):
    with pytest.raises(FileNotFoundError):
        tile_janitor._remove_tiles(tmp_path / 'missing')
