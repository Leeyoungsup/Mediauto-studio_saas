"""Project comparison ZIPs containing Excel-compatible CSVs and per-account JSON."""
import csv
import io
import json
import re
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from app.comparison_statistics import (CALCULATION_RULES, build_reports, grade, positive, score)

KST = timezone(timedelta(hours=9))
HEADERS = ['프로젝트', '슬라이드', '슬라이드 ID', '판별 모델', '계정 ID', '로그인 ID', '계정명',
           'CPS (%)', 'CPS Grade', 'AI CPS (%)', 'AI CPS Grade',
           'TPS (%)', 'TPS Grade', 'AI TPS (%)', 'AI TPS Grade', '전문의 판독시간(초)',
           'AI 판독시간(초)', 'AI 시간 측정 기준', '측정 시각(KST)', '측정 ID']


def seconds(value):
    value = positive(value)
    return '' if value is None else round(value / 1000, 6)


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
        'percentage': record.get('percentage') if score(record.get('percentage')) is not None else None,
        'grade': record.get('grade'),
        'ai_percentage': record.get('ai_percentage') if score(record.get('ai_percentage')) is not None else None,
        'ai_grade': grade(record.get('ai_percentage'), score_type),
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
            item['ai_percentage'] if cps else '', item['ai_grade'] if cps else '',
            item['percentage'] if not cps else '', item['grade'] if not cps else '',
            item['ai_percentage'] if not cps else '', item['ai_grade'] if not cps else '',
            item['specialist_elapsed_seconds'], item['ai_elapsed_seconds'], basis,
            item['measured_at'], item['measurement_id'],
        ]])
    return output.getvalue().encode('utf-8-sig')


def report_csv(rows):
    output = io.StringIO(newline='')
    columns = list(dict.fromkeys(key for row in rows for key in row))
    writer = csv.writer(output)
    writer.writerow([csv_value(key) for key in columns])
    for row in rows:
        writer.writerow([csv_value(row.get(key)) for key in columns])
    return output.getvalue().encode('utf-8-sig')


def build_comparison_zip(records):
    items = [measurement(record) for record in records]
    reports = build_reports(items)
    groups = defaultdict(list)
    for item in items:
        groups[item['user_id']].append(item)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('전체_비교결과.csv', csv_bytes(items))
        for key, filename in [('slides','슬라이드별_종합결과.csv'),
                              ('metrics','PCC_CCC_성능지표.csv'),
                              ('times','판독시간_성능지표.csv'),
                              ('readers','판독자_목록.csv')]:
            archive.writestr(filename, report_csv(reports[key]))
        archive.writestr('성능지표_산출기준.csv', report_csv([{'항목':key,'산출 기준':value} for key,value in CALCULATION_RULES]))
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
                'schema_version': 2, 'measurements': results,
            }, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8'))
    return output.getvalue()
