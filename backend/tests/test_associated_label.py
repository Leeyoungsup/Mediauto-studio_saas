import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app import tile_generator


class _FakeSlide:
    def __init__(self, associated_images):
        self.associated_images = associated_images


class AssociatedLabelTests(unittest.TestCase):
    def test_explicit_label_is_cached_case_insensitively(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path_root = Path(temp_dir)
            path_source = path_root / "slide.svs"
            path_source.write_bytes(b"slide")
            path_tiles = path_root / "tiles"
            obj_label = Image.new("RGB", (500, 200), (30, 90, 150))
            obj_macro = Image.new("RGB", (800, 300), (220, 220, 220))
            slide = _FakeSlide({"LABEL": obj_label, "macro": obj_macro})

            path_cached = tile_generator.generate_associated_label_cache(
                slide, path_tiles, str(path_source), int_size=300
            )

            self.assertEqual(path_cached, path_tiles / "associated_label_300.jpeg")
            self.assertTrue(path_cached.is_file())
            with patch.object(tile_generator, "get_tiles_dir_for_path", return_value=path_tiles):
                self.assertTrue(tile_generator.associated_label_cache_status(str(path_source)))
            with Image.open(path_cached) as image:
                self.assertLessEqual(max(image.size), 300)
            obj_macro.close()

    def test_macro_without_label_is_not_treated_as_label(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path_root = Path(temp_dir)
            path_source = path_root / "slide.ndpi"
            path_source.write_bytes(b"slide")
            path_tiles = path_root / "tiles"
            obj_macro = Image.new("RGB", (600, 205), (0, 0, 0))
            slide = _FakeSlide({"macro": obj_macro})

            path_cached = tile_generator.generate_associated_label_cache(
                slide, path_tiles, str(path_source), int_size=300
            )

            self.assertIsNone(path_cached)
            with patch.object(tile_generator, "get_tiles_dir_for_path", return_value=path_tiles):
                self.assertFalse(tile_generator.associated_label_cache_status(str(path_source)))
            dict_status = json.loads(
                (path_tiles / tile_generator.ASSOCIATED_LABEL_STATUS_NAME).read_text()
            )
            self.assertFalse(dict_status["has_label"])
            obj_macro.close()

    def test_source_change_invalidates_label_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path_root = Path(temp_dir)
            path_source = path_root / "slide.svs"
            path_source.write_bytes(b"first")
            path_tiles = path_root / "tiles"
            slide = _FakeSlide({})
            tile_generator.generate_associated_label_cache(
                slide, path_tiles, str(path_source), int_size=300
            )
            with patch.object(tile_generator, "get_tiles_dir_for_path", return_value=path_tiles):
                self.assertFalse(tile_generator.associated_label_cache_status(str(path_source)))

            path_source.write_bytes(b"replacement slide")
            with patch.object(tile_generator, "get_tiles_dir_for_path", return_value=path_tiles):
                self.assertIsNone(tile_generator.associated_label_cache_status(str(path_source)))


if __name__ == "__main__":
    unittest.main()
