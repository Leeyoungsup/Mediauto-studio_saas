"""Exercise key loss prevention and both clinical storage copies in isolated DBs."""
import asyncio
import base64
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.config import settings
from app.encryption import encrypt_json, decrypt_json, ENCRYPTED_JSON_MARKER
from app.postgres.base import Base
from app.postgres.models import ApplicationDocument, CaseClinicalInfo
from app.postgres import database
from app.repositories.application_store import PostgresDocumentCollection, encode_document_value, decode_document_value
from app.repositories.operational_store import PostgresClinicalInfoStore
from scripts.encrypt_clinical_data import convert


def load_config(tmp_path, secret):
    config = tmp_path / "config.py"
    shutil.copyfile(Path(__file__).parents[1] / "app/config.py", config)
    spec = importlib.util.spec_from_file_location("isolated_secure_config", config)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(os.environ, {"MEDIAUTO_SECRETS_FILE": str(secret)}, clear=True):
        spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("content", ["{broken", "[]", "{}", '{"jwt_secret_key":"existing"}',
                                     '{"jwt_secret_key":null,"field_encryption_key":"existing"}'])
def test_damaged_existing_keys_are_never_replaced(tmp_path, content):
    secret = tmp_path / "secrets.json"
    secret.write_text(content)
    with pytest.raises(RuntimeError, match="Cannot safely load"):
        load_config(tmp_path, secret)
    assert secret.read_text() == content


def test_existing_keys_survive_and_permissions_are_repaired(tmp_path):
    secret = tmp_path / "secrets.json"
    old = {"jwt_secret_key": "original-jwt", "field_encryption_key": "original-field", "pepper": "original-pepper"}
    secret.write_text(json.dumps(old)); secret.chmod(0o644)
    module = load_config(tmp_path, secret)
    assert json.loads(secret.read_text()) == old
    assert module.settings.JWT_SECRET_KEY == old["jwt_secret_key"]
    if os.name == "posix":
        assert stat.S_IMODE(secret.stat().st_mode) == 0o600


def test_symlink_does_not_change_target(tmp_path):
    target = tmp_path / "target"; target.write_text("keep me")
    secret = tmp_path / "secrets.json"; secret.symlink_to(target)
    with pytest.raises(RuntimeError, match="symbolic link"):
        load_config(tmp_path, secret)
    assert target.read_text() == "keep me"


def test_legacy_pepper_migration_preserves_existing_keys(tmp_path):
    secret = tmp_path / "secrets.json"
    secret.write_text(json.dumps({"jwt_secret_key": "original-jwt", "field_encryption_key": "original-field"}))
    module = load_config(tmp_path, secret)
    assert module.settings.AUTH_PEPPER == "MeDICus_2024_P3pp3r"
    assert json.loads(secret.read_text())["field_encryption_key"] == "original-field"
    assert not list(tmp_path.glob(".secrets-*"))


def test_new_keys_are_persisted_and_survive_restart(tmp_path):
    secret = tmp_path / "keys/secrets.json"
    first = load_config(tmp_path, secret).settings
    original = secret.read_bytes()
    second = load_config(tmp_path, secret).settings
    assert first.FIELD_ENCRYPTION_KEY == second.FIELD_ENCRYPTION_KEY
    assert len(base64.urlsafe_b64decode(first.FIELD_ENCRYPTION_KEY + "=")) == 32
    assert original == secret.read_bytes()


def test_concurrent_starter_keeps_winner_keys(tmp_path):
    secret = tmp_path / "secrets.json"
    winner = {"jwt_secret_key": "winning-jwt", "field_encryption_key": "winning-field", "pepper": "winning-pepper"}
    def publish_winner(*args):
        secret.write_text(json.dumps(winner))
        raise FileExistsError()
    with patch("os.link", side_effect=publish_winner):
        module = load_config(tmp_path, secret)
    assert module.settings.JWT_SECRET_KEY == winner["jwt_secret_key"]
    assert json.loads(secret.read_text()) == winner
    assert not list(tmp_path.glob(".secrets-*"))


def test_persistence_failure_stops_startup_without_publishing_keys(tmp_path):
    secret = tmp_path / "secrets.json"
    with patch("os.link", side_effect=PermissionError()), pytest.raises(RuntimeError, match="Cannot persist"):
        load_config(tmp_path, secret)
    assert not secret.exists()
    assert not list(tmp_path.glob(".secrets-*"))


def test_json_encryption_round_trip_and_random_nonce():
    info = {"Ki67_index": "sensitive clinical value", "nested": {"value": "한글"}}
    one, two = encrypt_json(info), encrypt_json(info)
    assert one != two
    assert "sensitive clinical value" not in json.dumps(one)
    assert decrypt_json(one) == info
    assert decrypt_json(info) == info  # Legacy read compatibility.


