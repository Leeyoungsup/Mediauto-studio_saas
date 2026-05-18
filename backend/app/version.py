from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


_DEFAULT_VERSION_INFO: dict[str, Any] = {
    "name": "MeDIAuto Studio",
    "version": "0.0.0",
    "channel": "unknown",
    "release_date": "",
    "description": "",
}


def _version_file() -> Path:
    return Path(__file__).resolve().parents[2] / "version.json"


@lru_cache(maxsize=1)
def get_version_info() -> dict[str, Any]:
    try:
        with _version_file().open("r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (OSError, json.JSONDecodeError):
        data = {}
    info = {**_DEFAULT_VERSION_INFO, **(data if isinstance(data, dict) else {})}
    info["version"] = str(info.get("version") or _DEFAULT_VERSION_INFO["version"])
    return info


APP_VERSION = get_version_info()["version"]
