"""Calculate per-reader Pearson correlation from exported comparison folders.

Uses only Python's standard library and does not import the application/backend.
"""
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean, median


def pearson_pcc(reference, ai):
    """Return Pearson's r, or None for <2 pairs or a constant input.

    r = sum((x-mean(x))*(y-mean(y))) /
        sqrt(sum((x-mean(x))**2) * sum((y-mean(y))**2))

    Sequences must have equal lengths and contain finite numeric values.
    Missing values must be removed as PAIRS before calling this function.
    """
    x, y = list(reference), list(ai)
    if len(x) != len(y):
        raise ValueError('전문의와 AI 점수의 개수가 다릅니다.')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in x + y):
        raise ValueError('PCC 입력에는 유한한 숫자만 사용할 수 있습니다.')
    if len(x) < 2:
        return None
    mx, my = fmean(x), fmean(y)
    dx, dy = [v - mx for v in x], [v - my for v in y]
    sx, sy = math.fsum(v * v for v in dx), math.fsum(v * v for v in dy)
    if sx == 0 or sy == 0:
        return None
    # Normalize separately to avoid multiplying large squared sums.
    r = math.fsum((a / math.sqrt(sx)) * (b / math.sqrt(sy)) for a, b in zip(dx, dy))
    return max(-1.0, min(1.0, r))


def lin_ccc(reference, ai):
    """Lin CCC on matched Grade codes; population (1/N) moments.

    Return None for <2 pairs or zero denominator (identical constant arrays).
    """
    x, y = list(reference), list(ai)
    if len(x) != len(y):
        raise ValueError('전문의와 AI Grade의 개수가 다릅니다.')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in x + y):
        raise ValueError('CCC 입력에는 유한한 숫자만 사용할 수 있습니다.')
    if len(x) < 2:
        return None
    mx, my = fmean(x), fmean(y)
    vx, vy = fmean((v-mx)**2 for v in x), fmean((v-my)**2 for v in y)
    covariance = fmean((a-mx)*(b-my) for a,b in zip(x,y))
    denominator = vx + vy + (mx-my)**2
    return max(-1.0, min(1.0, 2*covariance/denominator)) if denominator > 0 else None


def _score(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and 0 <= result <= 100 else None


def score_to_grade_code(value, score_type='CPS'):
    """Grade encoding: CPS <1/1–<10/≥10; TPS <1/1–<50/≥50 → 0/1/2."""
    value = _score(value)
    if value is None:
        return None
    return 0 if value < 1 else 1 if value < (50 if score_type == 'TPS' else 10) else 2


def _csv_records(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        required = {'프로젝트', '슬라이드 ID', '판별 모델', '계정 ID', 'CPS (%)', 'AI CPS (%)'}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f'{path}: AI 점수가 포함된 새 비교결과 파일을 사용해주세요.')
        for row in reader:
            # One measurement is either CPS or TPS; empty CPS means TPS.
            kind = 'TPS' if not row.get('CPS (%)', '').strip() and row.get('TPS (%)', '').strip() else 'CPS'
            yield {
                'measurement_id': row.get('측정 ID', ''),
                'project_path': row['프로젝트'], 'slide_id': row['슬라이드 ID'],
                'tissue_type': row['판별 모델'], 'score_type': kind,
                'user_id': row['계정 ID'], 'username': row.get('로그인 ID', ''),
                'user_name': row.get('계정명', ''),
                'percentage': row.get(f'{kind} (%)'),
                'ai_percentage': row.get(f'AI {kind} (%)'),
                'measured_at': row.get('측정 시각(KST)'),
            }


def _order(record):
    value = record.get('measured_at')
    try:
        date = datetime.fromisoformat(value.replace('Z', '+00:00')) if value else datetime.min
    except (TypeError, ValueError) as error:
        raise ValueError(f"측정 시각을 해석할 수 없습니다: {value!r}") from error
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    return date, str(record.get('measurement_id', ''))


def load_latest_measurements(account_folder):
    """Read one account folder, the '계정별' parent, or the extracted ZIP root.

    Prefer 비교결과.json over its CSV in the same folder, avoiding double counts.
    Keep the latest measurement per project/model/score type/slide/account.
    """
    root = Path(account_folder).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f'계정별 폴더를 찾을 수 없습니다: {root}')
    if (root / '계정별').is_dir():
        root = root / '계정별'
    folders = sorted({p.parent for name in ('비교결과.json', '비교결과.csv') for p in root.rglob(name)})
    if not folders:
        raise FileNotFoundError(f'{root} 아래에 비교결과.json 또는 비교결과.csv가 없습니다.')
    latest = {}
    for folder in folders:
        json_file = folder / '비교결과.json'
        if json_file.is_file():
            payload = json.loads(json_file.read_text(encoding='utf-8-sig'))
            records = payload.get('measurements') if isinstance(payload, dict) else None
            if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
                raise ValueError(f'{json_file}: measurements 배열이 필요합니다.')
            if records and not any('ai_percentage' in row for row in records):
                raise ValueError(f'{json_file}: AI 점수가 포함된 새 비교결과 ZIP을 다운로드해주세요.')
        else:
            records = _csv_records(folder / '비교결과.csv')
        for record in records:
            if any(not record.get(key) for key in ('project_path', 'slide_id', 'user_id')):
                raise ValueError(f'{folder}: 프로젝트·슬라이드·계정 ID가 누락된 기록입니다.')
            kind = record.get('score_type', 'CPS')
            if kind not in ('CPS', 'TPS'):
                raise ValueError(f'{folder}: 지원하지 않는 점수 종류 {kind!r}')
            key = (record['project_path'], record.get('tissue_type') or '', kind,
                   record['slide_id'], record['user_id'])
            if key not in latest or _order(record) > _order(latest[key]):
                latest[key] = record
    return list(latest.values())


