#!/usr/bin/env python
"""Persistent Python 3.7 side server for Philips iSyntax access.

Protocol:
  stdin  : one JSON object per line
  stdout : one JSON object per line

Image commands can either write to caller-provided output paths or return PNG
bytes as base64. Large image callers should keep using output paths to avoid
huge JSON lines over stdout.
"""

import json
import base64
import io
import os
import sys
import mmap
import time
from pathlib import Path

from philips_cli import _json_default, _load_openphi, _prime_sdk_dll_paths


_prime_sdk_dll_paths()
_SLIDES = {}
_BOOL_LOG_COMMANDS = os.environ.get("PHILIPS_SERVER_LOG_COMMANDS", "0").lower() in ("1", "true", "yes")


def _log(message):
    sys.stderr.write("[philips_server] %s\n" % message)
    sys.stderr.flush()


def _emit(payload):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, default=_json_default) + "\n")
    sys.stdout.flush()


def _get_slide(path, view):
    key = (str(Path(path).resolve()), view)
    slide = _SLIDES.get(key)
    if slide is None:
        OpenPhi = _load_openphi()
        slide = OpenPhi(str(path), view=view)
        _SLIDES[key] = slide
    return slide


def _info(req):
    slide = _get_slide(req["slide"], req.get("view", "display"))
    data_envelope_rectangles = []
    try:
        data_envelope_rectangles = [
            [int(value) for value in rect]
            for rect in slide.view_wsi.data_envelopes(0).as_rectangles()
        ]
    except Exception:
        data_envelope_rectangles = []
    return {
        "ok": True,
        "dimensions": list(slide.dimensions),
        "level_count": int(slide.level_count),
        "level_dimensions": [list(item) for item in slide.level_dimensions],
        "level_downsamples": [float(item) for item in slide.level_downsamples],
        "properties": dict(slide.properties),
        "data_envelope_rectangles": data_envelope_rectangles,
        "associated_images": {
            name: list(image.size)
            for name, image in getattr(slide, "associated_images", {}).items()
        },
    }


def _thumbnail(req):
    slide = _get_slide(req["slide"], req.get("view", "display"))
    image = slide.get_thumbnail((int(req["width"]), int(req["height"])))
    output = req.get("output")
    if output:
        image.save(output)
    data = {
        "ok": True,
        "output": str(Path(output).resolve()) if output else "",
        "size": list(image.size),
        "mode": image.mode,
    }
    if bool(req.get("return_image")) or not output:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        data["encoding"] = "png_base64"
        data["image_b64"] = base64.b64encode(buf.getvalue()).decode("ascii")
    return data


def _write_shared_image(req, image):
    shm_name = req.get("shm_name")
    shm_size = int(req.get("shm_size") or 0)
    if not shm_name or shm_size <= 0:
        return None
    image_rgba = image.convert("RGBA")
    raw = image_rgba.tobytes()
    if len(raw) > shm_size:
        raise ValueError("shared memory buffer too small")
    mm = mmap.mmap(-1, shm_size, tagname=str(shm_name), access=mmap.ACCESS_WRITE)
    try:
        mm.seek(0)
        mm.write(raw)
    finally:
        mm.close()
    return {
        "encoding": "raw_rgba_shm",
        "shm_name": str(shm_name),
        "byte_count": len(raw),
        "size": list(image_rgba.size),
        "mode": "RGBA",
    }


def _region(req):
    slide = _get_slide(req["slide"], req.get("view", "display"))
    image = slide.read_region(
        (int(req["x"]), int(req["y"])),
        int(req["level"]),
        (int(req["width"]), int(req["height"])),
    )
    shm_data = _write_shared_image(req, image)
    output = req.get("output")
    if output:
        image.save(output)
    data = {
        "ok": True,
        "output": str(Path(output).resolve()) if output else "",
        "size": list(image.size),
        "mode": image.mode,
    }
    if shm_data:
        data.update(shm_data)
        return data
    if bool(req.get("return_image")) or not output:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        data["encoding"] = "png_base64"
        data["image_b64"] = base64.b64encode(buf.getvalue()).decode("ascii")
    return data


def _smoke(_req):
    import pixelengine
    import softwarerenderbackend
    import softwarerendercontext

    OpenPhi = _load_openphi()
    return {
        "ok": True,
        "modules": {
            "pixelengine": getattr(pixelengine, "__file__", ""),
            "softwarerenderbackend": getattr(softwarerenderbackend, "__file__", ""),
            "softwarerendercontext": getattr(softwarerendercontext, "__file__", ""),
            "openphi": getattr(OpenPhi, "__module__", "openphi"),
        },
    }


def _close(req):
    path = req.get("slide")
    view = req.get("view")
    keys = list(_SLIDES)
    for key in keys:
        if path and str(Path(path).resolve()) != key[0]:
            continue
        if view and view != key[1]:
            continue
        slide = _SLIDES.pop(key, None)
        if slide is not None:
            try:
                slide.close()
            except Exception:
                pass
    return {"ok": True}


def _handle(req):
    command = req.get("command")
    start = time.time()
    if _BOOL_LOG_COMMANDS:
        _log("command start: %s" % command)
    if command == "smoke":
        resp = _smoke(req)
    elif command == "info":
        resp = _info(req)
    elif command == "thumbnail":
        resp = _thumbnail(req)
    elif command == "region":
        resp = _region(req)
    elif command == "close":
        resp = _close(req)
    elif command == "shutdown":
        _close({})
        resp = {"ok": True, "shutdown": True}
    else:
        resp = {"ok": False, "error": "unknown command: %s" % command, "type": "ValueError"}
    if _BOOL_LOG_COMMANDS:
        _log("command end: %s %.3fs ok=%s" % (command, time.time() - start, resp.get("ok")))
    return resp


def main():
    _emit({"ok": True, "ready": True})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = _handle(req)
        except Exception as exc:
            resp = {"ok": False, "error": str(exc), "type": type(exc).__name__}
            _log("command error: %s: %s" % (type(exc).__name__, exc))
        _emit(resp)
        if resp.get("shutdown"):
            break
    _close({})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
