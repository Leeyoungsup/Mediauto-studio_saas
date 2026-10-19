import csv
import io
import json
import zipfile
from datetime import datetime, timezone
from app.comparison_export import build_comparison_zip


def test_export_units_model_types_and_spreadsheet_safe_text():
    base={'_id':'run','project_path':'project','slide_id':'slide','filename':'=danger.svs',
          'user_id':'one','user_name':'../전문의','username':'=name','tissue_type':'Stomach',
          'score_type':'CPS','percentage':12.5,'grade':'CPS ≥ 10',
          'specialist_elapsed_ms':123456,'ai_result_elapsed_ms':1234.5,
          'ai_timing_basis':'slide_entry_to_display','dt_created_at':datetime(2026,10,19,tzinfo=timezone.utc)}
    tps={**base,'_id':'tps','score_type':'TPS','percentage':55,'grade':'TPS ≥ 50','tissue_type':'Lung'}
    with zipfile.ZipFile(io.BytesIO(build_comparison_zip([base,tps]))) as archive:
        assert all('..' not in name and not name.startswith('/') for name in archive.namelist())
        rows=list(csv.DictReader(io.StringIO(archive.read('전체_비교결과.csv').decode('utf-8-sig'))))
        assert rows[0]['슬라이드']=="'=danger.svs"
        assert rows[0]['AI 판독시간(초)']=='1.2345'
        assert rows[0]['전문의 판독시간(초)']=='123.456'
        assert rows[0]['측정 시각(KST)'].endswith('09:00:00+09:00')
        assert rows[1]['CPS (%)']=='' and rows[1]['TPS (%)']=='55'
        result=json.loads(archive.read(next(name for name in archive.namelist() if name.endswith('.json'))))
        assert result['measurements'][0]['filename']=='=danger.svs'


def test_account_folders_use_names_without_hashes_and_keep_collisions_separate():
    records = [{'_id':str(i), 'user_id':str(i), 'username':name,
                'project_path':'project', 'slide_id':'slide', 'filename':'slide.svs'}
               for i,name in enumerate(['reader', 'reader', 'READER'])]
    with zipfile.ZipFile(io.BytesIO(build_comparison_zip(records))) as archive:
        names = archive.namelist()
        assert '계정별/reader/비교결과.json' in names
        assert '계정별/reader (2)/비교결과.json' in names
        assert '계정별/READER (3)/비교결과.json' in names
        accounts = [json.loads(archive.read(name))['measurements'][0]['user_id']
                    for name in names if name.endswith('.json')]
        assert set(accounts) == {'0','1','2'}
