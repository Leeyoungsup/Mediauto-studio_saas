"""Descriptive AI/reader agreement and matched reading-time comparisons."""
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import fmean, median

TIMING_LABELS = {
    'slide_entry_to_display': '슬라이드 입장부터 그리기 완료',
    'request_to_display': '결과 요청부터 표시 완료(이전 기준)',
}


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def score(value):
    value = number(value)
    return value if value is not None and 0 <= value <= 100 else None


def grade(value, score_type):
    value = score(value)
    if value is None:
        return None
    upper = 50 if score_type == 'TPS' else 10
    if value < 1:
        return f'{score_type} < 1'
    if value < upper:
        return f'1 ≤ {score_type} < {upper}'
    return f'{score_type} ≥ {upper}'


def grade_code(label):
    """Ordered score-band encoding used for Grade-based PCC."""
    return {'CPS < 1':0, '1 ≤ CPS < 10':1, 'CPS ≥ 10':2,
            'TPS < 1':0, '1 ≤ TPS < 50':1, 'TPS ≥ 50':2}.get(label)


def positive(value):
    value = number(value)
    return value if value is not None and value > 0 else None


def rounded(value):
    return round(value, 8) if value is not None else None


def reader_code(index):
    result = ''
    index += 1
    while index:
        index, remainder = divmod(index-1, 26)
        result = chr(65+remainder)+result
    return result


def latest_measurements(items):
    def order(item):
        date = item.get('measured_at')
        try:
            date = datetime.fromisoformat(date) if date else datetime.min.replace(tzinfo=timezone.utc)
            date = date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date
        except (TypeError, ValueError):
            date = datetime.min.replace(tzinfo=timezone.utc)
        return date, str(item['measurement_id'])
    latest = {}
    for item in sorted(items, key=order):
        key = (item['project_path'], item['slide_id'], item['tissue_type'], item['score_type'], item['user_id'])
        latest[key] = item
    return list(latest.values())


def agreement(pairs):
    n = len(pairs)
    result = {'대응 슬라이드 수':n, 'PCC 기준':'Grade (0/1/2)', 'PCC 대응 슬라이드 수':0, 'PCC':None, 'PCC 상태':'Grade 대응 슬라이드 2개 미만',
              'CCC 기준':'Grade (0/1/2)', 'CCC 대응 슬라이드 수':0,
              'CCC':None, 'CCC 상태':'Grade 대응 슬라이드 2개 미만',
              'MAE(점수)':None, 'RMSE(점수)':None, '편향(AI-참조, 점수)':None,
              'Grade 대응 슬라이드 수':0, 'Grade 일치율(%)':None}
    if not n:
        return result
    x, y = [p[0] for p in pairs], [p[1] for p in pairs]
    delta = [b-a for a,b in zip(x,y)]
    result.update({'MAE(점수)':rounded(fmean(abs(d) for d in delta)),
                   'RMSE(점수)':rounded(math.sqrt(fmean(d*d for d in delta))),
                   '편향(AI-참조, 점수)':rounded(fmean(delta))})
    grades = [(p[2],p[3]) for p in pairs if p[2] is not None and p[3] is not None]
    result['Grade 대응 슬라이드 수'] = len(grades)
    if grades:
        result['Grade 일치율(%)'] = rounded(100*sum(a==b for a,b in grades)/len(grades))
    coded = [(grade_code(a),grade_code(b)) for a,b in grades]
    coded = [(a,b) for a,b in coded if a is not None and b is not None]
    result['PCC 대응 슬라이드 수'] = len(coded)
    result['CCC 대응 슬라이드 수'] = len(coded)
    if len(coded) >= 2:
        gx, gy = fmean(a for a,_ in coded), fmean(b for _,b in coded)
        sx = math.fsum((a-gx)**2 for a,_ in coded)
        sy = math.fsum((b-gy)**2 for _,b in coded)
        covariance_grade = math.fsum((a-gx)*(b-gy) for a,b in coded)
        if sx > 0 and sy > 0:
            result.update({'PCC':rounded(max(-1,min(1,covariance_grade/math.sqrt(sx*sy)))), 'PCC 상태':'계산 완료'})
        else:
            result['PCC 상태'] = '참조 또는 AI Grade의 분산이 0'
        denominator = (sx+sy)/len(coded)+(gx-gy)**2
        if denominator > 0:
            result.update({'CCC':rounded(max(-1,min(1,2*covariance_grade/len(coded)/denominator))), 'CCC 상태':'계산 완료'})
        else:
            result['CCC 상태'] = 'Grade 분산과 평균 차이가 모두 0 (정의 불가)'
    return result


