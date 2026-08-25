import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app.openslide_utils import open_slide_silently
from app.raster_slide import (
    FIXED_RASTER_MPP,
    FIXED_RASTER_OBJECTIVE_POWER,
    RasterSlideProxy,
    is_fixed_magnification_raster,
)
from app.slide_manager import SlideInfo


class RasterSlideProxyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.image_path = Path(self.temp_dir.name) / "test-slide.jpg"
        image = Image.new("RGB", (2400, 1200), (190, 70, 110))
        image.save(self.image_path, "JPEG", quality=95)
        image.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_jpeg_is_opened_with_fixed_20x_metadata(self):
        slide = open_slide_silently(str(self.image_path))
        try:
            self.assertIsInstance(slide, RasterSlideProxy)
            self.assertEqual(slide.dimensions, (2400, 1200))
            self.assertEqual(float(slide.properties["openslide.mpp-x"]), FIXED_RASTER_MPP)
            self.assertEqual(
                float(slide.properties["openslide.objective-power"]),
                FIXED_RASTER_OBJECTIVE_POWER,
            )
            self.assertGreaterEqual(slide.level_count, 2)

            info = SlideInfo(slide, str(self.image_path))
            self.assertEqual(info.mpp, 0.5)
            self.assertEqual(info.objective_power, "20")
            self.assertAlmostEqual(info.physical_width_mm, 1.2)
            self.assertAlmostEqual(info.physical_height_mm, 0.6)
        finally:
            slide.close()

    def test_read_region_matches_openslide_shape_and_padding(self):
        slide = RasterSlideProxy(self.image_path)
        try:
            region = slide.read_region((-20, -10), 0, (100, 80))
            self.assertEqual(region.mode, "RGBA")
            self.assertEqual(region.size, (100, 80))
            self.assertEqual(region.getpixel((0, 0))[3], 0)
            self.assertEqual(region.getpixel((30, 20))[3], 255)
            region.close()

            level = slide.get_best_level_for_downsample(2.0)
            reduced = slide.read_region((0, 0), level, (120, 60))
            self.assertEqual(reduced.size, (120, 60))
            reduced.close()

            thumbnail = slide.get_thumbnail((300, 300))
            self.assertEqual(thumbnail.size, (300, 150))
            thumbnail.close()
        finally:
            slide.close()

    def test_only_jpeg_extensions_use_fixed_raster_mode(self):
        self.assertTrue(is_fixed_magnification_raster("slide.jpg"))
        self.assertTrue(is_fixed_magnification_raster("slide.JPEG"))
        self.assertFalse(is_fixed_magnification_raster("slide.svs"))
        self.assertFalse(is_fixed_magnification_raster("slide.png"))


if __name__ == "__main__":
    unittest.main()
