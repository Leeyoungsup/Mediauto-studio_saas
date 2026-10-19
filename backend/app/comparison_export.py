"""Project comparison ZIPs containing Excel-compatible CSVs and per-account JSON."""
import csv
import io
import json
import re
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
HEADERS = ['프로젝트', '슬라이드', '슬라이드 ID', '판별 모델', '계정 ID', '로그인 ID', '계정명',
           'CPS (%)', 'CPS Grade', 'TPS (%)', 'TPS Grade', '전문의 판독시간(초)',
           'AI 판독시간(초)', 'AI 시간 측정 기준', '측정 시각(KST)', '측정 ID']


def seconds(value):
    return '' if value is None else round(float(value) / 1000, 6)


def csv_value(value):
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


def measurement(record):
    score_type = record.get('score_type', 'CPS')
    date = record.get('dt_created_at')
    if isinstance(date, str):
        date = datetime.fromisoformat(date.replace('Z', '+00:00'))
    if date is not None:
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        date = date.astimezone(KST).isoformat()
    basis = record.get('ai_timing_basis')
    return {
        'measurement_id': record['_id'], 'project_path': record['project_path'],
        'slide_id': record['slide_id'], 'filename': record['filename'],
        'tissue_type': record.get('tissue_type'), 'score_type': score_type,
        'user_id': record['user_id'], 'username': record.get('username', ''),
        'user_name': record.get('user_name', ''),
        'percentage': record.get('percentage'), 'grade': record.get('grade'),
        'specialist_elapsed_seconds': seconds(record.get('specialist_elapsed_ms')),
        'ai_elapsed_seconds': seconds(record.get('ai_result_elapsed_ms')),
        'ai_timing_basis': basis, 'measured_at': date,
    }


def csv_bytes(items):
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(HEADERS)
    for item in items:
        cps = item['score_type'] == 'CPS'
        basis = {'slide_entry_to_display': '슬라이드 입장부터 그리기 완료',
                 'request_to_display': '결과 요청부터 표시 완료'}.get(item['ai_timing_basis'], '')
        writer.writerow([csv_value(value) for value in [
            item['project_path'], item['filename'], item['slide_id'], item['tissue_type'],
            item['user_id'], item['username'], item['user_name'],
            item['percentage'] if cps else '', item['grade'] if cps else '',
            item['percentage'] if not cps else '', item['grade'] if not cps else '',
            item['specialist_elapsed_seconds'], item['ai_elapsed_seconds'], basis,
            item['measured_at'], item['measurement_id'],
        ]])
    return output.getvalue().encode('utf-8-sig')


def build_comparison_zip(records):
    items = [measurement(record) for record in records]
    groups = defaultdict(list)
    for item in items:
        groups[item['user_id']].append(item)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('전체_비교결과.csv', csv_bytes(items))
        used_names = set()
        for user_id, results in sorted(groups.items()):
            label = results[-1]['username'] or results[-1]['user_name'] or 'account'
            label = re.sub(r'[^\w가-힣.-]+', '_', label).strip('._')[:60] or 'account'
            base = label
            suffix = 2
            while label.casefold() in used_names:
                label = f'{base} ({suffix})'; suffix += 1
            used_names.add(label.casefold())
            directory = f'계정별/{label}'
            archive.writestr(f'{directory}/비교결과.csv', csv_bytes(results))
            archive.writestr(f'{directory}/비교결과.json', json.dumps({
                'schema_version': 1, 'measurements': results,
            }, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8'))
    return output.getvalue()