def matched_times(items, basis):
    pairs = []
    for item in items:
        specialist = positive(item['specialist_elapsed_seconds'])
        ai = positive(item['ai_elapsed_seconds'])
        if item.get('ai_timing_basis') == basis and specialist is not None and ai is not None:
            pairs.append((specialist,ai,item['slide_id']))
    return pairs


def time_summary(pairs):
    if not pairs:
        return {'대응 평가 수':0,'슬라이드 수':0,'전문의 판독시간 합계(초)':None,'AI 판독시간 합계(초)':None,
                '전문의 판독시간 평균(초)':None,'AI 판독시간 평균(초)':None,
                '전체 판독시간 상승률(요청식, %)':None,'판독시간 절감률(%)':None,'속도향상 배수(전문의/AI)':None}
    specialist = math.fsum(p[0] for p in pairs)
    ai = math.fsum(p[1] for p in pairs)
    ratio = 100*ai/specialist
    return {'대응 평가 수':len(pairs),'슬라이드 수':len({p[2] for p in pairs}),
            '전문의 판독시간 합계(초)':rounded(specialist),'AI 판독시간 합계(초)':rounded(ai),
            '전문의 판독시간 평균(초)':rounded(specialist/len(pairs)),
            'AI 판독시간 평균(초)':rounded(ai/len(pairs)),
            '전체 판독시간 상승률(요청식, %)':rounded(ratio),
            '판독시간 절감률(%)':rounded(100-ratio),'속도향상 배수(전문의/AI)':rounded(specialist/ai)}


