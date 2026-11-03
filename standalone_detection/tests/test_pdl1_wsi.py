import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pdl1_wsi import load_reader_csvs, compare_readers


def write_csv(root, rows):
    path = root / 'reader' / '비교결과.csv'
    path.parent.mkdir(exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def record(slide='s1', grade='1 ≤ CPS < 10'):
    return {'프로젝트': 'PD-L1(ST)', '슬라이드 ID': slide, '계정 ID': 'a',
            'CPS Grade': grade, '전문의 판독시간(초)': '123', 'AI 판독시간(초)': '45',
            'AI CPS (%)': '999999', '판별 모델': 'Stomach',
            '측정 시각(KST)': '2026-11-03T10:00:00+09:00', '측정 ID': 'm1'}


def test_csv_ignores_saved_ai_and_json(tmp_path):
    path = write_csv(tmp_path, [record()])
    path.with_suffix('.json').write_text('not JSON')
    rows = load_reader_csvs(tmp_path)
    assert rows[0]['grade'] == 1
    assert rows[0]['reader_seconds'] == 123
    assert rows[0]['ai_seconds'] == 45
    assert 'AI CPS (%)' not in rows[0]
    result = {'s1': {'complete': True, 'cps': 15, 'grade': 2,
                     'inference_seconds': 3, 'status': 'ok'}}
    pairs, *_ = compare_readers(rows, result)
    assert pairs[0]['ai_grade'] == 2
    assert pairs[0]['ai_seconds'] == 45
    assert pairs[0]['inference_seconds'] == 3


def test_conflicting_repeats_fail(tmp_path):
    write_csv(tmp_path, [record(), record(grade='CPS ≥ 10')])
    with pytest.raises(ValueError, match='동일 측정'):
        load_reader_csvs(tmp_path)


@pytest.mark.parametrize('grade', ['3', 'nan', '-1', '1.5'])
def test_invalid_grade_rejected(tmp_path, grade):
    write_csv(tmp_path, [record(grade=grade)])
    with pytest.raises(ValueError):
        load_reader_csvs(tmp_path)


def test_partial_and_missing_predictions_fail(tmp_path):
    write_csv(tmp_path, [record()])
    rows = load_reader_csvs(tmp_path)
    with pytest.raises(ValueError, match='Missing WSI'):
        compare_readers(rows, {})
    with pytest.raises(ValueError, match='부분 패치'):
        compare_readers(rows, {'s1': {'complete': False}})


def test_majority_and_pairwise_missing():
    rows = []
    for slide, grades in [('s1', [0, 0, 2]), ('s2', [1, 1, 2]), ('s3', [0, 1, 2]), ('s4', [None, None, None])]:
        rows.extend({'project': 'p', 'slide': slide, 'account': str(i), 'grade': grade}
                    for i, grade in enumerate(grades))
    predictions = {s: {'complete': True, 'cps': cps, 'grade': grade,
                        'inference_seconds': 5, 'status': 'ok'}
                   for s, cps, grade in [('s1', 0, 0), ('s2', 5, 1), ('s3', 50, 2), ('s4', None, None)]}
    _, summaries, consensus, overall = compare_readers(rows, predictions)
    assert [r['grade'] for r in consensus] == [0, 1, None, None]
    assert overall[0]['paired'] == 2
    assert overall[0]['PCC'] == pytest.approx(1)
    assert overall[0]['CCC'] == pytest.approx(1)
    assert summaries[0]['excluded'] == 1


def test_latest_reading_matches_zip_order(tmp_path):
    older = record(grade='CPS < 1')
    newer = {**record(grade='CPS ≥ 10'), '측정 시각(KST)': '2026-11-03T11:00:00+09:00'}
    tied = {**newer, 'CPS Grade': '1 ≤ CPS < 10', '측정 ID': 'm2'}
    write_csv(tmp_path, [tied, older, newer])
    result = load_reader_csvs(tmp_path)
    assert len(result) == 1
    assert result[0]['grade'] == 1
    assert result[0]['measurement_id'] == 'm2'


def test_actual_knuch_export_schema():
    root = Path(__file__).resolve().parents[1] / 'examples/knuch_zip_export'
    rows = load_reader_csvs(root)
    assert len(rows) == 9
    assert rows == load_reader_csvs(root / '계정별')
    assert len(load_reader_csvs(root / '계정별/예제_reader_a')) == 3
    assert {r['grade'] for r in rows} == {0, 1, 2}
    assert {r['reader_seconds'] for r in rows} == {120, 150, 180}
    assert {r['ai_seconds'] for r in rows} == {40, 50, 60}
    assert all('ai_percentage' not in r and 'percentage' not in r for r in rows)


def test_missing_grade_not_derived_from_score_and_other_models_skipped(tmp_path):
    write_csv(tmp_path, [{**record(grade=''), 'CPS (%)': '75'},
                         {**record(), '판별 모델': 'Lung', 'CPS (%)': '99'}])
    rows = load_reader_csvs(tmp_path)
    assert len(rows) == 1
    assert rows[0]['grade'] is None
