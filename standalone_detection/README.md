# PD-L1 WSI 비교

`PDL1_account_PCC.ipynb`의 입력은 **KNUCH에서 PD-L1 비교 결과 ZIP을 다운로드했을 때 들어 있는 계정별 폴더**입니다.

## 입력

ZIP을 압축 해제한 뒤 `계정별/<로그인 ID>/비교결과.csv`와 JSON을 `standalone_detection/계정별`에 그대로 배치하세요. 노트북 `ACCOUNT_FOLDER`에 압축 해제 루트, 계정별 폴더 또는 특정 계정 폴더를 지정해도 됩니다. 실제 ZIP 데이터는 아직 제공되지 않았으며 기본 입력 폴더는 비워두었습니다.

KNUCH 원본 CSV를 변환할 필요가 없습니다.

| 원본 열 | 사용 |
|---|---|
| CPS Grade | `CPS < 1`, `1 ≤ CPS < 10`, `CPS ≥ 10`을 0/1/2로 변환 |
| 전문의 판독시간(초) | 전문의 판독시간 |
| AI 판독시간(초) | ZIP에 기록된 AI 판독시간 |
| 프로젝트·슬라이드 ID·판별 모델·계정 ID | PD-L1(ST)/Stomach 선택 및 연결 |
| 측정 시각(KST)·측정 ID | 동일 계정/슬라이드의 최신 기록 선택 |

`CPS (%)`, 저장된 AI CPS/Grade와 JSON은 사용하지 않습니다. 전문의 Grade가 비어 있으면 CPS 점수에서 복원하지 않고 결측으로 유지합니다. 반복 판독은 KNUCH `comparison_statistics.latest_measurements`처럼 측정 시각, 측정 ID 순서로 최신 하나를 사용합니다.

## 추론

backend 의존성이 설치된 커널에서 노트북을 위에서부터 실행하세요.

- `PROJECT_DIR`: 화면 제목 PD-L1(ST)의 로컬 경로 `backend/uploads/IHC(PD-L1)`.
- `CHECKPOINT`: `backend/model/PDL1_ST_CPS_detection.pt`.
- `MAX_PATCHES=None`: 전체 조직 영역의 패치 추론. 일부 패치 결과는 PCC/CCC에서 차단합니다.
- WSI 영역 선택 → 패치 추론/NMS → level-0 좌표 병합 → 전역 NMS → CPS/Grade → 계정별·과반 합의 PCC/CCC.
- 결과는 `results/`에 저장합니다. 같은 슬라이드는 한 번만 새로 추론합니다.
- `inference_seconds`는 이번 실행에서 모델 로딩을 제외한 전처리·추론·후처리 시간입니다. CSV 판독시간과 별도입니다.

## 형식 및 실행 검증

`examples/knuch_zip_export`는 KNUCH의 실제 `build_comparison_zip` 함수를 가상 판독 기록에 실행하여 만든 ZIP을 압축 해제한 자료입니다. 20개 열, Grade 문자열, 계정별 CSV/JSON 구성을 보존합니다. **실제 전문의 기록이 아닙니다.** 이전 임의 형식 예제는 기본 입력 폴더에서 제거했습니다.

2026-11-03 실제 WSI 3장의 전체 조직 패치 183개를 CPU로 추론했고 전역 NMS로 1,356개 중복 검출을 제거했습니다. 이는 WSI 처리 검증이며 실제 계정별 ZIP에 대한 성능 평가를 의미하지 않습니다.

입력 수정 후 테스트: **34 passed, 2 skipped**. 실제 KNUCH ZIP 생성 함수로 만든 CSV 읽기, 최신 판독 선택, 저장된 AI 점수 무시, 결측 Grade, 다른 모델 제외, 노트북 실행 등을 검증했습니다. 제외한 2개는 main에 없는 KNUCH 전용 exporter와의 기존 비교 테스트입니다.

```bash
PYTHONPATH=backend:standalone_detection /home/user/anaconda3/envs/medicus-saas/bin/python -m pytest standalone_detection/tests -q
```

이 서버의 medicus-saas 환경에서 OpenSlide의 libstdc++ 버전 충돌이 발생하면 커널 시작 전 다음을 설정하세요.

```bash
export LD_PRELOAD=/home/user/anaconda3/envs/medicus-saas/lib/libstdc++.so.6
```
