import csv
import io
import json
import math
import zipfile
from datetime import datetime,timedelta,timezone

import pytest
from app.comparison_export import build_comparison_zip,measurement
from app.comparison_statistics import agreement,build_reports,reader_code


def record(slide,user,value,ai=10,doctor_ms=10000,ai_ms=1000,**changes):
    return {'_id':f'{slide}-{user}','project_path':'project','slide_id':slide,'filename':slide+'.svs',
            'user_id':user,'username':user,'user_name':'Reader '+user,'tissue_type':'Stomach','score_type':'CPS',
            'percentage':value,'grade':'ignored legacy grade','ai_percentage':ai,'ai_grade':None,
            'specialist_elapsed_ms':doctor_ms,'ai_result_elapsed_ms':ai_ms,
            'ai_timing_basis':'slide_entry_to_display','dt_created_at':datetime(2026,10,20,tzinfo=timezone.utc),**changes}


def reports(records):return build_reports([measurement(row) for row in records])
def read_csv(archive,name):return list(csv.DictReader(io.StringIO(archive.read(name).decode('utf-8-sig'))))


def test_consensus_cps_uses_only_majority_grade_readers_median():
    records=[record('one','a',1,ai=4),record('one','b',3,ai=4),record('one','c',80,ai=4)]
    data=reports(records);row=data['slides'][0]
    assert row['판독자 합의 CPS 중앙값 (%)']==2
    assert row['판독자 다수결 CPS Grade']=='1 ≤ CPS < 10'
    assert row['AI CPS (%)']==4 and row['AI CPS Grade']=='1 ≤ CPS < 10'
    assert row['A 점수']==1 and row['B 점수']==3 and row['C 점수']==80
    assert row['A 전문의 판독시간(초)']==10 and row['A AI 판독시간(초)']==1
    assert [r['계정 ID'] for r in data['readers']]==['a','b','c']
    assert data['metrics'][0]['Grade 일치율(%)']==100


def test_no_majority_leaves_consensus_score_and_grade_blank():
    data=reports([record('one','a',0,ai=10),record('one','b',5,ai=10),record('one','c',25,ai=10)])
    row=data['slides'][0]
    assert row['판독자 합의 CPS 중앙값 (%)'] is None and row['판독자 다수결 CPS Grade'] is None
    assert '합의 미성립' in row['Grade 합의 상태']
    metric=data['metrics'][0]
    assert metric['대응 슬라이드 수']==0 and metric['Grade 대응 슬라이드 수']==0
    assert metric['Grade 일치율(%)'] is None


def test_latest_only_for_statistics_but_all_history_kept_in_export():
    old=record('one','a',99,_id='old')
    latest=record('one','a',2,_id='new',dt_created_at=old['dt_created_at']+timedelta(seconds=1))
    records=[latest,record('one','b',4),old]
    data=reports(records)
    assert data['slides'][0]['판독자 합의 CPS 중앙값 (%)']==3
    assert data['slides'][0]['유효 점수 수']==2
    with zipfile.ZipFile(io.BytesIO(build_comparison_zip(records))) as archive:
        assert len(read_csv(archive,'전체_비교결과.csv'))==3
        assert len(read_csv(archive,'슬라이드별_종합결과.csv'))==1
        assert len(json.loads(archive.read('계정별/a/비교결과.json'))['measurements'])==2


def test_pcc_ccc_and_errors_against_hand_computed_population_moments():
    pairs=[(0,1,'CPS < 1','CPS < 1'),(1,2,'1 ≤ CPS < 10','CPS ≥ 10'),(2,3,'CPS ≥ 10','CPS ≥ 10')]
    result=agreement(pairs)
    assert result['PCC']==pytest.approx(0.8660254)
    assert result['CCC']==pytest.approx(0.8)
    assert result['MAE(점수)']==1 and result['RMSE(점수)']==1
    assert result['편향(AI-참조, 점수)']==1
    assert result['Grade 일치율(%)']==pytest.approx(200/3)


@pytest.mark.parametrize('pairs,pcc,ccc',[
    ([],None,None), ([(1,1,None,None)],None,None),
    ([(1,1,None,None),(1,1,None,None)],None,None),
    ([(1,2,None,None),(1,2,None,None)],None,None),
    ([(0,2,'CPS < 1','CPS ≥ 10'),(1,1,'1 ≤ CPS < 10','1 ≤ CPS < 10'),(2,0,'CPS ≥ 10','CPS < 1')],-1,-1),
])
def test_undefined_correlations_are_blank_not_fake_perfect_scores(pairs,pcc,ccc):
    result=agreement(pairs)
    assert result['PCC']==pcc and result['CCC']==ccc


