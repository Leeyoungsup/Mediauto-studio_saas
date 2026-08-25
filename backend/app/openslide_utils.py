"""OpenSlide helpers."""

import contextlib
import os
import threading

import openslide

from app.dicom_slide import DicomSlideProxy, is_dicom_slide_archive
from app.raster_slide import RasterSlideProxy, is_fixed_magnification_raster


_stderr_redirect_lock = threading.Lock()


@contextlib.contextmanager
def suppress_native_stderr():
    """Temporarily silence C-library stderr output.

    libtiff can print benign metadata warnings directly to file descriptor 2,
    bypassing Python's warnings/logging system.  Use this only around short
    OpenSlide operations that may emit those noisy warnings.
    """
    with _stderr_redirect_lock:
        saved_fd = None
        devnull_fd = None
        try:
            saved_fd = os.dup(2)
            devnull_fd = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull_fd, 2)
            yield
        finally:
            if saved_fd is not None:
                try:
                    os.dup2(saved_fd, 2)
                except Exception:
                    pass
            if devnull_fd is not None:
                try:
                    os.close(devnull_fd)
                except Exception:
                    pass
            if saved_fd is not None:
                try:
                    os.close(saved_fd)
                except Exception:
                    pass


def open_slide_silently(file_path: str):
    """Open an OpenSlide file while suppressing benign libtiff stderr noise."""
    if is_dicom_slide_archive(file_path):
        return DicomSlideProxy(file_path)
    if is_fixed_magnification_raster(file_path):
        return RasterSlideProxy(file_path)
    with suppress_native_stderr():
        return openslide.OpenSlide(str(file_path))