def build_reports(items):
    latest = latest_measurements(items)
    accounts = {}
    for item in sorted(latest, key=lambda i:(i.get('measured_at') or '',i['measurement_id'])):
        accounts[item['user_id']] = item
    readers = sorted(accounts, key=lambda uid:((accounts[uid]['username'] or accounts[uid]['user_name'] or uid).casefold(), uid))
    codes = {uid:reader_code(i) for i,uid in enumerate(readers)}
    reader_rows = [{'판독자':codes[uid],'계정 ID':uid,'로그인 ID':accounts[uid]['username'],
                    '계정명':accounts[uid]['user_name']} for uid in readers]
    slides, groups = defaultdict(list), defaultdict(list)
    for item in latest:
        key = (item['project_path'],item['tissue_type'] or '',item['score_type'])
        slides[(*key,item['slide_id'])].append(item)
        groups[key].append(item)
    slide_rows, summaries = [], defaultdict(list)
    for key, evaluations in sorted(slides.items()):
        project,tissue,score_type,slide_id = key
        valid = [e for e in evaluations if score(e['percentage']) is not None]
        percentages = [score(e['percentage']) for e in valid]
        votes = Counter(grade(v,score_type) for v in percentages)
        majority = next((g for g,n in votes.items() if n > len(valid)/2),None)
        if len(valid)<2:
            majority = None
        ai_values = [score(e['ai_percentage']) for e in evaluations if score(e['ai_percentage']) is not None]
        ai_consistent = bool(ai_values) and max(ai_values)-min(ai_values)<=1e-9
        ai_value = ai_values[0] if ai_consistent else None
        majority_values = [v for v in percentages if grade(v,score_type)==majority] if majority else []
        reference = median(majority_values) if majority_values else None
        row = {'프로젝트':project,'슬라이드':evaluations[-1]['filename'],'슬라이드 ID':slide_id,
               '판별 모델':tissue,'점수 종류':score_type,'평가 계정 수':len(evaluations),
               '유효 점수 수':len(valid),'프로젝트 참여 계정 수':len(readers)}
        by_reader = {e['user_id']:e for e in evaluations}
        for uid in readers:
            item = by_reader.get(uid,{})
            prefix = codes[uid]
            value = score(item.get('percentage'))
            doctor = positive(item.get('specialist_elapsed_seconds'))
            ai_time = positive(item.get('ai_elapsed_seconds'))
            row.update({f'{prefix} 점수':value,f'{prefix} Grade':grade(value,score_type),
                        f'{prefix} 전문의 판독시간(초)':doctor,f'{prefix} AI 판독시간(초)':ai_time,
                        f'{prefix} AI 시간 기준':TIMING_LABELS.get(item.get('ai_timing_basis'),'미확인' if item else ''),
                        f'{prefix} 측정 ID':item.get('measurement_id','')})
        grade_status = '과반 합의' if majority is not None else '1인 평가(합의 불가)' if len(valid)==1 else '유효 평가 없음' if not valid else '과반 없음(합의 미성립)'
        ai_status = '점수 불일치(종합 지표 제외)' if ai_values and not ai_consistent else '없음' if not ai_values else '일치' if len(ai_values)==len(evaluations) else '일부 누락; 가용 결과 일치'
        row.update({'다수 Grade 판독자 CPS/TPS 중앙값':rounded(reference),'중앙값 산출 판독자 수':len(majority_values),'Grade 다수결 결과':majority,'Grade 합의 상태':grade_status,
                    '중앙값 산출 판독자':'; '.join(codes[e['user_id']] for e in valid if majority is not None and grade(e['percentage'],score_type)==majority),
                    'Grade 득표':'; '.join(f'{g}: {votes[g]}' for g in sorted(votes)),
                    'AI 점수':ai_value,'AI Grade':grade(ai_value,score_type),'AI 결과 상태':ai_status})
        for kind in ('CPS','TPS'):
            row[f'판독자 합의 {kind} 중앙값 (%)'] = rounded(reference) if score_type==kind else None
            row[f'판독자 다수결 {kind} Grade'] = majority if score_type==kind else None
            row[f'AI {kind} (%)'] = ai_value if score_type==kind else None
            row[f'AI {kind} Grade'] = grade(ai_value,kind) if score_type==kind else None
        bases = {e['ai_timing_basis'] for e in evaluations
                 if e.get('ai_timing_basis') in TIMING_LABELS and positive(e['specialist_elapsed_seconds']) and positive(e['ai_elapsed_seconds'])}
        basis = next(iter(bases)) if len(bases)==1 else None
        summary = time_summary(matched_times(evaluations,basis)) if basis else time_summary([])
        row.update({'시간 집계 기준':TIMING_LABELS.get(basis,'혼합(기준별 시간 통계 참조)' if len(bases)>1 else '유효 대응 시간 없음'),**summary})
        slide_rows.append(row)
        summaries[key[:3]].append({'reference':reference,'ai':ai_value,'grade':majority,
                                  'ai_grade':grade(ai_value,score_type),'readers':len(valid)})
    metric_rows,time_rows = [],[]
    for key,evaluations in sorted(groups.items()):
        project,tissue,score_type = key
        common = {'프로젝트':project,'판별 모델':tissue,'점수 종류':score_type}
        candidates = summaries[key]
        pairs = [(s['reference'],s['ai'],s['grade'],s['ai_grade']) for s in candidates
                 if s['readers']>=2 and s['reference'] is not None and s['ai'] is not None]
        metric_rows.append({**common,'비교 대상':'AI 대 판독자 종합(Grade 다수결/해당 판독자 중앙값)','판독자':'종합','계정 ID':'',
                            '대상 슬라이드 수':len(candidates),'제외 슬라이드 수':len(candidates)-len(pairs),
                            **agreement(pairs)})
        for uid in readers:
            own = [e for e in evaluations if e['user_id']==uid]
            if not own:continue
            pairs = [(score(e['percentage']),score(e['ai_percentage']),grade(e['percentage'],score_type),grade(e['ai_percentage'],score_type))
                     for e in own if score(e['percentage']) is not None and score(e['ai_percentage']) is not None]
            metric_rows.append({**common,'비교 대상':'AI 대 개별 판독자','판독자':codes[uid],'계정 ID':uid,
                                '대상 슬라이드 수':len(own),'제외 슬라이드 수':len(own)-len(pairs),**agreement(pairs)})
        scopes = [('전체(계정별 최신 평가 합산)','',evaluations)]
        scopes.extend((codes[uid],uid,[e for e in evaluations if e['user_id']==uid]) for uid in readers
                      if any(e['user_id']==uid for e in evaluations))
        for label,uid,scope in scopes:
            bases = sorted({e.get('ai_timing_basis') or '' for e in scope})
            for basis in bases:
                subset = [e for e in scope if (e.get('ai_timing_basis') or '')==basis]
                pairs = matched_times(subset,basis) if basis in TIMING_LABELS else []
                time_rows.append({**common,'집계 대상':label,'계정 ID':uid,
                                  'AI 시간 기준':TIMING_LABELS.get(basis,'미확인(집계 제외)'),
                                  '대상 평가 수':len(subset),'제외 평가 수':len(subset)-len(pairs),**time_summary(pairs)})
    return {'slides':slide_rows,'metrics':metric_rows,'times':time_rows,'readers':reader_rows}


