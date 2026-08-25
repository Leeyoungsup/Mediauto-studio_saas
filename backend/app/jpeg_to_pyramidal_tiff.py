"""Convert uploaded JPEG images to OpenSlide-readable pyramidal BigTIFF."""

from __future__ import annotations

import os
import time
from pathlib import Path


JPEG_FIXED_OBJECTIVE_POWER = 20.0
JPEG_FIXED_MPP = 0.5


def converted_tiff_path(jpeg_path: str | Path) -> Path:
    """Return the stored TIFF path used for an uploaded JPG/JPEG file."""

    path_source = Path(jpeg_path)
    return path_source.with_suffix(".tiff")


def converted_tiff_filename(filename: str) -> str:
    path_name = Path(filename)
    if path_name.suffix.lower() not in {".jpg", ".jpeg"}:
        return path_name.name
    return path_name.with_suffix(".tiff").name


def convert_jpeg_to_pyramidal_tiff(
    source_path: str | Path,
    destination_path: str | Path | None = None,
    *,
    max_pixels: int = 1_000_000_000,
    jpeg_quality: int = 90,
) -> Path:
    """Stream a JPEG into a tiled, pyramidal BigTIFF and atomically publish it.

    libvips decodes the source sequentially, avoiding Pillow's full-image
    allocation and decompression-bomb limit.  A finite pixel cap remains in
    place so a maliciously crafted JPEG cannot request an unbounded image.
    """

    try:
        import pyvips
    except ImportError as exc:
        raise RuntimeError(
            "JPG conversion requires pyvips and the system libvips library"
        ) from exc

    path_source = Path(source_path)
    if path_source.suffix.lower() not in {".jpg", ".jpeg"}:
        raise ValueError(f"Not a JPG/JPEG file: {path_source.name}")
    if not path_source.is_file():
        raise FileNotFoundError(path_source)

    path_destination = (
        Path(destination_path) if destination_path is not None
        else converted_tiff_path(path_source)
    )
    if path_destination.exists():
        raise FileExistsError(path_destination)
    path_destination.parent.mkdir(parents=True, exist_ok=True)
    path_temp = path_destination.with_name(
        f".{path_destination.name}.{os.getpid()}.{time.time_ns()}.converting"
    )

    obj_image = None
    try:
        obj_image = pyvips.Image.new_from_file(str(path_source), access="sequential")
        int_width = int(obj_image.width)
        int_height = int(obj_image.height)
        int_pixels = int_width * int_height
        if int_width <= 0 or int_height <= 0:
            raise ValueError("JPEG image has invalid dimensions")
        if int_pixels > max(1, int(max_pixels)):
            raise ValueError(
                f"JPEG image is too large: {int_pixels:,} pixels "
                f"(limit {int(max_pixels):,})"
            )

        # Honor EXIF orientation before coordinates become permanent in the
        # TIFF pyramid, then normalize grayscale/CMYK JPEGs to display RGB.
        try:
            obj_image = obj_image.autorot()
        except Exception:
            pass
        if obj_image.bands != 3 or str(obj_image.interpretation).lower() != "srgb":
            try:
                obj_image = obj_image.colourspace("srgb")
            except Exception:
                if obj_image.bands == 1:
                    obj_image = obj_image.bandjoin([obj_image, obj_image])
                elif obj_image.bands > 3:
                    obj_image = obj_image.extract_band(0, n=3)

        obj_image = obj_image.copy()
        obj_image.set_type(
            pyvips.GValue.gstr_type,
            "image-description",
            "MeDIAuto JPEG conversion;objective-power=20;mpp=0.5",
        )
        obj_image.tiffsave(
            str(path_temp),
            tile=True,
            tile_width=512,
            tile_height=512,
            pyramid=True,
            bigtiff=True,
            compression="jpeg",
            Q=max(50, min(100, int(jpeg_quality))),
            xres=1000.0 / JPEG_FIXED_MPP,
            yres=1000.0 / JPEG_FIXED_MPP,
            resunit="cm",
            properties=True,
        )
        path_temp.replace(path_destination)
        return path_destination
    finally:
        obj_image = None
        try:
            if path_temp.exists():
                path_temp.unlink()
        except OSError:
            pass

