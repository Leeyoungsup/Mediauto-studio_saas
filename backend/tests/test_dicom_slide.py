import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile, ZipInfo

from app.dicom_slide import (
    _safe_member_parts,
    _strip_dicom_frame_padding,
    is_dicom_slide_archive,
)


class DicomSlideArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_detects_zip_with_dicom_instances(self):
        archive = self.root / "slide.zip"
        with ZipFile(archive, "w") as output:
            output.writestr("DICOM/volume-1.dcm", b"test")
        self.assertTrue(is_dicom_slide_archive(archive))

    def test_rejects_zip_without_dicom_candidates(self):
        archive = self.root / "images.zip"
        with ZipFile(archive, "w") as output:
            output.writestr("readme.txt", b"test")
        self.assertFalse(is_dicom_slide_archive(archive))

    def test_rejects_parent_directory_member(self):
        with self.assertRaises(ValueError):
            _safe_member_parts(ZipInfo("../outside.dcm"))

    def test_strips_only_padding_after_jpeg_end_marker(self):
        frame = b"\xff\xd8payload\xff\xd9\xff\x00"
        self.assertEqual(_strip_dicom_frame_padding(frame), b"\xff\xd8payload\xff\xd9")
        frame_with_data = b"\xff\xd8payload\xff\xd9extra"
        self.assertEqual(_strip_dicom_frame_padding(frame_with_data), frame_with_data)


if __name__ == "__main__":
    unittest.main()
