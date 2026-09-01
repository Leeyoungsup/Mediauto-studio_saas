import asyncio
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
from fastapi import HTTPException

from app.tile_generator import (
    _mark_blank_tile,
    _save_jpeg,
    _tile_result_exists,
    blank_tile_marker_exists,
)
from app.routers import tiles as tile_routes


class TileBlankMarkerTests(unittest.TestCase):
    def test_blank_marker_is_replaced_by_rendered_tile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path_tile = Path(temp_dir) / "1" / "2_3.jpeg"
            _mark_blank_tile(path_tile)

            self.assertFalse(path_tile.exists())
            self.assertTrue(blank_tile_marker_exists(path_tile))
            self.assertTrue(_tile_result_exists(path_tile))

            image = Image.new("RGB", (32, 32), (120, 30, 80))
            try:
                _save_jpeg(image, path_tile, 85)
            finally:
                image.close()

            self.assertTrue(path_tile.exists())
            self.assertFalse(blank_tile_marker_exists(path_tile))
            self.assertTrue(_tile_result_exists(path_tile))

    def test_partial_cache_tile_is_served_before_complete_marker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path_root = Path(temp_dir)
            path_tile = path_root / "1" / "2_2.jpeg"
            path_tile.parent.mkdir(parents=True)
            image = Image.new("RGB", (32, 32), (120, 30, 80))
            try:
                image.save(path_tile, "JPEG")
            finally:
                image.close()

            info = SimpleNamespace(file_path="/fake/slide.zip")
            with (
                patch.object(tile_routes, "_find_and_open", return_value=info),
                patch.object(tile_routes, "get_tiles_dir_for_path", return_value=path_root),
                patch.object(tile_routes, "tiles_marker_matches_file", return_value=False),
                patch.object(tile_routes, "notify_viewer_activity"),
            ):
                response = asyncio.run(
                    tile_routes.get_tile(None, "slide-id", 1, 2, 2, {})
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(Path(response.path), path_tile)

    def test_blank_marker_returns_cacheable_white_tile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path_root = Path(temp_dir)
            path_tile = path_root / "1" / "2_2.jpeg"
            _mark_blank_tile(path_tile)

            info = SimpleNamespace(file_path="/fake/slide.zip")
            with (
                patch.object(tile_routes, "_find_and_open", return_value=info),
                patch.object(tile_routes, "get_tiles_dir_for_path", return_value=path_root),
                patch.object(tile_routes, "tiles_marker_matches_file", return_value=False),
                patch.object(tile_routes, "notify_viewer_activity"),
            ):
                response = asyncio.run(
                    tile_routes.get_tile(None, "slide-id", 1, 2, 2, {})
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "public, max-age=604800")

    def test_disconnected_request_sets_worker_cancel_event(self):
        bool_worker_started = threading.Event()
        bool_worker_cancelled = threading.Event()

        class DisconnectedRequest:
            async def is_disconnected(self):
                return True

        def cancellable_job(cancel_event):
            bool_worker_started.set()
            if cancel_event.wait(2):
                bool_worker_cancelled.set()
            return None

        async def run_job():
            with self.assertRaises(HTTPException) as context:
                await tile_routes._run_viewer_job(DisconnectedRequest(), cancellable_job)
            self.assertEqual(context.exception.status_code, 499)

        asyncio.run(run_job())
        self.assertTrue(bool_worker_started.wait(1))
        self.assertTrue(bool_worker_cancelled.wait(1))

    def test_response_timeout_does_not_cancel_running_tile_generation(self):
        bool_worker_started = threading.Event()
        bool_release_worker = threading.Event()
        bool_worker_finished = threading.Event()
        bool_cancel_seen = threading.Event()

        class ConnectedRequest:
            async def is_disconnected(self):
                return False

        def slow_tile_job(cancel_event):
            bool_worker_started.set()
            bool_release_worker.wait(2)
            if cancel_event.is_set():
                bool_cancel_seen.set()
            bool_worker_finished.set()
            return None

        async def run_job():
            with self.assertRaises(HTTPException) as context:
                await tile_routes._run_viewer_job(
                    ConnectedRequest(),
                    slow_tile_job,
                    timeout_seconds=0.01,
                )
            self.assertEqual(context.exception.status_code, 503)

        asyncio.run(run_job())
        self.assertTrue(bool_worker_started.wait(1))
        bool_release_worker.set()
        self.assertTrue(bool_worker_finished.wait(1))
        self.assertFalse(bool_cancel_seen.is_set())


if __name__ == "__main__":
    unittest.main()
