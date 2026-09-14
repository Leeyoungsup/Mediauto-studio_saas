import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app import auth
from app.config import settings
from app.routers import annotation_storage, file_operations, projects, slides


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "ANNOTATIONS_DIR", str(tmp_path / "annotations"))
    monkeypatch.setattr(auth, "is_auth_store_connected", lambda: True)
    instance = FastAPI()
    for router in (projects.router, annotation_storage.router, file_operations.router, slides.router):
        instance.include_router(router, prefix="/api/slides")
    return instance


@pytest.mark.parametrize("url", ["/folder-tree", "/projects", "/annotation-classes?path=test",
                                  "/test/annotations/load"])
def test_private_reads_require_authentication(app, url):
    with TestClient(app) as client:
        assert client.get("/api/slides" + url).status_code == 401


@pytest.mark.parametrize("role, expected", [("viewer", 403), ("labeler", 200),
                                           ("doctor", 200), ("admin", 200)])
def test_file_delete_role_boundary(app, monkeypatch, role, expected):
    app.dependency_overrides[auth.get_current_user] = lambda: {"_id": "test", "str_role": role}
    delete = AsyncMock(return_value={"filename": "test.svs"})
    monkeypatch.setattr(file_operations, "_delete_slide_file", delete)
    monkeypatch.setattr(file_operations, "_log_event", AsyncMock())
    with TestClient(app) as client:
        response = client.post("/api/slides/file/delete", data={"filenames_json": '["test.svs"]'})
    assert response.status_code == expected
    assert delete.await_count == (1 if expected == 200 else 0)


@pytest.mark.parametrize("url", ["/file/move", "/file/status", "/folder/create",
                                  "/folder/rename", "/folder/delete"])
def test_viewer_cannot_mutate_files_or_folders(app, url):
    app.dependency_overrides[auth.get_current_user] = lambda: {"str_role": "viewer"}
    with TestClient(app) as client:
        assert client.post("/api/slides" + url).status_code == 403


@pytest.mark.parametrize("method,url", [("POST", "/upload/start"), ("POST", "/upload/chunk"),
                                       ("POST", "/upload/complete"),
                                       ("PATCH", "/cases/test/clinical-info"),
                                       ("PATCH", "/test/clinical-info")])
def test_viewer_cannot_upload_or_change_clinical_information(app, method, url):
    app.dependency_overrides[auth.get_current_user] = lambda: {"str_role": "viewer"}
    with TestClient(app) as client:
        assert client.request(method, "/api/slides" + url).status_code == 403


def test_unavailable_auth_store_fails_closed(monkeypatch):
    monkeypatch.setattr(auth, "is_auth_store_connected", lambda: False)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth.get_current_user(Request({"type": "http", "headers": []})))
    assert exc.value.status_code == 503


def test_media_ticket_cannot_cache_locked_user(monkeypatch):
    from app.url_signer import sign_media_ticket
    auth.invalidate_user_cache()
    user = {"_id": "locked", "bool_is_active": True, "bool_is_locked": True,
            "dt_locked_until": datetime.now(timezone.utc) + timedelta(minutes=5)}
    monkeypatch.setattr(auth, "is_auth_store_connected", lambda: True)
    monkeypatch.setattr(auth, "get_user_store", lambda: SimpleNamespace(find_by_id=AsyncMock(return_value=user)))
    ticket = sign_media_ticket("locked")["str_token"]
    request = Request({"type": "http", "headers": [], "query_string": f"mt={ticket}".encode()})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth.get_media_user(request))
    assert exc.value.status_code == 403
    assert auth._get_cached_user("locked") is None


def test_annotation_conflict_preserves_first_writer(app, monkeypatch, tmp_path):
    app.dependency_overrides[auth.get_current_user] = lambda: {"str_role": "doctor"}
    monkeypatch.setattr(annotation_storage.slide_manager, "get",
                        lambda _: SimpleNamespace(file_path=str(tmp_path / "test.svs")))
    with TestClient(app) as client:
        url = "/api/slides/test/annotations"
        before = client.get(url + "/load")
        assert before.json() == []
        assert client.post(url + "/save", data={"data": "[]"}).status_code == 428
        headers = {"If-Match": before.headers["etag"]}
        first = client.post(url + "/save", headers=headers, data={"data": '[{"memo":"first"}]'})
        assert first.status_code == 200
        stale = client.post(url + "/save", headers=headers, data={"data": '[{"memo":"stale"}]'})
        assert stale.status_code == 409
        current = client.get(url + "/load")
        assert current.json() == [{"memo": "first"}]
        assert current.headers["etag"] == first.json()["revision"]
