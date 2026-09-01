import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

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


class TileMarkerRequestCacheTests(unittest.TestCase):
    def test_reuses_positive_marker_validation_within_ttl(self):
        file_path = "/tmp/mediauto-marker-cache-test.svs"
        tile_routes._forget_tiles_marker_cache(file_path)
        with patch.object(tile_routes, "tiles_marker_matches_file", return_value=True) as mocked:
            self.assertTrue(tile_routes._cached_tiles_marker_matches_file("test.svs", file_path))
            self.assertTrue(tile_routes._cached_tiles_marker_matches_file("test.svs", file_path))
        self.assertEqual(mocked.call_count, 1)
        tile_routes._forget_tiles_marker_cache(file_path)


if __name__ == "__main__":
    unittest.main()