def calculate_account_pcc(account_folder):
    """Return per-account/project/model Grade-based (0/1/2) PCC dictionaries.

    Missing/non-finite/out-of-range scores are excluded as pairs, never zero-filled.
    Models, projects, and CPS/TPS are calculated separately.
    """
    groups = defaultdict(list)
    for record in load_latest_measurements(account_folder):
        key = (record['project_path'], record.get('tissue_type') or '',
               record.get('score_type', 'CPS'), record['user_id'])
        groups[key].append(record)
    results = []
    for (project, model, kind, uid), records in sorted(groups.items()):
        pairs = [(score_to_grade_code(row.get('percentage'), kind),
                  score_to_grade_code(row.get('ai_percentage'), kind)) for row in records]
        pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
        pcc = pearson_pcc([x for x, _ in pairs], [y for _, y in pairs])
        ccc = lin_ccc([x for x, _ in pairs], [y for _, y in pairs])
        account = max(records, key=_order)
        status = '계산 완료' if pcc is not None else '대응 슬라이드 2개 미만' if len(pairs) < 2 else '전문의 또는 AI Grade의 분산이 0'
        results.append({
            '프로젝트': project, '판별 모델': model, '점수 종류': kind,
            '계정 ID': uid, '로그인 ID': account.get('username') or '',
            '계정명': account.get('user_name') or '',
            '대상 슬라이드 수': len(records), '대응 슬라이드 수': len(pairs),
            '제외 슬라이드 수': len(records) - len(pairs), 'PCC 기준': 'Grade (0/1/2)', 'PCC': pcc, '상태': status,
            'CCC 기준': 'Grade (0/1/2)', 'CCC': ccc,
            'CCC 상태': '계산 완료' if ccc is not None else '대응 슬라이드 2개 미만' if len(pairs)<2 else 'Grade 분산과 평균 차이가 모두 0 (정의 불가)',
        })
    return results


def grade_majority_median(values, score_type='CPS'):
    """Grade 과반 → 해당 Grade 판독자 점수의 중앙값. 합의 없으면 None."""
    def band(value):
        upper = 50 if score_type == 'TPS' else 10
        return (f'{score_type} < 1' if value < 1 else
                f'1 ≤ {score_type} < {upper}' if value < upper else f'{score_type} ≥ {upper}')
    valid = [(index, _score(value)) for index, value in enumerate(values)]
    valid = [(index, value) for index, value in valid if value is not None]
    votes = Counter(band(value) for _, value in valid)
    winner = next((g for g, n in votes.items() if n > len(valid) / 2), None) if len(valid) >= 2 else None
    selected = [(index, value) for index, value in valid if winner is not None and band(value) == winner]
    return {'grade': winner, 'median': median([value for _, value in selected]) if selected else None,
            'selected_indices': [index for index, _ in selected], 'valid_count': len(valid),
            'votes': dict(votes)}


