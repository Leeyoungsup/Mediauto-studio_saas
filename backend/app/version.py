from __future__ import annotations

import json
import re
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

_RELEASE_PATTERN = re.compile(r"^## \[([^\]]+)](?:\s+-\s+(.+))?$")
_SECTION_PATTERN = re.compile(r"^###\s+(.+)$")


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


def parse_changelog(str_markdown: str) -> list[dict[str, Any]]:
    """Parse Keep-a-Changelog-style release sections into JSON-safe data."""
    list_releases: list[dict[str, Any]] = []
    dict_release: dict[str, Any] | None = None
    dict_section: dict[str, Any] | None = None

    for str_raw_line in str_markdown.splitlines():
        str_line = str_raw_line.strip()
        obj_release_match = _RELEASE_PATTERN.match(str_line)
        if obj_release_match:
            dict_release = {
                "version": obj_release_match.group(1).strip(),
                "date": (obj_release_match.group(2) or "").strip(),
                "sections": [],
            }
            list_releases.append(dict_release)
            dict_section = None
            continue

        if dict_release is None:
            continue

        obj_section_match = _SECTION_PATTERN.match(str_line)
        if obj_section_match:
            dict_section = {
                "title": obj_section_match.group(1).strip(),
                "items": [],
            }
            dict_release["sections"].append(dict_section)
            continue

        if str_line.startswith("- "):
            if dict_section is None:
                dict_section = {"title": "Notes", "items": []}
                dict_release["sections"].append(dict_section)
            dict_section["items"].append(str_line[2:].strip())

    for dict_item in list_releases:
        dict_item["change_count"] = sum(
            len(dict_section_item["items"])
            for dict_section_item in dict_item["sections"]
        )
    return list_releases


@lru_cache(maxsize=1)
def get_version_history() -> dict[str, Any]:
    """Return current metadata plus all release notes from CHANGELOG.md."""
    path_changelog = _version_file().with_name("CHANGELOG.md")
    try:
        str_markdown = path_changelog.read_text(encoding="utf-8")
    except OSError:
        str_markdown = ""
    list_releases = parse_changelog(str_markdown)
    return {
        "current": get_version_info(),
        "releases": list_releases,
        "total_releases": len(list_releases),
        "source": "CHANGELOG.md",
    }
