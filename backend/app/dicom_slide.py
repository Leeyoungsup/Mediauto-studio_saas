"""OpenSlide-compatible access to DICOM WSI archives via dicomslide.

The upload unit is a ZIP archive containing the DICOM instances for one
physical glass slide. Instances are extracted to a source-signature cache,
grouped by Container Identifier and Frame of Reference UID, and exposed through
``dicomslide.OpenSlide`` so the viewer and AI patch readers can use the same
``read_region`` interface as SVS/NDPI slides.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import sqlite3
import tempfile
import threading
import time
import warnings
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import BadZipFile, ZipFile, ZipInfo

from app.config import settings
from app.slide_identity import slide_cache_key


DICOM_WSI_SOP_CLASS_UID = "1.2.840.10008.5.1.4.1.1.77.1.6"
_extract_locks_guard = threading.Lock()
_extract_locks: dict[str, threading.Lock] = {}
_metadata_cache_lock = threading.Lock()
_metadata_cache: dict[str, tuple[tuple[Any, ...], tuple[str, str]]] = {}
_expected_unprofiled_associated_uids: set[str] = set()


class _DicomSlideExpectedMessageFilter(logging.Filter):
    """Hide dicomslide messages that are informational for this adapter."""

    _frame_count_pattern = re.compile(r"^n=\d+ frames will be retrieved$")
    _missing_icc_pattern = re.compile(
        r'^color image "([^"]+)" does not contain an ICC profile - '
        r'pixel values will not be color corrected$'
    )

    def filter(self, record: logging.LogRecord) -> bool:
        str_message = record.getMessage()
        if self._frame_count_pattern.fullmatch(str_message):
            # dicomslide emits this at WARNING even though it only reports the
            # number of tiled frames covered by a normal region read.
            return False
        match = self._missing_icc_pattern.fullmatch(str_message)
        if match and match.group(1) in _expected_unprofiled_associated_uids:
            # LABEL/OVERVIEW images commonly omit ICC. Keep the same warning
            # visible for a VOLUME image, where it may affect pathology color.
            return False
        return True


_dicomslide_log_filter = _DicomSlideExpectedMessageFilter()
_dicomslide_matrix_logger = logging.getLogger("dicomslide.matrix")
if not any(
    isinstance(obj_filter, _DicomSlideExpectedMessageFilter)
    for obj_filter in _dicomslide_matrix_logger.filters
):
    _dicomslide_matrix_logger.addFilter(_dicomslide_log_filter)


def _archive_lock(file_path: str | Path) -> threading.Lock:
    str_key = str(Path(file_path).resolve())
    with _extract_locks_guard:
        obj_lock = _extract_locks.get(str_key)
        if obj_lock is None:
            obj_lock = threading.Lock()
            _extract_locks[str_key] = obj_lock
        return obj_lock


def is_dicom_slide_archive(file_path: str | Path) -> bool:
    """Return True when a ZIP contains DICOM WSI candidates."""

    path_archive = Path(file_path)
    if path_archive.suffix.lower() != ".zip" or not path_archive.is_file():
        return False
    try:
        with ZipFile(path_archive) as obj_zip:
            list_names = [name for name in obj_zip.namelist() if not name.endswith("/")]
        return any(
            PurePosixPath(name).suffix.lower() == ".dcm"
            or PurePosixPath(name).name.upper() == "DICOMDIR"
            for name in list_names
        )
    except (BadZipFile, OSError):
        return False


def _source_signature(path_archive: Path) -> dict[str, Any]:
    stat = path_archive.stat()
    return {
        "path": str(path_archive.resolve()),
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


def _signature_name(dict_signature: dict[str, Any]) -> str:
    bytes_value = json.dumps(
        dict_signature, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha1(bytes_value).hexdigest()[:16]


def dicom_archive_cache_root(file_path: str | Path) -> Path:
    return Path(settings.DICOM_CACHE_DIR) / slide_cache_key(str(file_path))


def cleanup_dicom_archive_cache(file_path: str | Path) -> None:
    """Remove extracted DICOM instances for one archive."""

    path_root = dicom_archive_cache_root(file_path)
    if path_root.exists():
        shutil.rmtree(path_root, ignore_errors=True)


def _safe_member_parts(obj_info: ZipInfo) -> tuple[str, ...]:
    path_member = PurePosixPath(obj_info.filename.replace("\\", "/"))
    if path_member.is_absolute() or not path_member.parts:
        raise ValueError(f"Unsafe DICOM ZIP member: {obj_info.filename}")
    if any(part in {"", ".", ".."} for part in path_member.parts):
        raise ValueError(f"Unsafe DICOM ZIP member: {obj_info.filename}")
    return tuple(path_member.parts)


def _selected_members(obj_zip: ZipFile) -> list[ZipInfo]:
    list_files = [info for info in obj_zip.infolist() if not info.is_dir()]
    bool_has_dicomdir = any(
        PurePosixPath(info.filename.replace("\\", "/")).name.upper() == "DICOMDIR"
        for info in list_files
    )
    if bool_has_dicomdir:
        # DICOM media may use extensionless files referenced by DICOMDIR.
        list_selected = list_files
    else:
        list_selected = [
            info for info in list_files
            if PurePosixPath(info.filename.replace("\\", "/")).suffix.lower() == ".dcm"
        ]
    if not list_selected:
        raise ValueError("ZIP archive contains no DICOM files")
    if len(list_selected) > int(settings.DICOM_ZIP_MAX_FILES):
        raise ValueError(
            f"DICOM ZIP contains too many files: {len(list_selected):,} "
            f"(limit {int(settings.DICOM_ZIP_MAX_FILES):,})"
        )
    int_total = sum(max(0, int(info.file_size)) for info in list_selected)
    if int_total > int(settings.DICOM_ZIP_MAX_UNCOMPRESSED_BYTES):
        raise ValueError(
            f"DICOM ZIP expands to {int_total / (1024 ** 3):.1f} GB "
            f"(limit {int(settings.DICOM_ZIP_MAX_UNCOMPRESSED_BYTES) / (1024 ** 3):.1f} GB)"
        )
    return list_selected


def _extract_archive(file_path: str | Path) -> Path:
    path_archive = Path(file_path).resolve()
    dict_signature = _source_signature(path_archive)
    path_root = dicom_archive_cache_root(path_archive)
    path_version = path_root / _signature_name(dict_signature)
    path_complete = path_version / ".complete.json"
    if path_complete.is_file():
        return path_version

    with _archive_lock(path_archive):
        if path_complete.is_file():
            return path_version
        path_root.mkdir(parents=True, exist_ok=True)
        path_temp = Path(tempfile.mkdtemp(prefix=".extracting-", dir=str(path_root)))
        int_written = 0
        try:
            with ZipFile(path_archive) as obj_zip:
                list_members = _selected_members(obj_zip)
                for obj_info in list_members:
                    tuple_parts = _safe_member_parts(obj_info)
                    path_output = path_temp.joinpath(*tuple_parts)
                    path_output.parent.mkdir(parents=True, exist_ok=True)
                    with obj_zip.open(obj_info, "r") as file_source, open(path_output, "wb") as file_output:
                        while True:
                            bytes_chunk = file_source.read(1024 * 1024)
                            if not bytes_chunk:
                                break
                            int_written += len(bytes_chunk)
                            if int_written > int(settings.DICOM_ZIP_MAX_UNCOMPRESSED_BYTES):
                                raise ValueError("DICOM ZIP exceeded the extraction size limit")
                            file_output.write(bytes_chunk)
            (path_temp / ".complete.json").write_text(
                json.dumps(dict_signature, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            if path_version.exists():
                shutil.rmtree(path_temp, ignore_errors=True)
            else:
                path_temp.replace(path_version)
            return path_version
        except Exception:
            shutil.rmtree(path_temp, ignore_errors=True)
            raise


def _strip_dicom_frame_padding(bytes_frame: bytes) -> bytes:
    """Trim trailing JPEG padding after the final EOI marker."""

    int_eoi = bytes_frame.rfind(b"\xff\xd9")
    if int_eoi < 0:
        return bytes_frame
    bytes_tail = bytes_frame[int_eoi + 2:]
    if bytes_tail and all(value in (0x00, 0xFF) for value in bytes_tail):
        return bytes_frame[:int_eoi + 2]
    return bytes_frame


class _CompatibleDICOMFileClient:
    """Create a reusable local index with Leica frame compatibility.

    ``in_memory=True`` forces dicomweb-client to rescan every extracted DICOM
    instance for every proxy.  A source-signature extraction directory is
    immutable, so its SQLite index can safely be persisted and reused.
    """

    @staticmethod
    def create(path_root: Path):
        from dicomweb_client import DICOMfileClient

        class _Client(DICOMfileClient):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)

                # A DicomSlideProxy serializes access with its own RLock but is
                # intentionally shared by viewer/AI threads.  Reopen the
                # persistent index with SQLite's cross-thread guard disabled;
                # serialization remains enforced by the proxy.
                obj_manager = self._db_manager
                obj_cursor = getattr(obj_manager, "_db_cursor_handle", None)
                obj_connection = getattr(obj_manager, "_db_connection_handle", None)
                if obj_cursor is not None:
                    obj_cursor.close()
                if obj_connection is not None:
                    obj_connection.commit()
                    obj_connection.close()
                obj_connection = sqlite3.connect(
                    str(obj_manager._db_file_identifier),
                    detect_types=sqlite3.PARSE_DECLTYPES,
                    check_same_thread=False,
                )
                obj_connection.row_factory = sqlite3.Row
                obj_manager._db_connection_handle = obj_connection
                obj_manager._db_cursor_handle = None

            def retrieve_instance_frames(self, *args, **kwargs):
                list_frames = super().retrieve_instance_frames(*args, **kwargs)
                return [_strip_dicom_frame_padding(value) for value in list_frames]

        # Only the first open creates the index. Concurrent first opens must
        # not race while dicomweb-client creates the SQLite schema.
        with _archive_lock(path_root):
            return _Client(
                url=path_root.as_uri(),
                in_memory=False,
                db_dir=path_root,
                readonly=True,
            )


def _image_flavor(dataset) -> str:
    list_image_type = list(getattr(dataset, "ImageType", []) or [])
    return str(list_image_type[2]).upper() if len(list_image_type) > 2 else ""


def _slide_group_key(dataset) -> tuple[str, str]:
    str_container = str(getattr(dataset, "ContainerIdentifier", "") or "").strip()
    str_frame = str(getattr(dataset, "FrameOfReferenceUID", "") or "").strip()
    if not str_container:
        str_container = str(getattr(dataset, "SeriesInstanceUID", "") or "").strip()
    return str_container, str_frame


def _load_wsi_metadata_uncached(path_root: Path) -> tuple[list, tuple[str, str]]:
    import pydicom

    dict_groups: dict[tuple[str, str], list] = {}
    for path_file in path_root.rglob("*"):
        if (
            not path_file.is_file()
            or path_file.name == ".complete.json"
            or path_file.name.startswith(".dicom-file-client.db")
        ):
            continue
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Invalid value for VR DT:.*")
                dataset = pydicom.dcmread(path_file, stop_before_pixels=True)
        except Exception:
            continue
        if str(getattr(dataset, "SOPClassUID", "")) != DICOM_WSI_SOP_CLASS_UID:
            continue
        tuple_key = _slide_group_key(dataset)
        dict_groups.setdefault(tuple_key, []).append(dataset)

    if not dict_groups:
        raise ValueError("Archive contains no VL Whole Slide Microscopy Image instances")
    if len(dict_groups) != 1:
        raise ValueError(
            f"DICOM ZIP contains {len(dict_groups)} physical slides; "
            "upload one physical slide per ZIP"
        )
    tuple_key, list_metadata = next(iter(dict_groups.items()))
    if not any(_image_flavor(item) == "VOLUME" for item in list_metadata):
        raise ValueError("DICOM slide contains no VOLUME image instances")

    # Leica thumbnails can have a different origin than VOLUME matrices. The
    # VOLUME pyramid already includes a low-resolution level, so excluding the
    # THUMBNAIL is safe while LABEL/OVERVIEW remain associated images.
    list_usable = [item for item in list_metadata if _image_flavor(item) != "THUMBNAIL"]
    for item in list_usable:
        if _image_flavor(item) not in {"LABEL", "OVERVIEW"}:
            continue
        list_optical_paths = list(getattr(item, "OpticalPathSequence", []) or [])
        bool_has_icc = bool(
            list_optical_paths and hasattr(list_optical_paths[0], "ICCProfile")
        )
        if not bool_has_icc:
            _expected_unprofiled_associated_uids.add(
                str(getattr(item, "SOPInstanceUID", "") or "")
            )
    return list_usable, tuple_key


def _load_wsi_metadata(path_root: Path) -> tuple[list, tuple[str, str]]:
    """Load header-only WSI metadata once per immutable extraction version."""

    str_key = str(path_root.resolve())
    with _metadata_cache_lock:
        tuple_cached = _metadata_cache.get(str_key)
    if tuple_cached is not None:
        tuple_metadata, tuple_group = tuple_cached
        return list(tuple_metadata), tuple_group

    # Avoid duplicate multi-frame header scans when several initial tile
    # requests reach a newly opened DICOM slide at the same time.
    with _archive_lock(path_root):
        with _metadata_cache_lock:
            tuple_cached = _metadata_cache.get(str_key)
        if tuple_cached is None:
            list_metadata, tuple_group = _load_wsi_metadata_uncached(path_root)
            tuple_cached = (tuple(list_metadata), tuple_group)
            with _metadata_cache_lock:
                _metadata_cache[str_key] = tuple_cached
        tuple_existing = tuple_cached
    return list(tuple_existing[0]), tuple_existing[1]


class DicomSlideProxy:
    """OpenSlide-compatible proxy for one DICOM WSI ZIP archive."""

    is_dicom = True
    color_managed = True

    def __init__(self, file_path: str | Path):
        try:
            import dicomslide
        except ImportError as exc:
            raise RuntimeError("DICOM slides require the dicomslide package") from exc

        float_started = time.perf_counter()
        self.file_path = str(Path(file_path).resolve())
        self._lock = threading.RLock()
        self._closed = False
        self._extracted_path = _extract_archive(self.file_path)
        float_extracted = time.perf_counter()
        self._client = _CompatibleDICOMFileClient.create(self._extracted_path)
        float_indexed = time.perf_counter()
        list_metadata, tuple_group = _load_wsi_metadata(self._extracted_path)
        float_metadata = time.perf_counter()
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Invalid value for VR DT:.*")
            self._slide = dicomslide.Slide(
                self._client,
                list_metadata,
                max_frame_cache_size=max(1, int(settings.DICOM_FRAME_CACHE_SIZE)),
                pyramid_tolerance=float(settings.DICOM_PYRAMID_TOLERANCE_MM),
            )
        self._wrapped = dicomslide.OpenSlide(self._slide)
        float_pyramid = time.perf_counter()

        self.dimensions = tuple(int(v) for v in self._wrapped.dimensions)
        self.level_dimensions = [
            tuple(int(v) for v in item) for item in self._wrapped.level_dimensions
        ]
        self.level_downsamples = [float(v) for v in self._wrapped.level_downsamples]
        self.level_count = len(self.level_dimensions)
        self.properties = dict(self._wrapped.properties)
        stat = Path(self.file_path).stat()
        str_stable_hash = hashlib.sha1(
            f"{Path(self.file_path).name}:{stat.st_size}:{stat.st_mtime_ns}".encode("utf-8")
        ).hexdigest()
        self.properties["openslide.quickhash-1"] = str_stable_hash
        self.properties["mediauto.dicom.container-id"] = tuple_group[0]
        self.properties["mediauto.dicom.frame-of-reference-uid"] = tuple_group[1]
        self.properties["mediauto.source-format"] = "DICOM WSI ZIP"
        self.vendor = self.properties.get("openslide.vendor", "DICOM")
        try:
            self.mpp = float(self.properties.get("openslide.mpp-x", 0.0) or 0.0)
        except (TypeError, ValueError):
            self.mpp = 0.0
        self.color_profile = None  # dicomslide already applies the DICOM ICC profile
        self.data_envelope_rectangles: list[tuple[int, int, int, int]] = []
        print(
            f"[dicom] opened {Path(self.file_path).name} "
            f"total={float_pyramid - float_started:.3f}s "
            f"extract={float_extracted - float_started:.3f}s "
            f"index={float_indexed - float_extracted:.3f}s "
            f"metadata={float_metadata - float_indexed:.3f}s "
            f"pyramid={float_pyramid - float_metadata:.3f}s"
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("DICOM slide is closed")

    @property
    def associated_images(self):
        with self._lock:
            self._ensure_open()
            return self._wrapped.associated_images

    def read_region(self, location, level, size):
        with self._lock:
            self._ensure_open()
            return self._wrapped.read_region(location, int(level), size)

    def get_thumbnail(self, size):
        with self._lock:
            self._ensure_open()
            return self._wrapped.get_thumbnail(size)

    def get_best_level_for_downsample(self, downsample: float) -> int:
        self._ensure_open()
        return int(self._wrapped.get_best_level_for_downsample(float(downsample)))

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                self._wrapped.close()
            finally:
                # dicomslide's OpenSlide.close() is API-compatible but a no-op.
                # Drop the slide references so cached decoded frames can be
                # reclaimed as soon as SlideManager evicts this proxy.
                self._wrapped = None
                self._slide = None
                self._client = None

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback):
        self.close()