def test_tampered_and_unknown_envelopes_fail_closed(monkeypatch):
    envelope = encrypt_json({"Ki67_index": "clinical"})
    raw = bytearray(base64.urlsafe_b64decode(envelope["ciphertext"])); raw[-1] ^= 1
    envelope["ciphertext"] = base64.urlsafe_b64encode(raw).decode()
    with pytest.raises(InvalidTag): decrypt_json(envelope)
    with pytest.raises(ValueError): decrypt_json({ENCRYPTED_JSON_MARKER: "unknown", "ciphertext": ""})
    envelope = encrypt_json({"Ki67_index": "private"})
    monkeypatch.setattr(settings, "FIELD_ENCRYPTION_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    with pytest.raises(InvalidTag): decrypt_json(envelope)


def test_slide_clinical_copy_preserves_datetime_and_dotted_updates():
    dt = datetime.now(timezone.utc)
    source = {"dict_clinical_info": {"Ki67_index": "private"}, "dt_updated_at": dt}
    stored = encode_document_value(source)
    assert "private" not in json.dumps(stored)
    assert decode_document_value(stored) == source


def test_real_storage_and_backfill_are_safe(monkeypatch, tmp_path):
    async def run():
        uri = os.environ.get("SECURITY_TEST_DATABASE_URI", "")
        schema = "clinical_test_" + uuid.uuid4().hex
        if uri:
            parsed = make_url(uri)
            assert parsed.host == "127.0.0.1" and parsed.database == "knuch_security_test"
            engine = create_async_engine(uri, poolclass=NullPool, connect_args={"server_settings": {"search_path": schema}})
        else:
            engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "clinical.sqlite"))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(database, "_session_factory", factory)
        async with engine.begin() as conn:
            if uri: await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            await conn.run_sync(Base.metadata.create_all)
        cases = PostgresClinicalInfoStore(); slides = PostgresDocumentCollection("slides")
        await cases.insert({"_id": "new-case", "str_case_name": "anonymous-new", "dict_clinical_info": {"Ki67_index": "protected value"}})
        if uri:
            await cases.upsert("anonymous-new", {"Ki67_index": "protected value"}, datetime.now(timezone.utc))
        await slides.insert_one({"_id": "new-slide", "str_filename": "anon.svs", "dict_clinical_info": {"Ki67_index": "protected value"}})
        await slides.update_one({"_id": "new-slide"}, {"$set": {"dict_clinical_info.Ki67_index": "updated protected"}})
        assert (await slides.find_one({"_id": "new-slide"}))["dict_clinical_info"]["Ki67_index"] == "updated protected"
        async with factory() as session:
            row = await session.get(CaseClinicalInfo, "new-case")
            assert "protected value" not in json.dumps(row.dict_clinical_info)
            row = await session.get(ApplicationDocument, ("slides", "new-slide"))
            assert "updated protected" not in json.dumps(row.dict_document)
            session.add(CaseClinicalInfo(str_id="old-case", str_case_name="anonymous-old", dict_clinical_info={"Ki67_index": "legacy private"}))
            session.add(ApplicationDocument(str_collection="slides", str_id="old-slide", str_natural_key="legacy", dict_document={"_id": "old-slide", "dict_clinical_info": {"Ki67_index": "legacy private"}}))
            await session.commit()
        async with factory() as session:
            assert (await convert(session))["clinical_rows"] == 1
            assert "legacy private" in json.dumps((await session.get(CaseClinicalInfo, "old-case")).dict_clinical_info)
        async with factory() as session:
            result = await convert(session, apply=True)
            assert result["clinical_rows"] == result["slide_copies"] == 1
            await session.commit()
        assert (await cases.find("anonymous-old"))["dict_clinical_info"] == {"Ki67_index": "legacy private"}
        async with factory() as session:
            result = await convert(session, apply=True)
            assert result["clinical_rows"] == result["slide_copies"] == 0
            row = await session.get(CaseClinicalInfo, "old-case")
            assert "legacy private" not in json.dumps(row.dict_clinical_info)
        # One unreadable existing row aborts the transaction without converting
        # any other row or discarding the original plaintext.
        async with factory() as session:
            session.add(CaseClinicalInfo(str_id="rollback-case", str_case_name="anonymous-rollback", dict_clinical_info={"Ki67_index": "keep original"}))
            row = await session.get(ApplicationDocument, ("slides", "old-slide"))
            document = dict(row.dict_document)
            broken = dict(document["dict_clinical_info"])
            raw = bytearray(base64.urlsafe_b64decode(broken["ciphertext"])); raw[-1] ^= 1
            broken["ciphertext"] = base64.urlsafe_b64encode(raw).decode()
            document["dict_clinical_info"] = broken
            row.dict_document = document
            await session.commit()
        with pytest.raises(InvalidTag):
            async with database.get_postgres_session() as session:
                await convert(session, apply=True)
        async with factory() as session:
            assert (await session.get(CaseClinicalInfo, "rollback-case")).dict_clinical_info == {"Ki67_index": "keep original"}
        if uri:
            async with engine.begin() as conn: await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()
    asyncio.run(run())
