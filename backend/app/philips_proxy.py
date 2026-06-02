"""Python 3.12 proxy for Philips iSyntax slides.

The Philips SDK bundled with this project is compiled for Python 3.7, so the
main FastAPI process cannot import it directly. This proxy delegates metadata
and image extraction to ``backend/philips_bridge/philips_cli.py`` running in a
separate Python 3.7 environment.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image


BACKEND_DIR = Path(__file__).resolve().parents[1]
PHILIPS_CLI = BACKEND_DIR / "philips_bridge" / "philips_cli.py"
PHILIPS_CONDA_ENV = os.environ.get("PHILIPS_CONDA_ENV", "philips-sdk-py37")
PHILIPS_PYTHON = os.environ.get("PHILIPS_PYTHON", "").strip()
PHILIPS_VIEW = os.environ.get("PHILIPS_VIEW", "display").strip() or "display"
PHILIPS_TIMEOUT_SECONDS = int(os.environ.get("PHILIPS_TIMEOUT_SECONDS", "120"))


def is_philips_isyntax(file_path: str | Path) -> bool:
    return Path(file_path).suffix.lower() in {".isyntax", ".i2syntax"}


def _find_conda_env_python() -> str:
    candidates: list[Path] = []
    conda_prefix = os.environ.get("CONDA_PREFIX", "").strip()
    if conda_prefix:
        candidates.append(Path(conda_prefix).parent / PHILIPS_CONDA_ENV / "python.exe")
    user_profile = os.environ.get("USERPROFILE", "").strip()
    if user_profile:
        candidates.append(Path(user_profile) / ".conda" / "envs" / PHILIPS_CONDA_ENV / "python.exe")
    candidates.append(Path("C:/ProgramData/anaconda3/envs") / PHILIPS_CONDA_ENV / "python.exe")
    candidates.append(Path("C:/ProgramData/miniconda3/envs") / PHILIPS_CONDA_ENV / "python.exe")
    for path_python in candidates:
        if path_python.exists():
            return str(path_python)
    return ""


def _base_command() -> list[str]:
    if PHILIPS_PYTHON:
        return [PHILIPS_PYTHON, str(PHILIPS_CLI)]
    str_env_python = _find_conda_env_python()
    if str_env_python:
        return [str_env_python, str(PHILIPS_CLI)]
    return ["conda", "run", "-n", PHILIPS_CONDA_ENV, "python", str(PHILIPS_CLI)]


def _subprocess_env(cmd: list[str]) -> dict[str, str]:
    env = os.environ.copy()
    path_python = Path(cmd[0])
    if path_python.name.lower() == "python.exe" and path_python.parent.name.lower() == PHILIPS_CONDA_ENV.lower():
        path_env = path_python.parent
        env["CONDA_PREFIX"] = str(path_env)
        extra_path = [
            str(path_env),
            str(path_env / "Library" / "bin"),
            str(path_env / "DLLs"),
        ]
        env["PATH"] = os.pathsep.join(extra_path + [env.get("PATH", "")])
    return env


def _extract_json(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    raise RuntimeError(f"Philips bridge returned no JSON: {stdout[:500]}")


def _run_cli(args: list[str], timeout: int | None = None) -> dict[str, Any]:
    cmd = _base_command() + args
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout or PHILIPS_TIMEOUT_SECONDS,
        cwd=str(BACKEND_DIR),
        env=_subprocess_env(cmd),
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"Philips bridge failed ({proc.returncode}): {detail}")
    data = _extract_json(proc.stdout)
    if not data.get("ok"):
        raise RuntimeError(f"Philips bridge error: {data}")
    return data


def smoke_test() -> dict[str, Any]:
    return _run_cli(["smoke"], timeout=30)


class PhilipsSlideProxy:
    """OpenSlide-like proxy used by SlideInfo for Philips iSyntax files."""

    def __init__(self, file_path: str):
        self.file_path = str(file_path)
        self._closed = False
        data = _run_cli(["info", self.file_path, "--view", PHILIPS_VIEW])
        self._metadata = data
        self.dimensions = tuple(int(v) for v in data["dimensions"])
        self.level_count = int(data["level_count"])
        self.level_dimensions = [tuple(int(v) for v in item) for item in data["level_dimensions"]]
        self.level_downsamples = [float(v) for v in data["level_downsamples"]]
        self.data_envelope_rectangles = [
            tuple(int(v) for v in rect)
            for rect in data.get("data_envelope_rectangles", [])
        ]
        self.properties = dict(data.get("properties") or {})
        self.properties.setdefault("openslide.vendor", "PHILIPS")
        self.color_profile = None

    def get_thumbnail(self, size: tuple[int, int]) -> Image.Image:
        self._ensure_open()
        width, height = int(size[0]), int(size[1])
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            out_path = tmp.name
        try:
            _run_cli([
                "thumbnail",
                self.file_path,
                out_path,
                "--width",
                str(width),
                "--height",
                str(height),
                "--view",
                PHILIPS_VIEW,
            ])
            with Image.open(out_path) as image:
                return image.copy()
        finally:
            try:
                os.unlink(out_path)
            except OSError:
                pass

    def read_region(self, location: tuple[int, int], level: int, size: tuple[int, int]) -> Image.Image:
        self._ensure_open()
        x, y = int(location[0]), int(location[1])
        width, height = int(size[0]), int(size[1])
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            out_path = tmp.name
        try:
            _run_cli([
                "region",
                self.file_path,
                out_path,
                "--x",
                str(x),
                "--y",
                str(y),
                "--level",
                str(int(level)),
                "--width",
                str(width),
                "--height",
                str(height),
                "--view",
                PHILIPS_VIEW,
            ])
            with Image.open(out_path) as image:
                return image.copy()
        finally:
            try:
                os.unlink(out_path)
            except OSError:
                pass

    def close(self) -> None:
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("PhilipsSlideProxy is closed")
