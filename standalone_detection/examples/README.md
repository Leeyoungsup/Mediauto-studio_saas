# 형식 검증용 가상 데이터

`knuch_zip_export`는 KNUCH 브랜치의 `backend/app/comparison_export.py`에 있는 **build_comparison_zip**을 가상 판독 기록에 실행해 생성한 ZIP의 압축 해제 결과입니다. 실제 내보내기의 전체 20개 CSV 열, Grade 문자열, 계정별 CSV/JSON 및 요약 파일 구성을 그대로 사용합니다.

슬라이드 ID는 로컬 PD-L1(ST) 프로젝트와 연결되어 있지만 판독값·계정·시간은 가상입니다. 실제 전문의 기록이 아닙니다. CSV의 저장된 AI CPS는 의도적으로 99로 지정했습니다. 새 노트북은 이 값을 무시하고 WSI를 직접 추론합니다.

예제 실행 시에만 ACCOUNT_FOLDER를 `ROOT / 'standalone_detection/examples/knuch_zip_export/계정별'`로 바꾸세요. 기본 입력은 실제 ZIP을 넣는 `standalone_detection/계정별`입니다.
