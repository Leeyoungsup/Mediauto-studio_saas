#!/usr/bin/env python3
"""Concurrent smoke/load test for the MeDICus Studio SaaS viewer stack.

This is intentionally dependency-free so it can run on the production box
without installing Locust/k6. It exercises the same HTTP surfaces used by the
browser: slide open, media tickets, thumbnails, tiles, cell patch metadata,
labeling assistance, AI task status, and optional AI task starts.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SUPPORTED_EXTENSIONS = {
    ".svs", ".ndpi", ".vms", ".vmu", ".scn", ".mrxs", ".tiff", ".tif",
    ".png", ".jpg", ".jpeg", ".isyntax", ".i2syntax",
}


@dataclass
class Sample:
    name: str
    ok: bool
    elapsed_ms: float
    status: int = 0
    bytes_read: int = 0
    error: str = ""


@dataclass
class SharedState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    samples: list[Sample] = field(default_factory=list)
    ai_tasks: list[str] = field(default_factory=list)

    def add(self, sample: Sample) -> None:
        with self.lock:
            self.samples.append(sample)

    def add_ai_task(self, task_id: str) -> None:
        if not task_id:
            return
        with self.lock:
            self.ai_tasks.append(task_id)


class Client:
    def __init__(self, base_url: str, token: str = "", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_url = self.base_url + "/api"
        self.token = token
        self.timeout = timeout
        self.media_ticket = ""

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "User-Agent": "mediauto-load-test/1.0",
            "X-Requested-With": "XMLHttpRequest",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if extra:
            headers.update(extra)
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        name: str = "",
        expect_json: bool = True,
    ) -> tuple[Any, Sample]:
        url = path if path.startswith("http") else self.api_url + path
        req = urllib.request.Request(url, data=body, method=method, headers=self._headers(headers))
        started = time.perf_counter()
        status = 0
        raw = b""
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status = int(resp.status)
                raw = resp.read()
            elapsed = (time.perf_counter() - started) * 1000
            payload: Any = raw
            if expect_json:
                payload = json.loads(raw.decode("utf-8")) if raw else {}
            return payload, Sample(name or path, 200 <= status < 400, elapsed, status, len(raw))
        except urllib.error.HTTPError as exc:
            raw = exc.read() if hasattr(exc, "read") else b""
            elapsed = (time.perf_counter() - started) * 1000
            return None, Sample(name or path, False, elapsed, exc.code, len(raw), _short_error(raw, exc))
        except Exception as exc:
            elapsed = (time.perf_counter() - started) * 1000
            return None, Sample(name or path, False, elapsed, status, len(raw), str(exc)[:240])

    def login(self, login_id: str, password: str, totp: str = "") -> None:
        body = {
            "str_login_id": login_id,
            "str_password": password,
        }
        if totp:
            body["str_totp_code"] = totp
        payload, sample = self.request(
            "POST",
            "/auth/login",
            body=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            name="auth.login",
        )
        if not sample.ok:
            raise RuntimeError(f"login failed: HTTP {sample.status} {sample.error}")
        if payload.get("bool_mfa_required"):
            raise RuntimeError("login requires MFA; pass --totp")
        self.token = str(payload.get("str_access_token") or "")
        if not self.token:
            raise RuntimeError("login response had no access token")

    def ensure_media_ticket(self) -> str:
        payload, sample = self.request("GET", "/auth/media-ticket", name="auth.media-ticket")
        if not sample.ok:
            raise RuntimeError(f"media-ticket failed: HTTP {sample.status} {sample.error}")
        self.media_ticket = str(payload.get("str_token") or "")
        return self.media_ticket


def _short_error(raw: bytes, exc: Exception) -> str:
    text = raw.decode("utf-8", errors="replace").strip()
    if text:
        return text[:240]
    return str(exc)[:240]


def _multipart(fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = "----mediauto-load-" + uuid.uuid4().hex
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _find_default_slide(repo_root: Path) -> tuple[str, str]:
    upload_dir = repo_root / "backend" / "uploads"
    candidates = [
        path for path in upload_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    if not candidates:
        raise RuntimeError("No supported slide found under backend/uploads; pass --slide and --path")
    candidates.sort(key=lambda p: p.stat().st_size if p.exists() else 0, reverse=True)
    path = candidates[0]
    rel_dir = path.parent.relative_to(upload_dir)
    rel_path = "" if str(rel_dir) == "." else str(rel_dir)
    return path.name, rel_path


def _tile_coords(slide_info: dict[str, Any], rng: random.Random, count: int) -> list[tuple[int, int, int]]:
    dims = slide_info.get("stage_dimensions") or []
    coords: list[tuple[int, int, int]] = []
    for level in (2, 1, 0):
        if level < len(dims) and dims[level]:
            width, height = int(dims[level][0]), int(dims[level][1])
        else:
            width, height = slide_info.get("dimensions") or [1024, 1024]
            ds = [1, 4, 8][level]
            width, height = math.ceil(width / ds), math.ceil(height / ds)
        nx = max(1, math.ceil(width / 1024))
        ny = max(1, math.ceil(height / 1024))
        center = (max(0, nx // 2), max(0, ny // 2))
        coords.append((level, center[0], center[1]))
        while len([c for c in coords if c[0] == level]) < max(1, count // 3):
            coords.append((level, rng.randrange(nx), rng.randrange(ny)))
    while len(coords) < count:
        level = rng.choice([0, 1, 2])
        dims_level = dims[level] if level < len(dims) and dims[level] else slide_info.get("dimensions", [1024, 1024])
        ds = [1, 4, 8][level]
        width = math.ceil(int(dims_level[0]) / (1 if level < len(dims) else ds))
        height = math.ceil(int(dims_level[1]) / (1 if level < len(dims) else ds))
        coords.append((level, rng.randrange(max(1, math.ceil(width / 1024))), rng.randrange(max(1, math.ceil(height / 1024)))))
    rng.shuffle(coords)
    return coords[:count]


def _record(state: SharedState, result: tuple[Any, Sample]) -> Any:
    payload, sample = result
    state.add(sample)
    return payload


def _open_slide(client: Client, state: SharedState, filename: str, path: str, open_page: str) -> dict[str, Any]:
    body, content_type = _multipart({"filename": filename, "path": path, "open_page": open_page})
    payload = _record(state, client.request(
        "POST",
        "/slides/open",
        body=body,
        headers={"Content-Type": content_type},
        name="slides.open",
    ))
    if not payload or not payload.get("exists"):
        raise RuntimeError(f"slide open failed or not found: {filename} path={path}")
    return payload


def _start_ai(client: Client, state: SharedState, slide_id: str, model: str) -> None:
    model = model.strip().lower()
    if model == "none":
        return
    if model == "assistance":
        payload = _record(state, client.request(
            "POST",
            f"/cell-annotation/{slide_id}/wsi-labeling-assistance/run",
            body=b"{}",
            headers={"Content-Type": "application/json"},
            name="cell.assistance.run",
        ))
    else:
        path = {
            "detect": "/ai/detect",
            "pd-score": "/ai/pd-score",
            "precise-ihc": "/ai/precise-ihc",
            "virtual-stain": "/ai/virtual-stain",
        }.get(model)
        if not path:
            raise ValueError(f"unknown --start-ai value: {model}")
        fields = {"slide_id": slide_id}
        if model == "precise-ihc":
            fields["marker"] = "HER2"
        body, content_type = _multipart(fields)
        payload = _record(state, client.request(
            "POST",
            path,
            body=body,
            headers={"Content-Type": content_type},
            name=f"ai.{model}.start",
        ))
    if isinstance(payload, dict):
        state.add_ai_task(str(payload.get("task_id") or ""))


def virtual_user(
    user_index: int,
    args: argparse.Namespace,
    state: SharedState,
    filename: str,
    slide_path: str,
) -> None:
    rng = random.Random(args.seed + user_index)
    client = Client(args.base_url, token=args.token or "", timeout=args.timeout)
    if not client.token:
        client.login(args.login_id, args.password, args.totp)
    client.ensure_media_ticket()

    open_pages = ["ai", "cell-annotation", "tissue-annotation"]
    open_page = open_pages[user_index % len(open_pages)]
    slide = _open_slide(client, state, filename, slide_path, open_page)
    slide_id = str(slide.get("slide_id") or "")
    if not slide_id:
        raise RuntimeError("slides.open returned no slide_id")

    if args.start_ai and (args.ai_per_user or user_index == 0):
        for model in args.start_ai:
            _start_ai(client, state, slide_id, model)

    deadline = time.monotonic() + args.duration
    iterations = 0
    while time.monotonic() < deadline and iterations < args.iterations:
        iterations += 1
        if iterations % max(1, args.media_refresh_every) == 0:
            try:
                client.ensure_media_ticket()
            except Exception as exc:
                state.add(Sample("auth.media-ticket", False, 0, error=str(exc)[:240]))
        mt = urllib.parse.quote(client.media_ticket)
        tile_tasks = _tile_coords(slide, rng, args.tiles_per_iteration)

        requests: list[tuple[str, str, bool]] = [
            ("slides.info", f"/slides/{slide_id}/info", True),
            ("slides.tile-progress", f"/slides/tile-progress/{slide_id}", True),
            ("cell.grid-config", f"/cell-annotation/{slide_id}/grid-config", True),
            ("cell.required-regions", f"/cell-annotation/{slide_id}/required-regions", True),
            ("cell.patches", f"/cell-annotation/{slide_id}/patches", True),
            ("cell.assistance.options", f"/cell-annotation/{slide_id}/wsi-labeling-assistance/options", True),
            ("cell.assistance", f"/cell-annotation/{slide_id}/wsi-labeling-assistance", True),
            ("ai.active-tasks", "/ai/active-tasks", True),
            ("slides.thumbnail", f"/slides/{slide_id}/thumbnail?size=300&mt={mt}", False),
        ]
        for level, tx, ty in tile_tasks:
            requests.append((f"tile.L{level}", f"/tiles/{slide_id}/{level}/{tx}/{ty}.jpeg?mt={mt}", False))

        rng.shuffle(requests)
        for name, path, expect_json in requests:
            _record(state, client.request("GET", path, name=name, expect_json=expect_json))
            if args.jitter_ms > 0:
                time.sleep(rng.uniform(0, args.jitter_ms) / 1000)

        with state.lock:
            task_ids = list(state.ai_tasks)
        for task_id in task_ids[: args.poll_ai_tasks]:
            _record(state, client.request("GET", f"/ai/task/{task_id}", name="ai.task", expect_json=True))


def summarize(samples: list[Sample]) -> int:
    if not samples:
        print("No samples collected.")
        return 1
    grouped: dict[str, list[Sample]] = {}
    for sample in samples:
        grouped.setdefault(sample.name, []).append(sample)
    total = len(samples)
    failed = len([s for s in samples if not s.ok])
    print(f"\nTotal requests: {total}  failed: {failed}  error_rate: {failed / total * 100:.2f}%")
    print("Endpoint summary:")
    print(f"{'name':34} {'count':>7} {'fail':>5} {'p50':>8} {'p95':>8} {'max':>8} {'MB':>8}")
    for name in sorted(grouped):
        items = grouped[name]
        lat = sorted(s.elapsed_ms for s in items)
        p50 = _percentile(lat, 50)
        p95 = _percentile(lat, 95)
        max_v = max(lat)
        fail = len([s for s in items if not s.ok])
        mb = sum(s.bytes_read for s in items) / 1024 / 1024
        print(f"{name[:34]:34} {len(items):7d} {fail:5d} {p50:8.1f} {p95:8.1f} {max_v:8.1f} {mb:8.1f}")
    if failed:
        print("\nFirst errors:")
        for sample in [s for s in samples if not s.ok][:12]:
            print(f"- {sample.name}: status={sample.status} {sample.error}")
    return 2 if failed else 0


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    idx = (len(values) - 1) * pct / 100
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return values[int(idx)]
    return values[lo] * (hi - idx) + values[hi] * (idx - lo)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Concurrent MeDICus SaaS smoke/load test")
    parser.add_argument("--base-url", default=os.environ.get("MEDIAUTO_BASE_URL", "http://127.0.0.1:8092"))
    parser.add_argument("--users", type=int, default=5, help="concurrent virtual users")
    parser.add_argument("--duration", type=float, default=60.0, help="seconds per virtual user")
    parser.add_argument("--iterations", type=int, default=999999, help="max iterations per user")
    parser.add_argument("--tiles-per-iteration", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--jitter-ms", type=int, default=80)
    parser.add_argument("--seed", type=int, default=20260715)
    parser.add_argument("--media-refresh-every", type=int, default=8)
    parser.add_argument("--poll-ai-tasks", type=int, default=4)
    parser.add_argument("--login-id", default=os.environ.get("MEDIAUTO_LOGIN_ID", ""))
    parser.add_argument("--password", default=os.environ.get("MEDIAUTO_PASSWORD", ""))
    parser.add_argument("--totp", default=os.environ.get("MEDIAUTO_TOTP", ""))
    parser.add_argument("--token", default=os.environ.get("MEDIAUTO_ACCESS_TOKEN", ""))
    parser.add_argument("--shared-login", action="store_true", help="log in once and share the access token across virtual users")
    parser.add_argument("--slide", default="", help="filename under backend/uploads")
    parser.add_argument("--path", default="", help="relative folder path under backend/uploads")
    parser.add_argument(
        "--start-ai",
        action="append",
        default=[],
        choices=["detect", "pd-score", "precise-ihc", "virtual-stain", "assistance"],
        help="optionally start an AI task; may be repeated. By default starts once from user 0.",
    )
    parser.add_argument("--ai-per-user", action="store_true", help="start selected AI tasks for every virtual user")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.token and not (args.login_id and args.password):
        print("Need --token or --login-id/--password (or MEDIAUTO_ACCESS_TOKEN / MEDIAUTO_LOGIN_ID / MEDIAUTO_PASSWORD).", file=sys.stderr)
        return 1
    repo_root = Path(__file__).resolve().parents[2]
    filename = args.slide
    slide_path = args.path
    if not filename:
        filename, slide_path = _find_default_slide(repo_root)
    if args.shared_login and not args.token:
        login_client = Client(args.base_url, timeout=args.timeout)
        login_client.login(args.login_id, args.password, args.totp)
        args.token = login_client.token
    print(
        f"Load test: users={args.users} duration={args.duration}s base={args.base_url} "
        f"slide={slide_path + '/' if slide_path else ''}{filename} start_ai={args.start_ai or 'no'}"
    )
    state = SharedState()
    started = time.perf_counter()
    failures = 0
    with ThreadPoolExecutor(max_workers=args.users) as pool:
        futures = [
            pool.submit(virtual_user, idx, args, state, filename, slide_path)
            for idx in range(args.users)
        ]
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as exc:
                failures += 1
                state.add(Sample("virtual_user", False, 0, error=str(exc)[:240]))
    elapsed = time.perf_counter() - started
    print(f"Elapsed: {elapsed:.1f}s  virtual_user_failures={failures}")
    return summarize(state.samples)


if __name__ == "__main__":
    raise SystemExit(main())