def calculate_consensus_pcc(account_folder):
    """Return (slide-level consensus steps, AI-vs-majority Grade PCC per model).

    Load the parent containing ALL intended reader folders. A single reader cannot
    establish consensus. Disagreeing stored AI scores are excluded, not averaged.
    """
    slides = defaultdict(list)
    for record in load_latest_measurements(account_folder):
        key = (record['project_path'], record.get('tissue_type') or '',
               record.get('score_type', 'CPS'), record['slide_id'])
        slides[key].append(record)
    rows, groups = [], defaultdict(list)
    for (project, model, kind, slide), records in sorted(slides.items()):
        records = sorted(records, key=lambda record: record['user_id'])
        consensus = grade_majority_median([row.get('percentage') for row in records], kind)
        available_ai = [_score(row.get('ai_percentage')) for row in records]
        available_ai = [value for value in available_ai if value is not None]
        ai_value = available_ai[0] if available_ai and max(available_ai)-min(available_ai) <= 1e-9 else None
        row = {'프로젝트': project, '판별 모델': model, '점수 종류': kind, '슬라이드 ID': slide,
               '판독자별 점수': '; '.join(f"{r.get('username') or r['user_id']}: {r.get('percentage')}" for r in records),
               'Grade 득표': '; '.join(f'{g}: {n}' for g, n in consensus['votes'].items()),
               '다수결 Grade': consensus['grade'],
               '중앙값 산출 계정': '; '.join(records[i].get('username') or records[i]['user_id'] for i in consensus['selected_indices']),
               '합의 CPS/TPS 중앙값': consensus['median'], 'AI 점수': ai_value,
               '합의 Grade 코드': score_to_grade_code(consensus['median'], kind),
               'AI Grade 코드': score_to_grade_code(ai_value, kind),
               '합의 상태': '과반 합의' if consensus['grade'] is not None else '합의 미성립(2인 미만 또는 과반 없음)',
               'AI 상태': '가용 결과 일치' if ai_value is not None else 'AI 점수 누락 또는 불일치'}
        rows.append(row)
        groups[(project, model, kind)].append(row)
    results = []
    for (project, model, kind), candidates in sorted(groups.items()):
        paired = [row for row in candidates if row['합의 CPS/TPS 중앙값'] is not None and row['AI 점수'] is not None]
        pcc = pearson_pcc([r['합의 Grade 코드'] for r in paired], [r['AI Grade 코드'] for r in paired])
        ccc = lin_ccc([r['합의 Grade 코드'] for r in paired], [r['AI Grade 코드'] for r in paired])
        results.append({'프로젝트': project, '판별 모델': model, '점수 종류': kind,
                        '비교 대상': 'AI Grade 대 판독자 다수결 Grade', 'PCC 기준': 'Grade (0/1/2)',
                        '대상 슬라이드 수': len(candidates), '대응 슬라이드 수': len(paired),
                        '제외 슬라이드 수': len(candidates)-len(paired), 'PCC': pcc,
                        'CCC 기준': 'Grade (0/1/2)', 'CCC': ccc,
                        'CCC 상태': '계산 완료' if ccc is not None else '대응 슬라이드 2개 미만' if len(paired)<2 else 'Grade 분산과 평균 차이가 모두 0 (정의 불가)',
                        '상태': '계산 완료' if pcc is not None else '대응 슬라이드 2개 미만' if len(paired)<2 else '합의 또는 AI Grade의 분산이 0'})
    return rows, results


def save_pcc_csv(results, output_path):
    """Write an Excel-compatible UTF-8 BOM CSV without changing source files."""
    if not results:
        raise ValueError('저장할 PCC 결과가 없습니다.')
    path = Path(output_path).expanduser()
    def safe(value):
        return "'" + value if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')) else value
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows({key: safe(value) for key, value in row.items()} for row in results)
    return path.resolve()
