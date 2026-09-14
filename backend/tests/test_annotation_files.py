from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException

from app import annotation_files


def test_atomic_replace_failure_preserves_existing_file(tmp_path, monkeypatch):
    path = tmp_path / "annotations.json"
    path.write_text('[{"memo":"original"}]')
    original, revision = annotation_files.read_snapshot(path)
    def fail(*args):
        raise OSError("simulated full disk")
    monkeypatch.setattr(annotation_files.os, "replace", fail)
    with pytest.raises(OSError):
        annotation_files.save_snapshot(path, [], revision)
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_concurrent_saves_only_one_wins(tmp_path):
    path = tmp_path / "annotations.json"
    _, revision = annotation_files.read_snapshot(path)
    def save(value):
        try:
            annotation_files.save_snapshot(path, [value], revision)
            return 200
        except HTTPException as exc:
            return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save, [1, 2])) == [200, 409]
