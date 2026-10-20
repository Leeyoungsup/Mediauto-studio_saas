import io
import json
import math
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pdl1_pcc import (calculate_account_pcc, calculate_consensus_pcc,
                     grade_majority_median, lin_ccc, pearson_pcc, save_pcc_csv, score_to_grade_code)


@pytest.mark.parametrize('x,y,expected', [
    ([0, 1, 2], [1, 2, 3], 1),
    ([0, 1, 2], [2, 1, 0], -1),
    ([1, 0, -1, 0], [0, 1, 0, -1], 0),
    ([], [], None), ([1], [2], None), ([1, 1], [1, 2], None),
])
def test_formula(x, y, expected):
    result = pearson_pcc(x, y)
    assert result == pytest.approx(expected) if expected is not None else result is None


def test_invalid_arrays_are_rejected():
    with pytest.raises(ValueError):
        pearson_pcc([1, 2], [1])
    with pytest.raises(ValueError):
        pearson_pcc([1, math.nan], [1, 2])


def test_grade_pcc_uses_encoded_bands_instead_of_continuous_cps(tmp_path):
    records = [{'project_path': 'p', 'slide_id': str(i), 'user_id': 'u',
                'percentage': x, 'ai_percentage': y}
               for i, (x,y) in enumerate([(0,9), (5,9), (20,10)])]
    (tmp_path / '비교결과.json').write_text(json.dumps({'measurements': records}))
    result = calculate_account_pcc(tmp_path)[0]
    assert result['PCC'] == pytest.approx(math.sqrt(3)/2)
    assert result['PCC'] != pytest.approx(pearson_pcc([0,5,20], [9,9,10]))
    assert result['PCC 기준'] == 'Grade (0/1/2)'
    assert result['CCC'] == pytest.approx(2/3)
    assert result['CCC 기준'] == 'Grade (0/1/2)'
    assert [score_to_grade_code(v) for v in [0,1,9.99,10,100]] == [0,1,1,2,2]
    assert [score_to_grade_code(v,'TPS') for v in [0,1,49.99,50,100]] == [0,1,1,2,2]


@pytest.mark.parametrize('x,y,expected', [
    ([0,1,2], [0,1,2], 1), ([0,1,2], [2,1,0], -1),
    ([0,1,2], [0,2,2], 0.8), ([1,1], [2,2], 0),
    ([1,1], [1,1], None), ([1], [1], None), ([], [], None),
])
def test_grade_ccc_population_formula_and_undefined_cases(x,y,expected):
    result = lin_ccc(x,y)
    assert result == pytest.approx(expected) if expected is not None else result is None


def test_real_zip_schema_json_and_csv_produce_same_latest_results(tmp_path):
    from app.comparison_export import build_comparison_zip
    records = []
    for uid in ('a', 'b'):
        for slide, x, y in [('one', 1, 2), ('two', 5, 4), ('three', 20, 23), ('missing', 5, None)]:
            records.append({
                '_id': slide + uid, 'project_path': 'project', 'slide_id': slide,
                'filename': slide + '.svs', 'user_id': uid, 'username': uid,
                'tissue_type': 'Stomach', 'score_type': 'CPS',
                'percentage': x, 'ai_percentage': y,
                'dt_created_at': datetime(2026, 10, 20, tzinfo=timezone.utc),
            })
    records.append({**records[0], '_id': 'old', 'percentage': 90,
                    'dt_created_at': datetime(2026, 10, 19, tzinfo=timezone.utc)})
    records.append({**records[0], '_id': 'breast', 'tissue_type': 'Breast'})
    with zipfile.ZipFile(io.BytesIO(build_comparison_zip(records))) as archive:
        archive.extractall(tmp_path)
    by_json = calculate_account_pcc(tmp_path)
    assert len(by_json) == 3
    stomach = [row for row in by_json if row['판별 모델'] == 'Stomach']
    expected = pearson_pcc([1, 1, 2], [1, 1, 2])
    for row in stomach:
        assert row['PCC'] == pytest.approx(expected)
        assert row['대상 슬라이드 수'] == 4 and row['제외 슬라이드 수'] == 1
    assert calculate_account_pcc(tmp_path / '계정별') == by_json
    assert len(calculate_account_pcc(tmp_path / '계정별' / 'a')) == 2
    for path in tmp_path.rglob('비교결과.json'):
        path.unlink()
    assert calculate_account_pcc(tmp_path) == by_json
    output = save_pcc_csv(by_json, tmp_path / 'pcc.csv')
    assert output.read_bytes().startswith(b'\xef\xbb\xbf')


