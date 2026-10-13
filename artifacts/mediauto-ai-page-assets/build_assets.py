"""Prepare existing redacted UI captures and browser-captured detail frames.
No production login, AI execution, or data mutation. Run with Playwright installed.
"""
from pathlib import Path
import json, shutil, hashlib, datetime
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / 'figure/manual-redacted'
SCENES = [
 ('01-overview','통합 AI 작업 공간','슬라이드와 AI 분석 결과를 한 화면에서',[
 ('05-ai-viewer/10-analysis-result-multi-view.png','multi-view','여러 분석 결과 함께 보기','full'),
 ('05-ai-viewer/07-same-case-slides.png','same-case','같은 케이스의 슬라이드 연결','full'),
 ('05-ai-viewer/08-multi-view.png','viewer','다중 화면 비교','viewer')], '전체 화면에서 시작해 분석 화면을 확대하고, 케이스 연결 화면으로 전환합니다.'),
 ('02-quanti-he','Quanti HE','H&E 조직·세포 분석과 공간 분포',[
 ('06-ai-analysis/08-quanti-he-results.png','he-result','H&E 분석 결과','viewer'),
 ('06-ai-analysis/09-quanti-he-spatial-heatmap.png','he-spatial','공간 분포 확인','modal')], '분석 결과를 천천히 확대하고 공간 분포 화면을 이어서 보여줍니다. 서로 다른 캡처를 같은 영역의 전후 결과로 표현하지 않습니다.'),
 ('03-quanti-ihc','Quanti IHC','마커별 세포 분석과 정량 지표',[
 ('06-ai-analysis/11-quanti-ihc-her2-results.png','her2','HER2 세포 분석','viewer'),
 ('06-ai-analysis/10-quanti-ihc-erpr-results.png','er-pr','ER/PR 세포 분석','viewer'),
 ('06-ai-analysis/04-result-allred-analysis.png','allred','Allred 결과 확인','modal'),
 ('06-ai-analysis/14-quanti-ihc-ki67-results.png','ki67','Ki-67 결과 확인','viewer')], 'HER2 → ER/PR → Ki-67 탭 전환 형태로 구성합니다. 점수는 실제 화면 값 그대로 사용합니다.'),
 ('04-quanti-pdl1','Quanti PD-L1','PD-L1 세포 분류와 CPS·TPS 결과',[
 ('06-ai-analysis/15-quanti-pdl1-results.png','pdl1-cells','PD-L1 세포 결과','viewer'),
 ('06-ai-analysis/16-quanti-pdl1-cps-tps-analysis.png','pdl1-score','CPS·TPS 분석 화면','modal')], '세포 결과에서 점수 화면으로 전환합니다. 최근 공개 평가 문서의 범위와 다르므로 페이지에 포함할지는 별도 결정합니다.'),
 ('05-virtual-stain','VS IHC','IHC와 Virtual H&E를 같은 위치에서 비교',[
 ('06-ai-analysis/07-virtual-stain-split-view.png','split-view','IHC | Virtual H&E','viewer')], '실제 분할 화면을 확대해 두 영상을 강조합니다. 현재 자료는 고정된 분할 화면 한 장이므로 경계를 움직이는 실제 비교 슬라이더에는 동일 위치의 원본·생성 영상 별도 캡처가 필요합니다.'),
 ('06-expert-review','전문가 결과 검토','세포 단위 확인과 수정',[
 ('06-ai-analysis/11-quanti-ihc-her2-results.png','result','분석 결과 확인','viewer'),
 ('06-ai-analysis/12-quanti-ihc-her2-single-cell-edit.png','single-cell','세포 하나씩 검토','viewer'),
 ('06-ai-analysis/13-quanti-ihc-her2-batch-cell-edit.png','batch-edit','여러 세포 함께 편집','viewer'),
 ('06-ai-analysis/03-result-class-distribution.png','class-distribution','세포 클래스 분포 확인','modal')], '전체 결과 → 단일 세포 편집 → 다중 세포 편집 화면으로 전환합니다. 실제 저장 완료·점수 변경을 보여주려면 추가 촬영이 필요합니다.'),
 ('07-ai-annotation','AI 보조 라벨링과 검수','조직·세포 주석에서 패치 검수까지',[
 ('07-tissue-annotation/01-annotation-viewer.png','tissue','조직 주석','viewer'),
 ('08-cell-annotation/01-annotation-settings.png','settings','라벨링 작업 설정','full'),
 ('08-cell-annotation/02-patch-list.png','patch-workflow','패치별 작업 상태','full'),
 ('08-cell-annotation/03-bounding-box-display.png','bbox','세포 Bounding Box 표시','viewer'),
 ('08-cell-annotation/04-point-display.png','point','세포 Point 표시','viewer')], '조직 주석과 Cell 작업을 별도 단계로 설명합니다. 패치 목록 → BBox → Point 화면으로 전환하고, 작성·검수·종결 상태를 설명합니다. AI 보조 실행 전후는 추가 촬영 대상입니다.'),
 ('08-workflow','프로젝트와 자동화','분석 설정과 결과 활용',[
 ('03-project/02-edit-project-settings.png','project-settings','프로젝트 분석 설정','full'),
 ('11-admin/05-system-settings.png','background-workers','백그라운드 작업 설정','full'),
 ('09-data-linkage/01-case-clinical-information.png','case-linkage','케이스 정보 연결','full'),
 ('06-ai-analysis/06-pdf-analysis-report.png','report','분석 보고서','report')], '프로젝트 설정 → 백그라운드 작업 → 케이스 정보 → 결과 보고서 순서로 설명합니다. 정지 화면을 실제 작업 진행률로 표현하지 않습니다.')
]
CROPS = {'modal': {'x':0,'y':0,'width':960,'height':550}, 'report': {'x':520,'y':0,'width':1520,'height':1272}, 'viewer': {'x':420,'y':112,'width':1750,'height':1150}, 'center': {'x':430,'y':90,'width':1710,'height':1170}}
manifest={'product_name':'MeDIAuto AI','created_at':datetime.datetime.now().astimezone().isoformat(),
 'provenance':'Existing real product screenshots from figure/manual-redacted; detail PNGs captured by Chromium from those images. Not fresh captures of the running application.',
 'production_access':False,'source_images_modified':False,'scenes':[],
 'additional_live_captures_needed':[
 '동일 시야의 AI overlay OFF / ON: 분석 결과 등장 애니메이션',
 '동일 시야의 IHC 원본 / Virtual H&E 전체 화면: 진짜 드래그 비교',
 '단일 세포 수정 전 / 편집 / 저장 후: 점수 반영과 저장 확인',
 '동일 패치의 AI assistance 실행 전 / 결과 / 전문가 수정 후',
 '검수 반려 / 재작업 / 검수 완료: 실제 상태 전환',
 '자동 분석 대기 / 진행 / 완료: 실제 작업 상태 전환'],
 'publication_note':'Sources have prior redaction. Filenames, tissue imagery, dataset-use permissions and remaining identifiers still require publication review; no blanket public-release clearance is asserted.'}
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/google-chrome',args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':2560,'height':1272},device_scale_factor=1)
 for scene_id,title,subtitle,items,motion in SCENES:
  folder=OUT/'images'/scene_id;folder.mkdir(parents=True,exist_ok=True)
  scene={'id':scene_id,'title':title,'subtitle':subtitle,'animation':motion,'frames':[]}
  for i,(source,slug,label,kind) in enumerate(items,1):
   src=SOURCE/source
   stem=f'{i:02d}-{slug}'
   full=folder/f'{stem}-full.png';shutil.copy2(src,full)
   page.goto(src.as_uri())
   page.evaluate("document.body.style.cssText='margin:0;background:white';document.querySelector('img').style.cssText='display:block;max-width:none;width:2560px;height:1272px'")
   page.wait_for_function("document.querySelector('img').complete && document.querySelector('img').naturalWidth > 0")
   frame={'label':label,'source':str(src.relative_to(ROOT)),'full':str(full.relative_to(OUT)),
    'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'hold_ms':3000,'transition_ms':500}
   if kind!='full':
    detail=folder/f'{stem}-detail.png'
    page.screenshot(path=str(detail),clip=CROPS[kind])
    frame.update(detail=str(detail.relative_to(OUT)),crop=CROPS[kind])
   # Browser-generated small JPEG for a light gallery and contact sheet.
   thumb=folder/f'{stem}-preview.jpg'
   page.set_viewport_size({'width':960,'height':477})
   page.evaluate("document.querySelector('img').style.cssText='display:block;width:960px;height:477px'")
   page.screenshot(path=str(thumb),type='jpeg',quality=82)
   page.set_viewport_size({'width':2560,'height':1272})
   frame['preview']=str(thumb.relative_to(OUT));scene['frames'].append(frame)
  manifest['scenes'].append(scene)
 browser.close()
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'scenes':len(manifest['scenes']),'full':sum(len(s['frames']) for s in manifest['scenes']),'detail':sum('detail' in f for s in manifest['scenes'] for f in s['frames'])}))
