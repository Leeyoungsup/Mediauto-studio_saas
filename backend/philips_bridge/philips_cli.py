#!/usr/bin/env python
"""Python 3.7 side CLI for Philips iSyntax access.

This file must run in an environment where the Philips Pathology SDK and
OpenPhi dependencies are importable. It intentionally prints JSON to stdout
for structured commands and writes image payloads to output files.
"""

import argparse
import json
import os
import site
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
OPENPHI_ROOT = BACKEND_DIR / "scripts" / "openphi-master"
if str(OPENPHI_ROOT) not in sys.path:
    sys.path.insert(0, str(OPENPHI_ROOT))


def _prime_sdk_dll_paths():
    """Make Philips SDK sibling package DLLs visible before importing .pyd files."""
    package_names = [
        "pixelengine",
        "softwarerenderbackend",
        "softwarerendercontext",
        "eglrendercontext",
        "gles2renderbackend",
        "gles3renderbackend",
    ]
    candidates = []
    try:
        site_roots = list(site.getsitepackages())
    except Exception:
        site_roots = []
    try:
        user_site = site.getusersitepackages()
        if user_site:
            site_roots.append(user_site)
    except Exception:
        pass
    for root in site_roots:
        for name in package_names:
            path_obj = Path(root) / name
            if path_obj.exists():
                candidates.append(str(path_obj))
    conda_prefix = os.environ.get("CONDA_PREFIX", "")
    if conda_prefix:
        candidates.append(str(Path(conda_prefix) / "Library" / "bin"))
        candidates.append(str(Path(conda_prefix) / "DLLs"))
    current_path = os.environ.get("PATH", "")
    prefix = os.pathsep.join([p for p in candidates if p and p not in current_path])
    if prefix:
        os.environ["PATH"] = prefix + os.pathsep + current_path


_prime_sdk_dll_paths()


def _json_default(value):
    try:
        import numpy as np

        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            return float(value)
    except Exception:
        pass
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _load_openphi():
    from openphi import OpenPhi

    return OpenPhi


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, default=_json_default), flush=True)


def cmd_smoke(_args) -> int:
    import pixelengine
    import softwarerenderbackend
    import softwarerendercontext

    OpenPhi = _load_openphi()
    _emit({
        "ok": True,
        "modules": {
            "pixelengine": getattr(pixelengine, "__file__", ""),
            "softwarerenderbackend": getattr(softwarerenderbackend, "__file__", ""),
            "softwarerendercontext": getattr(softwarerendercontext, "__file__", ""),
            "openphi": getattr(OpenPhi, "__module__", "openphi"),
        },
    })
    return 0


def cmd_info(args) -> int:
    OpenPhi = _load_openphi()
    slide = OpenPhi(args.slide, view=args.view)
    try:
        _emit({
            "ok": True,
            "dimensions": list(slide.dimensions),
            "level_count": int(slide.level_count),
            "level_dimensions": [list(item) for item in slide.level_dimensions],
            "level_downsamples": [float(item) for item in slide.level_downsamples],
            "properties": dict(slide.properties),
            "associated_images": {
                name: list(image.size)
                for name, image in getattr(slide, "associated_images", {}).items()
            },
        })
    finally:
        slide.close()
    return 0


def cmd_thumbnail(args) -> int:
    OpenPhi = _load_openphi()
    slide = OpenPhi(args.slide, view=args.view)
    try:
        image = slide.get_thumbnail((args.width, args.height))
        image.save(args.output)
        _emit({"ok": True, "output": str(Path(args.output).resolve()), "size": list(image.size), "mode": image.mode})
    finally:
        slide.close()
    return 0


def cmd_region(args) -> int:
    OpenPhi = _load_openphi()
    slide = OpenPhi(args.slide, view=args.view)
    try:
        image = slide.read_region((args.x, args.y), args.level, (args.width, args.height))
        image.save(args.output)
        _emit({"ok": True, "output": str(Path(args.output).resolve()), "size": list(image.size), "mode": image.mode})
    finally:
        slide.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Philips iSyntax bridge CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    smoke = sub.add_parser("smoke")
    smoke.set_defaults(func=cmd_smoke)

    info = sub.add_parser("info")
    info.add_argument("slide")
    info.add_argument("--view", choices=["source", "display"], default="source")
    info.set_defaults(func=cmd_info)

    thumb = sub.add_parser("thumbnail")
    thumb.add_argument("slide")
    thumb.add_argument("output")
    thumb.add_argument("--width", type=int, required=True)
    thumb.add_argument("--height", type=int, required=True)
    thumb.add_argument("--view", choices=["source", "display"], default="source")
    thumb.set_defaults(func=cmd_thumbnail)

    region = sub.add_parser("region")
    region.add_argument("slide")
    region.add_argument("output")
    region.add_argument("--x", type=int, required=True)
    region.add_argument("--y", type=int, required=True)
    region.add_argument("--level", type=int, required=True)
    region.add_argument("--width", type=int, required=True)
    region.add_argument("--height", type=int, required=True)
    region.add_argument("--view", choices=["source", "display"], default="source")
    region.set_defaults(func=cmd_region)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "type": type(exc).__name__}), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