def test_notebook_executes_against_account_fixture(tmp_path, monkeypatch):
    # Reproduce a kernel that still holds the older module without Grade encoding.
    import pdl1_pcc
    monkeypatch.delattr(pdl1_pcc, 'score_to_grade_code')
    account = tmp_path / 'reader'
    account.mkdir()
    records = [{'project_path': 'p', 'slide_id': str(i), 'user_id': 'u',
                'percentage': [0, 5, 20][i], 'ai_percentage': [0.5, 6, 30][i]} for i in range(3)]
    (account / '비교결과.json').write_text(json.dumps({'measurements': records}))
    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(root)
    notebook = json.loads((root / 'PDL1_account_PCC.ipynb').read_text())
    namespace = {}
    for cell in notebook['cells']:
        if cell['cell_type'] != 'code':
            continue
        source = ''.join(cell['source'])
        if 'ACCOUNT_FOLDER = Path(' in source:
            namespace['ACCOUNT_FOLDER'] = account
            continue
        exec(compile(source, '<notebook-cell>', 'exec'), namespace)
    assert namespace['results'][0]['PCC'] == pytest.approx(1)
    assert (account / '계정별_PCC_결과.csv').is_file()


def test_legacy_export_without_ai_fails_with_clear_message(tmp_path):
    (tmp_path / '비교결과.json').write_text(json.dumps({'measurements': [{'percentage': 1}]}))
    with pytest.raises(ValueError, match='AI 점수'):
        calculate_account_pcc(tmp_path)


@pytest.mark.parametrize('values,expected,indices', [
    ([1, 3, 80], 2, [0, 1]),
    ([1, 2, 8, 80], 2, [0, 1, 2]),
    ([0, 5, 25], None, []),
    ([1, 80], None, []),
    ([5], None, []),
    ([1, 3, None], 2, [0, 1]),
])
def test_grade_majority_then_selected_readers_median(values, expected, indices):
    result = grade_majority_median(values)
    assert result['median'] == expected
    assert result['selected_indices'] == indices


def test_consensus_steps_and_pcc_match_backend_export(tmp_path):
    from app.comparison_export import build_comparison_zip, measurement
    from app.comparison_statistics import build_reports
    records = []
    for slide, scores, ai in [('one', [1, 3, 80], 2), ('two', [0, 0.5, 90], 0.25),
                              ('three', [20, 30, 0], 25), ('tie', [0, 5, 25], 10)]:
        for uid, value in zip('abc', scores):
            records.append({'_id': slide+uid, 'project_path': 'p', 'slide_id': slide,
                            'filename': slide+'.svs', 'user_id': uid, 'username': uid,
                            'tissue_type': 'Stomach', 'score_type': 'CPS',
                            'percentage': value, 'ai_percentage': ai})
    with zipfile.ZipFile(io.BytesIO(build_comparison_zip(records))) as archive:
        archive.extractall(tmp_path)
    slides, metrics = calculate_consensus_pcc(tmp_path)
    one = next(row for row in slides if row['슬라이드 ID'] == 'one')
    assert one['합의 CPS/TPS 중앙값'] == 2
    assert one['중앙값 산출 계정'] == 'a; b'
    assert metrics[0]['PCC'] == pytest.approx(1)
    assert metrics[0]['대응 슬라이드 수'] == 3
    assert metrics[0]['제외 슬라이드 수'] == 1
    backend = build_reports([measurement(record) for record in records])
    assert backend['metrics'][0]['PCC'] == pytest.approx(metrics[0]['PCC'])
    assert backend['metrics'][0]['CCC'] == pytest.approx(metrics[0]['CCC'])
    assert backend['metrics'][0]['대응 슬라이드 수'] == metrics[0]['대응 슬라이드 수']
