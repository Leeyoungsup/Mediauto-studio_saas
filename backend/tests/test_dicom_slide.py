import sqlite3
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

from app import dicom_slide
from app.dicom_slide import (
    _CompatibleDICOMFileClient,
    _load_wsi_metadata,
    _safe_member_parts,
    _strip_dicom_frame_padding,
    is_dicom_slide_archive,
)
from app.thread_slide_pool import get_thread_slide
from app.slide_manager import SlideManager


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

    def test_metadata_scan_is_reused_for_same_extraction(self):
        extraction = self.root / "immutable-extraction"
        extraction.mkdir()
        dataset = SimpleNamespace(SOPInstanceUID="1.2.3")
        group = ("container", "frame")

        with patch.object(
            dicom_slide,
            "_load_wsi_metadata_uncached",
            return_value=([dataset], group),
        ) as mocked_load:
            first, first_group = _load_wsi_metadata(extraction)
            second, second_group = _load_wsi_metadata(extraction)

        self.assertEqual(mocked_load.call_count, 1)
        self.assertIsNot(first, second)
        self.assertIs(first[0], second[0])
        self.assertEqual(first_group, group)
        self.assertEqual(second_group, group)

    def test_file_client_uses_persistent_cross_thread_sqlite_index(self):
        extraction = self.root / "extraction"
        extraction.mkdir()
        captured = {}

        class FakeClient:
            def __init__(self, **kwargs):
                captured.update(kwargs)
                path_db = Path(kwargs["db_dir"]) / ".dicom-file-client.db"
                connection = sqlite3.connect(path_db)
                cursor = connection.cursor()
                cursor.execute("CREATE TABLE IF NOT EXISTS probe (value INTEGER)")
                self._db_manager = SimpleNamespace(
                    _db_file_identifier=str(path_db),
                    _db_connection_handle=connection,
                    _db_cursor_handle=cursor,
                )

            def retrieve_instance_frames(self, *args, **kwargs):
                return [b"\xff\xd8frame\xff\xd9\x00"]

        with patch("dicomweb_client.DICOMfileClient", FakeClient):
            client = _CompatibleDICOMFileClient.create(extraction)

        self.assertFalse(captured["in_memory"])
        self.assertEqual(Path(captured["db_dir"]), extraction)
        self.assertTrue(captured["readonly"])
        self.assertEqual(
            client.retrieve_instance_frames(),
            [b"\xff\xd8frame\xff\xd9"],
        )

        def query_from_worker():
            return client._db_manager._db_connection_handle.execute(
                "SELECT 1"
            ).fetchone()[0]

        with ThreadPoolExecutor(max_workers=1) as executor:
            self.assertEqual(executor.submit(query_from_worker).result(), 1)

    def test_thread_workers_reuse_manager_dicom_proxy(self):
        shared_slide = SimpleNamespace(is_dicom=True)
        info = SimpleNamespace(file_path="/slides/example.zip", slide=shared_slide)
        with (
            patch("app.thread_slide_pool.slide_manager.get", return_value=info),
            patch("app.thread_slide_pool.open_slide_silently") as mocked_open,
        ):
            result = get_thread_slide("slide-id", "/slides/example.zip")

        self.assertIs(result, shared_slide)
        mocked_open.assert_not_called()

    def test_slow_slide_open_does_not_hold_manager_global_lock(self):
        manager = SlideManager()
        bool_open_started = threading.Event()
        bool_release_open = threading.Event()
        fake_slide = SimpleNamespace(close=lambda: None)

        def slow_open(_path):
            bool_open_started.set()
            bool_release_open.wait(2)
            return fake_slide

        def make_info(slide, file_path):
            info = SimpleNamespace(
                slide=slide,
                file_path=file_path,
                last_accessed=time.time(),
            )
            info.touch = lambda: setattr(info, "last_accessed", time.time())
            return info

        with (
            patch("app.slide_manager.is_philips_isyntax", return_value=False),
            patch("app.slide_manager.open_slide_silently", side_effect=slow_open),
            patch("app.slide_manager.SlideInfo", side_effect=make_info),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            future_open = executor.submit(manager.open, "slow-slide", "/slides/slow.zip")
            self.assertTrue(bool_open_started.wait(1))
            future_get = executor.submit(manager.get, "other-slide")
            try:
                self.assertIsNone(future_get.result(timeout=0.25))
            finally:
                bool_release_open.set()
            self.assertEqual(future_open.result(timeout=1).file_path, "/slides/slow.zip")


if __name__ == "__main__":
    unittest.main()