CALCULATION_RULES = [
    ('원본 이력','전체_비교결과 및 계정별 파일에는 반복 측정을 포함한 모든 저장 이력을 수록'),
    ('종합·지표 대상','프로젝트·슬라이드·모델·점수종류별 계정당 최신 기록만 사용. 같은 시각은 측정 ID로 결정'),
    ('판독자 표기','로그인 ID/계정명 순으로 A,B,C...를 부여. 판독자_목록.csv에서 실제 계정 확인'),
    ('CPS/TPS 합의 중앙값','먼저 Grade 과반 다수결 후, 다수 Grade에 속한 판독자 점수만의 중앙값. 짝수이면 가운데 두 점수의 평균. 합의 미성립이면 공란'),
    ('Grade 다수결','개별 판독자 Grade의 과반(50% 초과)을 사용. 1인·동률·과반 없음은 합의 미성립'),
    ('AI Grade','저장된 AI 점수로 판독자와 동일한 점수구간을 계산. CPS 1/10, TPS 1/50 경계값'),
    ('AI 종합 점수','같은 슬라이드의 최신 계정별 AI 점수가 일치할 때만 사용. 불일치 시 임의 선택 없이 종합 지표에서 제외'),
    ('종합 참조','2인 이상 유효 평가와 Grade 과반 합의가 있는 슬라이드의 다수 Grade 판독자 중앙값을 사용. 합의 미성립은 종합 점수·Grade 지표에서 제외'),
    ('개별 지표','각 계정의 최신 전문의 점수와 해당 측정에 저장된 AI 점수를 슬라이드별로 대응'),
    ('점수 집계 구분','프로젝트·판별모델·CPS/TPS별로 분리. 서로 다른 점수종류를 합산하지 않음'),
    ('PCC','Grade를 0/1/2로 인코딩하여 Pearson r 계산. CPS: <1→0, 1이상10미만→1, 10이상→2. TPS: <1→0, 1이상50미만→1, 50이상→2. 종합은 다수결 Grade 대 AI Grade, 개별은 판독자 Grade 대 AI Grade'),
    ('CCC','PCC와 같은 Grade 0/1/2 기준 Lin CCC=2 cov(x,y)/(var(x)+var(y)+(평균x-평균y)^2). 분산·공분산은 1/N 기준. 종합은 다수결 Grade 대 AI Grade'),
    ('계산 불가','대응 슬라이드 2개 미만, PCC 분산 0, CCC 분모 0은 공란과 사유로 표시'),
    ('오차 지표','MAE=평균|AI-참조|, RMSE=sqrt(평균(AI-참조)^2), 편향=평균(AI-참조). 단위는 점수 차이'),
    ('시간 집계','계정별 최신 평가 중 전문의와 AI 판독시간이 모두 양수인 대응 평가만 합산. 시간 기준별로 분리'),
    ('시간 상승률(요청식)','100×ΣAI시간/Σ전문의시간. 개별 비율의 단순평균이 아닌 전체 합계의 비율. 시간 사용 비율이므로 작을수록 AI 시간이 짧음'),
    ('시간 절감률','100-요청식 시간 비율. 음수이면 AI 시간이 더 오래 걸림'),
    ('속도향상 배수','Σ전문의시간/ΣAI시간'),
    ('시간 측정 범위','현재 AI 시간은 슬라이드 입장·초기 타일 준비·JSON 전송/처리·별도 캔버스 그리기 완료까지. 모델 추론 시간은 포함하지 않음'),
    ('이전 시간','request_to_display는 이전 요청 기준으로 별도 집계. JSON 읽기 시간만 있는 기록은 판독시간 통계에서 제외'),
    ('결측값','누락·유효하지 않은 점수/시간은 0으로 대체하지 않고 대응 지표에서 제외'),
    ('표본 해석','종합 참조는 제출 판독자들의 기술적 집계이며 독립적인 확정 정답을 의미하지 않음. 표본 수와 제외 수를 함께 제공'),
    ('PCC 근거','https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.pearsonr.html'),
    ('CCC 근거','Lin LI. Biometrics 1989;45:255-268. https://pubmed.ncbi.nlm.nih.gov/2720055/'),
]
