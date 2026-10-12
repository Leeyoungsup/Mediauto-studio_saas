"""Check concurrent measurements and per-account/per-slide JSON isolation."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from app.comparison_files import write_comparison_json
from app.config import settings


@pytest.fixture
def storage(monkeypatch, tmp_path):
    uploads = tmp_path / 'slides'
    monkeypatch.setattr(settings, 'UPLOAD_DIR', str(uploads))
    monkeypatch.setattr(settings, 'COMPARISON_DIR', str(tmp_path / 'comparison'))
    path = uploads / 'project' / 'anonymous.svs'
    path.parent.mkdir(parents=True);path.touch()
    return path


def record(identifier='1', user='a', seconds=0):
    return {'_id':identifier, 'user_id':user, 'user_name':f'Specialist {user}',
            'slide_id':'slide-one', 'project_path':'project', 'filename':'anonymous.svs',
            'specialist_elapsed_ms':1000, 'ai_result_elapsed_ms':500,
            'dt_created_at':datetime(2026,10,12,tzinfo=timezone.utc)+timedelta(seconds=seconds)}


def test_concurrent_measurements_are_retained_and_retries_are_unique(storage):
    with ThreadPoolExecutor(max_workers=6) as executor:
        paths = list(executor.map(lambda i:write_comparison_json(record(str(i),seconds=i),str(storage)),range(12)))
    assert len(set(paths)) == 1
    write_comparison_json(record('1',seconds=1),str(storage))
    document = json.loads(paths[0].read_text())
    assert len(document['measurements']) == 12
    assert document['latest']['measurement_id'] == '11'
    assert paths[0].stat().st_mode & 0o777 == 0o600


def test_account_and_same_filename_different_folder_isolation(storage):
    account_a = write_comparison_json(record(user='a'),str(storage))
    account_b = write_comparison_json(record(user='b'),str(storage))
    other = storage.parent / 'other-folder' / storage.name
    other.parent.mkdir();other.touch()
    other_slide = write_comparison_json(record(user='a'),str(other))
    assert len({account_a,account_b,other_slide}) == 3
    assert json.loads(account_a.read_text())['account']['user_id'] == 'a'
    assert json.loads(account_b.read_text())['account']['user_id'] == 'b'


def test_export_rejects_external_slide(storage, tmp_path):
    with pytest.raises(ValueError):write_comparison_json(record(),str(tmp_path/'external.svs'))


def test_export_does_not_follow_account_json_symlink(storage, tmp_path):
    target = write_comparison_json(record(),str(storage))
    target.unlink()
    external=tmp_path/'external.json';external.write_text('preserve')
    target.symlink_to(external)
    with pytest.raises(OSError):write_comparison_json(record('2'),str(storage))
    assert external.read_text() == 'preserve'
