"""Python 3.12 proxy for Philips iSyntax slides.

The Philips SDK bundled with this project is compiled for Python 3.7, so the
main FastAPI process cannot import it directly. This proxy delegates metadata
and image extraction to ``backend/philips_bridge/philips_cli.py`` running in a
separate Python 3.7 environment.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import mmap
import os
import queue
import subprocess
import tempfile
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any

from PIL import Image


logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[1]
PHILIPS_CLI = BACKEND_DIR / "philips_bridge" / "philips_cli.py"
PHILIPS_SERVER = BACKEND_DIR / "philips_bridge" / "philips_server.py"
PHILIPS_CONDA_ENV = os.environ.get("PHILIPS_CONDA_ENV", "philips-sdk-py38")
PHILIPS_PYTHON = os.environ.get("PHILIPS_PYTHON", "").strip()
PHILIPS_VIEW = os.environ.get("PHILIPS_VIEW", "display").strip() or "display"
PHILIPS_TIMEOUT_SECONDS = int(os.environ.get("PHILIPS_TIMEOUT_SECONDS", "120"))
PHILIPS_BRIDGE_MODE = os.environ.get("PHILIPS_BRIDGE_MODE", "auto").strip().lower() or "auto"
PHILIPS_BYTES_MAX_PIXELS = int(os.environ.get("PHILIPS_BYTES_MAX_PIXELS", str(2048 * 2048)))
PHILIPS_SHARED_MEMORY = os.environ.get("PHILIPS_SHARED_MEMORY", "1").strip().lower() not in {"0", "false", "no"}
PHILIPS_RAW_FILE = os.environ.get("PHILIPS_RAW_FILE", "1").strip().lower() not in {"0", "false", "no"}
PHILIPS_START_TIMEOUT_SECONDS = int(os.environ.get("PHILIPS_START_TIMEOUT_SECONDS", "30"))
PHILIPS_STOP_GRACE_SECONDS = float(os.environ.get("PHILIPS_STOP_GRACE_SECONDS", "3"))
PHILIPS_STDERR_TAIL_LINES = int(os.environ.get("PHILIPS_STDERR_TAIL_LINES", "80"))
PHILIPS_LOG_STDERR = os.environ.get("PHILIPS_LOG_STDERR", "1").strip().lower() not in {"0", "false", "no"}


def is_philips_isyntax(file_path: str | Path) -> bool:
    return Path(file_path).suffix.lower() in {".isyntax", ".i2syntax"}


def _find_conda_env_python() -> str:
    candidates: list[Path] = []
    conda_prefix = os.environ.get("CONDA_PREFIX", "").strip()
    if conda_prefix:
        candidates.append(Path(conda_prefix).parent / PHILIPS_CONDA_ENV / "bin" / "python")
        candidates.append(Path(conda_prefix).parent / PHILIPS_CONDA_ENV / "python.exe")
    home = Path.home()
    candidates.append(home / "anaconda3" / "envs" / PHILIPS_CONDA_ENV / "bin" / "python")
    candidates.append(home / "miniconda3" / "envs" / PHILIPS_CONDA_ENV / "bin" / "python")
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


def _server_command() -> list[str]:
    cmd = _base_command()
    cmd[-1] = str(PHILIPS_SERVER)
    return cmd


def _subprocess_env(cmd: list[str]) -> dict[str, str]:
    env = os.environ.copy()
    path_python = Path(cmd[0])
    if path_python.name.lower().startswith("python") and path_python.parent.name == "bin":
        path_env = path_python.parent.parent
        env["CONDA_PREFIX"] = str(path_env)
        env["LD_LIBRARY_PATH"] = os.pathsep.join([
            str(path_env / "lib"),
            env.get("LD_LIBRARY_PATH", ""),
        ])
    elif path_python.name.lower() == "python.exe" and path_python.parent.name.lower() == PHILIPS_CONDA_ENV.lower():
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


class _PersistentPhilipsBridge:
    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._lock = threading.RLock()
        self._stdout_queue: queue.Queue[dict[str, Any] | str] = queue.Queue()
        self._stderr_tail: deque[str] = deque(maxlen=max(1, PHILIPS_STDERR_TAIL_LINES))

    def request(self, payload: dict[str, Any], timeout: int | None = None) -> dict[str, Any]:
        with self._lock:
            proc = self._ensure_started(timeout=timeout)
            try:
                assert proc.stdin is not None
                assert proc.stdout is not None
                proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
                proc.stdin.flush()
                command = str(payload.get("command") or "unknown")
                data = self._read_json_response(proc, timeout or PHILIPS_TIMEOUT_SECONDS, command)
                if not data.get("ok"):
                    raise RuntimeError(f"Philips bridge error: {data}")
                return data
            except TimeoutError:
                self._stop_locked(force=True)
                raise
            except Exception:
                if proc.poll() is not None:
                    self._stop_locked()
                raise

    def close_slide(self, slide_path: str, view: str) -> None:
        try:
            self.request({"command": "close", "slide": slide_path, "view": view}, timeout=10)
        except Exception:
            pass

    def _ensure_started(self, timeout: int | None = None) -> subprocess.Popen:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        cmd = _server_command()
        self._stdout_queue = queue.Queue()
        self._stderr_tail.clear()
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(BACKEND_DIR),
            env=_subprocess_env(cmd),
            bufsize=1,
        )
        self._proc = proc
        self._start_pipe_readers(proc)
        try:
            start_timeout = min(float(timeout or PHILIPS_START_TIMEOUT_SECONDS), float(PHILIPS_START_TIMEOUT_SECONDS))
            ready = self._wait_for_json(proc, start_timeout, "startup")
        except TimeoutError:
            self._stop_locked()
            raise RuntimeError(
                "Philips persistent bridge startup timed out. "
                f"stderr tail: {self._stderr_detail()}"
            )
        if not ready.get("ok") or not ready.get("ready"):
            self._stop_locked()
            raise RuntimeError(f"Philips persistent bridge bad ready response: {ready}")
        logger.info("Philips persistent bridge started: %s", " ".join(cmd))
        return proc

    def _start_pipe_readers(self, proc: subprocess.Popen) -> None:
        def _read_stdout() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    self._stdout_queue.put(line)
                    continue
                if isinstance(data, dict):
                    self._stdout_queue.put(data)

        def _read_stderr() -> None:
            assert proc.stderr is not None
            for line in proc.stderr:
                line = line.rstrip()
                if not line:
                    continue
                self._stderr_tail.append(line)
                if PHILIPS_LOG_STDERR:
                    logger.warning("Philips bridge stderr: %s", line)

        threading.Thread(target=_read_stdout, name="philips-stdout-reader", daemon=True).start()
        threading.Thread(target=_read_stderr, name="philips-stderr-reader", daemon=True).start()

    def _read_json_response(self, proc: subprocess.Popen, timeout: int, command: str) -> dict[str, Any]:
        return self._wait_for_json(proc, timeout, command)

    def _wait_for_json(self, proc: subprocess.Popen, timeout: int | float, context: str) -> dict[str, Any]:
        deadline = time.monotonic() + max(0.1, float(timeout))
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"Philips persistent bridge timed out during {context} "
                    f"after {timeout}s. stderr tail: {self._stderr_detail()}"
                )
            if proc.poll() is not None:
                self._stop_locked()
                raise RuntimeError(
                    f"Philips persistent bridge stopped during {context}. "
                    f"stderr tail: {self._stderr_detail()}"
                )
            try:
                item = self._stdout_queue.get(timeout=min(0.25, remaining))
            except queue.Empty:
                continue
            if isinstance(item, dict):
                return item

    def _stderr_detail(self) -> str:
        detail = "\n".join(self._stderr_tail)
        return detail.strip() or "(empty)"

    def _stop_locked(self, force: bool = False) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if not force and proc.poll() is None and proc.stdin is not None:
                proc.stdin.write(json.dumps({"command": "shutdown"}) + "\n")
                proc.stdin.flush()
        except Exception:
            pass
        try:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=PHILIPS_STOP_GRACE_SECONDS)
        except Exception:
            try:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=PHILIPS_STOP_GRACE_SECONDS)
            except Exception:
                pass
        logger.info("Philips persistent bridge stopped")


_PERSISTENT_BRIDGES: dict[str, _PersistentPhilipsBridge] = {}
_PERSISTENT_BRIDGES_LOCK = threading.Lock()


def _bridge_key_for_current_thread() -> str:
    name = threading.current_thread().name.lower()
    if name.startswith("viewer"):
        return f"viewer:{name}"
    if name.startswith("tile_worker"):
        return "tile"
    if name.startswith("ai_worker") or name.startswith("cell_patch"):
        return "ai"
    return "default"


def _get_persistent_bridge() -> _PersistentPhilipsBridge:
    key = _bridge_key_for_current_thread()
    with _PERSISTENT_BRIDGES_LOCK:
        bridge = _PERSISTENT_BRIDGES.get(key)
        if bridge is None:
            bridge = _PersistentPhilipsBridge()
            _PERSISTENT_BRIDGES[key] = bridge
        return bridge


def _close_slide_on_persistent_bridges(slide_path: str, view: str) -> None:
    with _PERSISTENT_BRIDGES_LOCK:
        bridges = list(_PERSISTENT_BRIDGES.values())
    for bridge in bridges:
        bridge.close_slide(slide_path, view)


def shutdown_persistent_bridges() -> None:
    """Stop every persistent Philips bridge process owned by this FastAPI process."""
    with _PERSISTENT_BRIDGES_LOCK:
        bridges = list(_PERSISTENT_BRIDGES.values())
        _PERSISTENT_BRIDGES.clear()
    for bridge in bridges:
        with bridge._lock:
            bridge._stop_locked()


def _run_cli(args: list[str], timeout: int | None = None) -> dict[str, Any]:
    cmd = _base_command() + args
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout or PHILIPS_TIMEOUT_SECONDS,
            cwd=str(BACKEND_DIR),
            env=_subprocess_env(cmd),
        )
    except subprocess.TimeoutExpired as exc:
        detail = (exc.stderr or exc.stdout or "")
        raise TimeoutError(
            f"Philips CLI bridge timed out after {timeout or PHILIPS_TIMEOUT_SECONDS}s: "
            f"{str(detail)[:1000]}"
        ) from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"Philips bridge failed ({proc.returncode}): {detail}")
    if proc.stderr and PHILIPS_LOG_STDERR:
        logger.warning("Philips CLI stderr: %s", proc.stderr.strip()[:2000])
    data = _extract_json(proc.stdout)
    if not data.get("ok"):
        raise RuntimeError(f"Philips bridge error: {data}")
    return data


def _request_persistent(payload: dict[str, Any], timeout: int | None = None) -> dict[str, Any]:
    return _get_persistent_bridge().request(payload, timeout=timeout or PHILIPS_TIMEOUT_SECONDS)


def _run_bridge(payload: dict[str, Any], cli_args: list[str], timeout: int | None = None) -> dict[str, Any]:
    if PHILIPS_BRIDGE_MODE == "cli":
        return _run_cli(cli_args, timeout=timeout)
    try:
        return _request_persistent(payload, timeout=timeout)
    except Exception:
        if PHILIPS_BRIDGE_MODE == "persistent":
            raise
        return _run_cli(cli_args, timeout=timeout)


def _image_from_bridge_response(
    data: dict[str, Any],
    fallback_path: str,
    shm_map: mmap.mmap | None = None,
) -> Image.Image:
    if data.get("encoding") == "raw_rgba_shm" and shm_map is not None:
        size = tuple(int(v) for v in data.get("size", (0, 0)))
        byte_count = int(data.get("byte_count") or 0)
        if size[0] > 0 and size[1] > 0 and byte_count > 0:
            shm_map.seek(0)
            raw = shm_map.read(byte_count)
            return Image.frombytes("RGBA", size, raw)
    if data.get("encoding") == "raw_rgba_file":
        size = tuple(int(v) for v in data.get("size", (0, 0)))
        byte_count = int(data.get("byte_count") or 0)
        if size[0] > 0 and size[1] > 0 and byte_count > 0:
            with open(fallback_path, "rb") as fh:
                raw = fh.read(byte_count)
            return Image.frombytes("RGBA", size, raw)
    image_b64 = data.get("image_b64")
    if image_b64:
        raw = base64.b64decode(str(image_b64))
        with Image.open(io.BytesIO(raw)) as image:
            return image.copy()
    with Image.open(fallback_path) as image:
        return image.copy()


def _can_use_shared_memory(width: int, height: int) -> bool:
    return (
        os.name == "nt"
        and PHILIPS_SHARED_MEMORY
        and PHILIPS_BRIDGE_MODE != "cli"
        and width > 0
        and height > 0
        and width * height > PHILIPS_BYTES_MAX_PIXELS
    )


def smoke_test() -> dict[str, Any]:
    return _run_bridge({"command": "smoke"}, ["smoke"], timeout=30)


class PhilipsSlideProxy:
    """OpenSlide-like proxy used by SlideInfo for Philips iSyntax files."""

    def __init__(self, file_path: str):
        self.file_path = str(Path(file_path).resolve())
        self._closed = False
        data = _run_bridge(
            {"command": "info", "slide": self.file_path, "view": PHILIPS_VIEW},
            ["info", self.file_path, "--view", PHILIPS_VIEW],
        )
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
            data = _run_bridge(
                {
                    "command": "thumbnail",
                    "slide": self.file_path,
                    "width": width,
                    "height": height,
                    "view": PHILIPS_VIEW,
                    "return_image": True,
                },
                [
                    "thumbnail",
                    self.file_path,
                    out_path,
                    "--width",
                    str(width),
                    "--height",
                    str(height),
                    "--view",
                    PHILIPS_VIEW,
                ],
            )
            return _image_from_bridge_response(data, out_path)
        finally:
            try:
                os.unlink(out_path)
            except OSError:
                pass

    def read_region(self, location: tuple[int, int], level: int, size: tuple[int, int]) -> Image.Image:
        self._ensure_open()
        x, y = int(location[0]), int(location[1])
        width, height = int(size[0]), int(size[1])
        use_raw_file = PHILIPS_RAW_FILE and PHILIPS_BRIDGE_MODE != "cli"
        return_image = (
            not use_raw_file
            and width * height <= PHILIPS_BYTES_MAX_PIXELS
            and PHILIPS_BRIDGE_MODE != "cli"
        )
        use_shm = _can_use_shared_memory(width, height)
        shm_map: mmap.mmap | None = None
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            out_path = tmp.name
        try:
            payload = {
                "command": "region",
                "slide": self.file_path,
                "x": x,
                "y": y,
                "level": int(level),
                "width": width,
                "height": height,
                "view": PHILIPS_VIEW,
                "return_image": return_image,
            }
            if use_raw_file:
                payload["raw_file"] = True
                payload["output"] = out_path
            if use_shm:
                shm_name = f"MediautoPhilips_{uuid.uuid4().hex}"
                shm_size = width * height * 4
                shm_map = mmap.mmap(-1, shm_size, tagname=shm_name, access=mmap.ACCESS_WRITE)
                payload["shm_name"] = shm_name
                payload["shm_size"] = shm_size
            if not return_image and not use_shm and not use_raw_file:
                payload["output"] = out_path
            data = _run_bridge(
                payload,
                [
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
                ],
            )
            return _image_from_bridge_response(data, out_path, shm_map=shm_map)
        finally:
            if shm_map is not None:
                try:
                    shm_map.close()
                except OSError:
                    pass
            try:
                os.unlink(out_path)
            except OSError:
                pass

    def get_best_level_for_downsample(self, downsample: float) -> int:
        self._ensure_open()
        try:
            target = float(downsample)
        except Exception:
            target = 1.0
        best_level = 0
        best_delta = float("inf")
        for idx, value in enumerate(self.level_downsamples):
            delta = abs(float(value) - target)
            if delta < best_delta:
                best_delta = delta
                best_level = idx
        return best_level

    def close(self) -> None:
        if not self._closed and PHILIPS_BRIDGE_MODE != "cli":
            _close_slide_on_persistent_bridges(self.file_path, PHILIPS_VIEW)
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("PhilipsSlideProxy is closed")