def test_multi_slide_consensus_and_per_reader_metrics_remain_separate():
    records=[]
    for slide,x in [('one',1),('two',3),('three',6)]:
        records.extend([record(slide,'a',x,ai=x+1),record(slide,'b',x+2,ai=x+1)])
    data=reports(records)
    consensus=data['metrics'][0]
    assert consensus['대응 슬라이드 수']==3 and consensus['PCC'] is None and consensus['CCC'] is None
    assert len(data['metrics'])==3
    for individual in data['metrics'][1:]:
        assert individual['대응 슬라이드 수']==3 and individual['MAE(점수)']==1


def test_disagreeing_ai_scores_and_single_readers_excluded_only_from_consensus_metrics():
    data=reports([record('one','a',1,ai=1),record('one','b',3,ai=5),record('two','a',5,ai=5)])
    one=next(row for row in data['slides'] if row['슬라이드 ID']=='one')
    assert one['AI CPS (%)'] is None and '불일치' in one['AI 결과 상태']
    assert data['metrics'][0]['대응 슬라이드 수']==0
    assert data['metrics'][0]['제외 슬라이드 수']==2
    assert next(row for row in data['metrics'] if row['계정 ID']=='a')['대응 슬라이드 수']==2


def test_time_ratio_uses_matched_sums_not_mean_of_ratios_and_never_json_read_time():
    data=reports([record('one','a',5,doctor_ms=10000,ai_ms=1000),
                  record('two','a',6,doctor_ms=90000,ai_ms=18000),
                  record('three','a',7,doctor_ms=10000,ai_ms=None,ai_json_elapsed_ms=1)])
    total=data['times'][0]
    assert total['집계 대상'].startswith('전체') and total['대응 평가 수']==2
    assert total['제외 평가 수']==1
    assert total['전체 판독시간 상승률(요청식, %)']==19
    assert total['판독시간 절감률(%)']==81
    assert total['속도향상 배수(전문의/AI)']==pytest.approx(100/19)


def test_timing_bases_and_tps_breast_and_stomach_never_pooled():
    data=reports([record('one','a',5),record('one','b',5,ai_timing_basis='request_to_display'),
                  record('two','a',5,tissue_type='Breast'),
                  record('three','a',55,tissue_type='Lung',score_type='TPS',ai=60)])
    assert len(data['slides'])==3
    stomach=next(row for row in data['slides'] if row['판별 모델']=='Stomach')
    assert stomach['대응 평가 수']==0 and '혼합' in stomach['시간 집계 기준']
    totals=[row for row in data['times'] if row['집계 대상'].startswith('전체')]
    assert len(totals)==4
    lung=next(row for row in data['slides'] if row['판별 모델']=='Lung')
    assert lung['판독자 합의 CPS 중앙값 (%)'] is None and lung['AI TPS Grade']=='TPS ≥ 50'


def test_export_has_ai_fields_reports_utf8_and_safe_dynamic_text():
    records=[record('one','a',5,ai=12.5,filename='=unsafe.svs'),
             record('one','b',7,ai=12.5,filename='=unsafe.svs')]
    with zipfile.ZipFile(io.BytesIO(build_comparison_zip(records))) as archive:
        rows=read_csv(archive,'전체_비교결과.csv')
        assert rows[0]['AI CPS (%)']=='12.5' and rows[0]['AI CPS Grade']=='CPS ≥ 10'
        assert rows[0]['AI TPS (%)']==''
        slides=read_csv(archive,'슬라이드별_종합결과.csv')
        assert slides[0]['슬라이드'].startswith("'")
        for name in ['PCC_CCC_성능지표.csv','판독시간_성능지표.csv','판독자_목록.csv','성능지표_산출기준.csv']:
            assert archive.read(name).startswith(b'\xef\xbb\xbf')
        account=json.loads(archive.read('계정별/a/비교결과.json'))
        assert account['measurements'][0]['ai_grade']=='CPS ≥ 10'


def test_missing_nan_scores_or_times_do_not_become_zero_or_break_json():
    records=[record('one','a',float('nan'),ai=float('nan'),ai_ms=float('nan')),
             record('one','b',5,ai=5)]
    data=reports(records)
    assert data['slides'][0]['유효 점수 수']==1
    assert data['metrics'][0]['대응 슬라이드 수']==0
    build_comparison_zip(records)
    assert reader_code(25)=='Z' and reader_code(26)=='AA'
