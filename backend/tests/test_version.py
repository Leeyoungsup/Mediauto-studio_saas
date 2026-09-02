from app.version import get_version_history, parse_changelog


def test_parse_changelog_builds_release_sections_and_counts():
    list_releases = parse_changelog(
        """# Changelog

## [2.0.0] - 2026-09-01

### Added

- First feature.
- Second feature.

### Fixed

- One fix.

## [1.0.0] - 2026-01-01

### Notes

- Initial release.
"""
    )

    assert [item["version"] for item in list_releases] == ["2.0.0", "1.0.0"]
    assert list_releases[0]["date"] == "2026-09-01"
    assert list_releases[0]["change_count"] == 3
    assert list_releases[0]["sections"][1] == {
        "title": "Fixed",
        "items": ["One fix."],
    }


def test_repository_changelog_contains_current_release():
    dict_history = get_version_history()

    assert dict_history["current"]["version"] == "2.0.1"
    assert dict_history["total_releases"] >= 235
    assert dict_history["releases"][0]["version"] == "2.0.1"
    assert dict_history["releases"][0]["change_count"] > 0
