<!-- markdownlint-disable MD024 MD031 MD032 MD036 MD040 -->
# MeDIAuto Studio SaaS — 기능 명세

병원 On-Premise 배포용 디지털 병리 WSI 뷰어 + AI 분석 플랫폼. 이 문서는 현재 구현된 모든 기능을 사용자 관점 + 내부 동작 관점으로 정리한다.

## 목차

1. [WSI 뷰어](#1-wsi-뷰어)
2. [슬라이드 & 폴더 관리](#2-슬라이드--폴더-관리)
3. [Annotation](#3-annotation)
4. [AI 분석 — HE-Fit](#4-ai-분석--he-fit)
5. [AI 분석 — PD-Score](#5-ai-분석--pd-score-pd-l1)
6. [AI 분석 — Precise-IHC](#6-ai-분석--precise-ihc)
7. [AI 분석 — VS-IHC (Virtual Staining)](#7-ai-분석--vs-ihc-virtual-staining)
8. [폴더 단위 자동 AI 추론](#8-폴더-단위-자동-ai-추론)
9. [타일 프리제네레이션 워커](#9-타일-프리제네레이션-워커)
10. [타일 디스크 쿼터 janitor](#10-타일-디스크-쿼터-janitor)
11. [관리자 페이지](#11-관리자-페이지)
12. [반응형 UI (모바일 / 태블릿)](#12-반응형-ui-모바일--태블릿)
13. [UX 보조 기능](#13-ux-보조-기능)

---

## 1. WSI 뷰어

**포맷**: SVS, NDPI, TIFF, VMS, VMU, SCN, MRXS (+ PNG/JPG) — OpenSlide 지원 WSI 전체.

### 렌더링 파이프라인

- **멀티레벨 타일 서빙** — OpenSlide 피라미드를 1024px JPEG 타일로 사전 생성. 뷰어는 HTTP GET으로 `/{slide_id}/{level}/{x}/{y}.jpeg` 타일을 요청.
- **4단계 stage level** — 실제 WSI 레벨에서 중복 제거된 4개 줌 stage를 계산. 뷰어는 현재 줌에 가장 가까운 stage에서 타일을 가져오고 다른 stage 캐시를 fallback으로 사용.
- **최상위 레벨 프리로드** — 슬라이드 로드 직후 가장 거친 레벨 전체(보통 1~16장)를 즉시 캐시. 확대할 때 블러 fallback을 즉시 제공 → "빈 셀" 경험 제거.
- **ICC profile 적용** — 스캐너의 ICC profile을 타일 생성과 AI 분석 패치 로딩 양쪽에 일관 적용. 스캐너 색공간이 그대로 유지됨.

### 조작

| 동작 | 데스크톱 | 모바일 |
| ---- | -------- | ------ |
| 팬 | 좌클릭 드래그 | 한 손가락 드래그 |
| 줌 | 마우스 휠 | 두 손가락 핀치 |
| Annotation 내부 팬 | Ctrl + 드래그 | — |
| 그리기 취소 | 우클릭 또는 ESC | — |
| Fit to window | Fit 버튼 | Fit 버튼 |

- **마우스 좌표 오버레이** — 뷰어 우하단 반투명 표시(`x: Npx, y: Npx`) — 슬라이드 좌표계 기준.
- **미니맵** — 좌하단. 현재 뷰포트가 사각형으로 표시.
- **Touch gesture 제어** — `touch-action: none` + viewport meta `user-scalable=no`로 모바일 네이티브 핀치줌이 뷰어를 가로채지 않도록 차단. 뷰어 내부 줌/팬 로직만 동작.

### 뷰어 우선순위 게이팅

사용자가 뷰어를 조작 중이면 AI 워커가 양보하는 메커니즘:

- 타일 엔드포인트 진입 시 뷰어 활동 타임스탬프 갱신 (1.2초 grace window).
- AI 추론 워커의 패치 로딩 루프는 뷰어 활동 체크 → 활성 시 최대 3초 양보.
- 결과: 큰 AI 작업 실행 중에도 뷰어 팬/줌이 끊기지 않음.

---

## 2. 슬라이드 & 폴더 관리

### 파일 시스템 구조

- **루트**: `backend/uploads/` (환경변수 `UPLOAD_DIR` 오버라이드 가능).
- 사용자가 만드는 모든 폴더는 여기 아래 상대 경로. breadcrumb으로 네비게이션.

### 업로드

- **청크 업로드** — 5MB 청크 단위 `/upload/start` → `/upload/chunk` → `/upload/complete` 3단계. 큰 WSI 파일(최대 20GB) 재개 가능.
- 업로드 중에는 AI 자동 추론이 일시정지 → 부분 파일로 AI가 돌지 않도록 방어.
- `UPLOAD_DIR`의 디스크 여유 공간 체크 — 부족하면 업로드 시작 시 403.

### 파일 조작

- **열기**: `POST /open` (업로드된 파일) / `POST /open-local` (절대 경로, admin 전용). 열기 시 `slides` 컬렉션에 upsert + `slide.view` 감사 로그 기록.
- **상태 플래그**: `str_status` — `pending` / `in_progress` / `done` / `flagged` (리뷰 워크플로 지원).
- **이동**: `POST /file/move` — DB의 `str_rel_path`도 갱신.
- **삭제**: `POST /file/delete` — 파일 + DB 문서 + 관련 AI 결과 캐시 + 타일 디렉토리 모두 제거.

### 폴더 조작

- **생성/이름변경/삭제** — 폴더 이름 변경 시 `slides`와 `folder_ai_configs`의 `str_rel_path`를 모두 재작성.

### 브라우징

- `GET /browse?path=<rel_path>` — 폴더 내용 트리 조회. 목록/그리드 뷰 전환.
- Grid 뷰는 썸네일(미디어 HMAC 티켓으로 인증).

---

## 3. Annotation

### 도구

| 도구 | 방식 | 완료 |
| ---- | ---- | ---- |
| **Polygon** | 누른 채 드래그 (lasso) — 10px 간격 점 자동 추가 | 마우스 떼면 완성. 최소 3점 + 자기교차 시 취소 |
| **Rectangle** | 드래그 | 마우스 떼면 완성 |
| **Point** | 클릭 | 즉시 생성 |

- **활성 상태 가시화** — 선택된 도구 버튼은 accent 배경 + glow + 아래 도트 인디케이터 표시.
- **우클릭 / ESC** — 그리기 모드 즉시 해제.
- **Ctrl + 드래그** — annotation 내부에서 드래그해도 annotation 이동이 아닌 화면 팬으로 동작.

### 저장/불러오기

- `POST /api/slides/{slide_id}/annotations/save` — 현재 슬라이드의 annotation 전체를 JSON으로 업서트. `require_not_viewer` 의존성.
- `GET /api/slides/{slide_id}/annotations/load` — 저장된 annotation 불러오기.
- 각 annotation은 고유 색상 + 레이블을 가지며 우측 패널의 Annotation Panel에서 관리.

---

## 4. AI 분석 — HE-Fit

**목적**: H&E 염색 슬라이드 전 영역에서 세포 단위 검출 + 분류. Stomach/Breast는 추가로 Tumor/Benign epithelial 재분류까지 수행.

### Input

| 항목 | 값 | 비고 |
| --- | --- | --- |
| endpoint | `POST /api/ai/detect` | `require_not_viewer` |
| `slide_id` | slide_manager key | 열려 있는 슬라이드 |
| `tissue_type` | `Stomach` / `Breast` / `Other` | Stomach·Breast만 seg 재분류 |
| `roi_polygons` | optional JSON `[[x,y],...]` 리스트 | 없으면 전체 슬라이드 |
| 모델 파일 | `models/HnE_detection.pt` | YOLOv11m, 6 class |

**추가 seg 모델 (Stomach/Breast):**
- Stomach → `HnE_ST_segmentation.pt`
- Breast → `HnE_BR_segmentation.pt`
- 구조: WSISegmentationModel, `model_mpp=1.0`, `output_mpp=4.0`

### Process

1. **캐시 확인** — `ai_results/HE-Fit/{stem}_HE-Fit_{tissue_type}.json` 존재 시 즉시 반환 (전체 추론 때만).
2. **모델 로드** — YOLOv11m(6 class), checkpoint의 state_dict 주입, eval 모드.
3. **조직 마스크 생성** — 썸네일을 H-DAB color deconvolution → H/DAB 각각 Otsu 이진화 → 국소 표준편차 텍스처 Otsu → union → 유리 배경 제외. 배경 패치를 스킵해 I/O·추론 생략.
4. **패치 그리드 생성** — 1024px 격자 순회, 조직 마스크가 0인 타일 스킵, ROI bounding box 필터.
5. **병렬 I/O 프리페치** — ThreadPoolExecutor(최대 8 workers)로 스레드별 독립 OpenSlide 핸들. 각 worker가 `read_region` → RGB → ICC transform → resize(512) → Tensor 변환. PREFETCH_BATCHES=3 크기 큐에 BATCH_SIZE=8 단위로 공급.
6. **배치 GPU 추론** — AMP autocast + no_grad → 모델 추론 → NMS(conf=0.01, iou=0.3). bbox center를 coord_scale=2.0으로 복원 + 패치 오프셋으로 슬라이드 좌표 환산.
7. **Viewer 양보** — 각 패치 I/O 시작 전 뷰어 활동 체크 → 활성 시 최대 3초 대기. 매 배치 사이 취소 체크.
8. **(옵션) Epithelial 재분류** (Stomach/Breast) — cls==1(Epithelial) 셀이 있으면:
   - seg 모델로 WSI segmentation (patch_size=512, overlap=0.4, batch=8) → prediction mask + per-class softmax prob_map.
   - WSI↔mask 좌표 변환 (scale = wsi_mpp / output_mpp).
   - connected components 분석. 각 component의 tumor_ratio = count(tumor) / count(epithelial). ratio >= 0.1이면 Tumor, 미만이면 Benign.
   - cls 1 → **6 (Tumor Epithelial)** 또는 **7 (Benign Epithelial)** 로 in-place 치환.
   - 썸네일 + 클래스별 확률맵 jet colormap PNG base64 오버레이 생성.
9. **결과 캐시 저장** (ROI 없을 때만) + DB variant 등록.

### Output

```jsonc
{
  "total_cells": 123456,
  "cells": [
    { "x": 12345.6, "y": 23456.7,
      "confidence": 0.87,
      "class_id": 6,
      "class_name": "Tumor Epithelial" }
  ],
  "class_names": { "0": "Neutrophil", "1": "Epithelial", "2": "Lymphocyte",
                   "3": "Plasma",     "4": "Eosinophil", "5": "Connective tissue",
                   "6": "Tumor Epithelial", "7": "Benign Epithelial" },
  "class_colors": { "0": "#FF4500", "1": "#00FF00", ..., "6": "#FF0000", "7": "#00FF00" },
  "seg_data": {          // Stomach/Breast에서만 — null 가능
    "thumbnail": "<jpeg base64>",
    "overlays": { "Tumor": "<png base64>", "Benign": "<png base64>", ... },
    "class_names": ["Tumor", "Benign", ...],
    "width": 800, "height": 480
  }
}
```

### 시각화 (프론트)

- 우측 Detection Results 리스트: class별 count + 체크박스로 오버레이 on/off.
- `Visualize` 버튼 → 4탭 다이얼로그:
  - Class Distribution — 바 차트
  - Tumor Analysis — Tumor/Benign ratio (Stomach/Breast only)
  - Spatial Heatmap — seg_data.overlays 렌더
  - Confidence Distribution — conf histogram
- `Save` → 서버 캐시로 결과 덮어쓰기.
- PDF Export 지원.

---

## 5. AI 분석 — PD-Score (PD-L1)

**목적**: PD-L1 IHC 슬라이드에서 세포별 양성/음성 + 종류(Epithelial/Lymphocyte/Macrophage)를 검출해 임상 score(CPS/TPS) 자동 산출.

### Input

| 항목 | 값 |
| --- | --- |
| endpoint | `POST /api/ai/pd-score` |
| `slide_id` | 열려 있는 PD-L1 IHC 슬라이드 |
| `tissue_type` | `Stomach` → CPS, `Lung` → TPS |
| `roi_polygons` | optional |

| tissue_type | 모델 파일 | num_classes |
| --- | --- | :---: |
| Stomach | `PDL1_ST_CPS_detection.pt` | 7 |
| Lung | `PDL1_TPS_detection.pt` | 3 |

**모델 특이사항** — PDL1 체크포인트는 DFL 채널수가 기본 16이 아닌 **4**로 훈련됨. 로드 시 head의 DFL 모듈과 box 브랜치를 재빌드하여 shape를 맞춤.

### Process

1. 캐시 확인. 레거시 캐시의 `score_conf_threshold`가 현재 값(0.1)과 다르면 cells로부터 **재계산 후 덮어쓰기**.
2. 모델 로드 + DFL head 재빌드.
3. 조직 마스크 → 1024px 패치 grid → ROI 필터.
4. 병렬 I/O (8 workers) + 배치 GPU 추론 (batch=8, coord_scale=2.0). HE-Fit과 동일한 producer/consumer 큐 구조.
5. `exclude_classes=[6]`(Stomach "Other")을 화면 표시 셀 리스트에서 제외.
6. **Score 계산** — confidence >= 0.1인 셀만 사용 (프론트 기본 필터와 일관).
7. 캐시 저장 + DB variant 등록.

### Score 수식

**CPS (Stomach)** — Combined Positive Score:

```
positive_tumor  = count(cls==3)                 # Positive Epithelial
positive_immune = count(cls==4) + count(cls==5) # Pos Lymph + Pos Macro
viable_tumor    = count(cls==0) + count(cls==3) # Neg Epi + Pos Epi
CPS = min(100, (positive_tumor + positive_immune) / viable_tumor * 100)
```

**TPS (Lung)** — Tumor Proportion Score:

```
positive_tumor = count(cls==1)
negative_tumor = count(cls==0)
TPS = positive_tumor / (positive_tumor + negative_tumor) * 100
```

### 클래스 정의

| id | Stomach (CPS 모델) | Lung (TPS 모델) |
| :-: | --- | --- |
| 0 | Negative Epithelial (`#1e8449`) | PD-L1 Negative Tumor |
| 1 | Negative Lymphocyte (`#27ae60`) | PD-L1 Positive Tumor |
| 2 | Negative Macrophage (`#16a085`) | Non-Tumor Cell |
| 3 | Positive Epithelial (`#922b21`) | — |
| 4 | Positive Lymphocyte (`#e74c3c`) | — |
| 5 | Positive Macrophage (`#ec7063`) | — |
| 6 | Other (excluded) | — |

### Output

```jsonc
{
  "total_cells": 45678,
  "cells": [ { "x":..., "y":..., "confidence":..., "class_id":..., "class_name":... } ],
  "class_names":  { "0": "Negative Epithelial", ... },
  "class_colors": { "0": "#1e8449", ... },
  "score_conf_threshold": 0.1,
  "pd_score": {           // CPS
    "score_type": "CPS",
    "score": 42.37,
    "positive_tumor": 1234, "positive_immune": 567,
    "viable_tumor": 4321,
    "class_counts": {"0": N0, "1": N1, ..., "5": N5}
  },
  "tissue_type": "Stomach"
}
```

> TPS 응답은 `positive_tumor / negative_tumor / total_tumor` 필드 사용.

---

## 6. AI 분석 — Precise-IHC

**목적**: IHC marker 염색 강도(0+~3+)를 세포 단위로 정밀 분류 → HER2 score / Allred score / KI-67 Labeling Index 산출.

### Input

| 항목 | 값 |
| --- | --- |
| endpoint | `POST /api/ai/precise-ihc` |
| `slide_id` | IHC 슬라이드 |
| `marker` | `HER2` / `ER_PR` / `KI_67` |
| `roi_polygons` | optional |

| marker | 모델 파일 | num_classes | score_type | confidence threshold |
| --- | --- | :---: | --- | :---: |
| HER2 | `Precise_IHC_HER2_detection.pt` | 5 (0+~3+ + Other) | HER2 | 0.1 |
| ER_PR | `Precise_IHC_ER_PR_detection.pt` | 5 (0+~3+ + Other) | Allred | 0.3 |
| KI_67 | `Precise_IHC_ER_PR_detection.pt` (공유) | 5 (0+~3+ + Other) | KI67 | 0.3 |

> KI-67은 현재 ER/PR 모델을 임시 공유한다. class 0 = Negative, class 1/2/3 = Positive로 재해석.

### Process

HE-Fit / PD-Score와 동일한 공용 pipeline:

1. 캐시 확인 + 임계값 변경 시 score만 재계산.
2. YOLOv11m 로드 (DFL head 재빌드 적용).
3. 조직 마스크 → 1024px 패치 → ROI 필터.
4. 병렬 I/O + 배치 GPU 추론 → `exclude_classes=[4]`("Other") 필터.
5. confidence >= threshold 셀만으로 score 계산.
6. 캐시 + DB variant 등록.

### Score 수식

**HER2 score:**

```
weighted_avg = sum(i * count(cls==i)) / sum(count(cls==i))   for i in 0..3
dominant_class = argmax(count(cls==i))
```

→ `score` 필드는 0.0 ~ 3.0 실수(가중 평균).

**Allred score (ER/PR):**

```
n0, n1, n2, n3 = counts of cls 0~3
total    = n0 + n1 + n2 + n3
positive = n1 + n2 + n3
positive_pct = positive / total * 100

# Proportion Score (PS)  0~5
PS = 0 if positive == 0
     1 if positive_pct < 1%
     2 if positive_pct < 10%
     3 if positive_pct < 33%
     4 if positive_pct < 66%
     5 otherwise

# Intensity Score (IS)  0~3
avg_intensity = (1*n1 + 2*n2 + 3*n3) / positive
IS = 0 if avg < 0.5
     1 if avg < 1.5
     2 if avg < 2.5
     3 otherwise

Total Score (TS) = PS + IS       # 0..8
interpretation   = "Positive" if TS >= 3 else "Negative"
```

**KI-67 Labeling Index:**

```
n0, n1, n2, n3 = counts of cls 0~3
total    = n0 + n1 + n2 + n3
positive = n1 + n2 + n3        # class 1/2/3 모두 양성으로 간주
negative = n0                  # class 0만 음성

KI-67 Index (%) = positive / total * 100

# 임상 해석 (St Gallen 2013 기준)
interpretation = "High" if index >= 14% else "Low"
cutoff = 14%
```

> KI-67은 염색 강도가 아닌 양성/음성 이진 판정이 핵심. ER/PR 모델의 class 0(음성)과 class 1~3(양성 강도)을 양성 그룹으로 묶어 Labeling Index를 계산한다. 14% cutoff은 St Gallen 2013 International Breast Cancer Conference 합의 기준이다.

### 클래스 정의

| id | HER2 | ER_PR | KI_67 | 색상 |
| :-: | --- | --- | --- | --- |
| 0 | HER2 0+ | ER/PR 0+ | Negative | `#27ae60` green |
| 1 | HER2 1+ | ER/PR 1+ | Positive (1+) | `#f1c40f` yellow / `#e67e22` orange |
| 2 | HER2 2+ | ER/PR 2+ | Positive (2+) | `#e67e22` orange / `#e74c3c` red |
| 3 | HER2 3+ | ER/PR 3+ | Positive (3+) | `#c0392b` deep red |
| 4 | Other | Other | Other | `#95a5a6` (excluded) |

### Output

```jsonc
// HER2
{
  "total_cells": ...,
  "cells": [...],
  "class_names": { "0": "HER2 0+", ..., "3": "HER2 3+" },
  "class_colors": {...},
  "score_conf_threshold": 0.1,
  "her2_score": {
    "score_type": "HER2",
    "score": 1.87,               // weighted average
    "dominant_class": 2,
    "total_tumor": 4321,
    "class_counts": {"0":..., "1":..., "2":..., "3":...}
  },
  "marker": "HER2"
}

// ER_PR
{
  ...,
  "allred_score": {
    "score_type": "Allred",
    "proportion_score": 4,       // 0..5
    "intensity_score": 2,        // 0..3
    "total_score": 6,            // PS + IS = 0..8
    "positive_pct": 52.3,
    "avg_intensity": 1.87,
    "interpretation": "Positive",
    "total_tumor": 4321,
    "class_counts": {...}
  },
  "marker": "ER_PR"
}

// KI_67
{
  ...,
  "ki67_score": {
    "score_type": "KI67",
    "index": 23.5,               // Labeling Index (%)
    "positive": 1234,
    "negative": 4000,
    "total": 5234,
    "interpretation": "High",    // >= 14%
    "cutoff": 14.0,
    "class_counts": {...}
  },
  "marker": "KI_67"
}
```

### 시각화 (프론트)

- **공통**: 우측 Detection Results에 class별 count + 체크박스로 오버레이 on/off.
- **셀 수정 → 스코어 실시간 반영**: 사용자가 개별 셀의 class를 수정하면 Allred/HER2/PD-Score/KI-67 스코어가 즉시 재계산되어 표시된다.
- **Visualize 다이얼로그**:
  - HER2: 4탭 — Score Card (가중평균 게이지 + Dominant class) + Distribution + Spatial + Confidence
  - Allred (ER/PR): 4탭 — Score Card (PS/IS/TS 표시 + 양성 판정) + Distribution + Spatial + Confidence
  - KI-67: 4탭 — Score Card (Index % 게이지 + High/Low 판정 + 14% cutoff 기준선) + Distribution + Spatial + Confidence
- **PDF Export**: 각 score type별 전용 페이지 (커버에 해당 score 메트릭 표시).
- **배치 분석**: 폴더 자동 AI 설정에서 KI-67도 선택 가능 (`Precise-IHC · KI-67`).

---

## 7. AI 분석 — VS-IHC (Virtual Staining)

**목적**: H&E 슬라이드에서 IHC 염색을 GAN으로 가상 생성 — 실제 IHC 염색 없이 membrane/nucleus 마커 시뮬레이션.

### Input

| 항목 | 값 |
| --- | --- |
| endpoint | `POST /api/ai/virtual-stain` |
| `slide_id` | H&E 슬라이드 |
| `stain_type` | `ihc_membrane` / `ihc_nucleus` |
| `target_mpp` | 기본 `2.0` — 추론 해상도 |
| `roi_polygons` | optional — **추론은 전체로 수행**, 폴리곤은 프론트 클립 마스크로만 사용 |

| stain_type | 모델 파일 |
| --- | --- |
| ihc_membrane | `IHC_HnE_virtual_stain_membrane.pth` |
| ihc_nucleus | `IHC_HnE_virtual_stain_nucleus.pth` |

**모델**: pix2pix 계열 U-Net/ResNet generator (in=3, out=3). CUDA 시 FP16.

### Process

1. **캐시 확인** — `ai_results/VS-IHC/{stem}_VS-IHC_{stain}_mpp{p}.{png,json}`.
   - 레거시 캐시에 타일 피라미드(`levels`)가 없으면 **자동 업그레이드**: PNG 로드 → 4-레벨 타일 생성 → meta 갱신.
2. **해상도 계산**:
   ```
   native_mpp         = slide.mpp-x
   downsample_factor  = target_mpp / native_mpp
   patch_size (ps)    = 512
   overlap            = ps // 4 = 128
   stride             = ps - overlap = 384
   read_size          = int(ps * downsample_factor)    # level-0 기준 패치 크기
   read_stride        = int(stride * downsample_factor)
   best_level         = get_best_level_for_downsample(downsample_factor)
   level_read         = int(read_size / level_downsamples[best_level])
   ```
3. **Patch grid 생성** — 마지막 패치가 영역 끝에 닿지 않으면 꼬리 패치 추가. 전체 캔버스 크기 계산.
4. **Tissue grid 생성** — 썸네일 기반 조직 마스크로 패치별 `is_tissue` 판정. 조직이 아닌 패치는 추론 생략 → 원본 H&E 그대로 복사.
5. **병렬 I/O + 배치 추론**:
   - ThreadPoolExecutor(최대 8 workers)로 원본 로드 + ICC transform + resize.
   - tissue 패치는 `[-1, 1]` 정규화 → batch_size=4로 누적.
   - GAN 추론 → 결과를 blend accumulation.
6. **Blend accumulation** — 패치 경계에 cosine blend weight 적용. 4개 캔버스(output, input, weight, blend) 누적:
   - 비-tissue 패치는 원본을 output에 넣어 이음새 자연스럽게.
7. **Compose**: weight 정규화 → 미커버 영역 흰색 → 비-tissue 영역은 원본 H&E로 복원.
8. **ROI polygon masking** (있을 경우) → RGBA alpha mask.
9. **저장**: composite PNG + 4단계 타일 피라미드(각 레벨 절반씩 bilinear downsample) + meta JSON + DB variant 등록.
10. **Viewer 양보** — 패치 I/O 시작 전 매번 뷰어 활동 체크, 배치 간 취소 체크.

### Output

```jsonc
{
  "stain_type": "ihc_membrane",
  "image_filename": "Sample_VS-IHC_ihc_membrane_mpp2.png",
  "roi_origin": [0, 0],
  "canvas_l0_w": 87654,
  "canvas_l0_h": 65432,
  "target_mpp": 2.0,
  "tissue_count": 1234,
  "total_patches": 2048,
  "tile_size": 512,
  "levels": [
    { "level": 0, "tile_w": 43, "tile_h": 32, "img_w": 21845, "img_h": 16384 },
    { "level": 1, ... },
    { "level": 2, ... },
    { "level": 3, ... }
  ],
  "cached": false,
  "roi_polygons": [...]
}
```

### 프론트 렌더링

- composite PNG 스트리밍(미디어 HMAC 티켓).
- 타일 피라미드 서빙 (큰 composite 대신 타일 사용 — 줌 가능).
- 뷰어는 WSI 타일 위에 VS 타일을 canvas_l0 좌표 기준으로 정합 후 오버레이.

### 특이사항

- 추론은 항상 전체 슬라이드 (ROI 무시) → 캐시 재사용성 향상. 사용자 ROI는 프론트에서 clip-path로만 적용.
- `target_mpp`별로 캐시 경로가 분리됨. DB에는 stain_type까지만 기록 — per-mpp 존재 여부는 파일시스템으로만 체크하므로 auto_ai는 base variant 단위로 dedupe.

---

## 8. 폴더 단위 자동 AI 추론

### 개념

특정 폴더에 대해 "이 AI를 자동으로 돌려라"를 지정하면, 백그라운드 워커가 1분마다 스캔해서 미완 슬라이드만 골라 AI를 돌린다. 사용자가 수동으로 버튼을 누를 필요 없음.

### 설정

- `POST /api/slides/folder-config` — `path`, `enabled`, `tasks_json`
  - `tasks_json` 예: `[{"model": "HE-Fit", "variant": "Stomach"}, {"model": "Precise-IHC", "variant": "KI_67"}, {"model": "VS-IHC", "variant": "ihc_membrane", "target_mpp": 2.0}]`
- `require_not_viewer` 의존성 (viewer는 설정 수정 불가, 조회만 가능).
- `folder_ai_configs` 컬렉션에 upsert.

### 워커 동작

1. `SCAN_INTERVAL_SECONDS=60` 주기.
2. `folder_ai_configs.find({bool_enabled: true})` 스캔.
3. 각 task마다 미완 슬라이드만 조회 (model + variant 기준).
4. `has_any_pending_tiles()` 체크 — 타일 프리젠 미완 슬라이드가 있으면 AI 보류.
5. `ping_ai_activity()` 체크 — 사용자가 수동으로 AI를 돌리고 있으면 양보.
6. `upload_enter()` 카운터 체크 — 업로드 중이면 정지.
7. AI 파이프라인 호출 → 성공 시 variant 추가.

### 사용자 플로우

- 우측 패널에서 "폴더 자동 분석 설정" 열고 AI 작업 리스트 구성 → Enable.
- 선택 가능한 작업: HE-Fit (Stomach/Breast/Other), PD-Score (Stomach/Lung), Precise-IHC (HER2/ER_PR/KI_67), VS-IHC (ihc_membrane/ihc_nucleus)
- 이후 해당 폴더에 업로드되는 모든 슬라이드가 자동으로 해당 AI 결과를 갖게 됨.

---

## 9. 타일 프리제네레이션 워커

### 문제

뷰어가 WSI 타일을 실시간으로 생성하면 첫 로딩이 느리고 AI와 경합. → 업로드 직후 백그라운드에서 미리 생성.

### 동작

- `SCAN_INTERVAL_SECONDS=20` 주기로 `slides.find({bool_tiles_ready: {$ne: true}})` 스캔.
- 오래된 업로드부터 순차 처리 — `run_in_executor`로 블로킹 OpenSlide 호출 오프로드.
- 모든 stage level(4단계)을 거친 레벨부터 역순 생성 → 뷰어 첫 화면이 가장 빠르게 채워짐.
- 완료 시 DB 플래그 + `dt_tiles_ready_at` 기록.
- 실패/누락 파일 — 파일이 없어진 경우 `bool_tiles_ready=true`로 강제 마킹(무한 재시도 방지).

### auto_ai와 조율

- tile_worker → auto_ai 순으로 lifespan에서 시작.
- auto_ai는 사이클 시작 + 슬라이드 간 분기점에서 타일 미완료 체크 → 미완 시 AI 추론 보류.
- 결과: 새 슬라이드 업로드 → 먼저 뷰어 타일이 준비되어 즉시 열람 가능 → 이후 자동 AI 돌아감.

---

## 10. 타일 디스크 쿼터 janitor

- `TILES_DIR` 총 크기가 `TILE_CACHE_QUOTA_BYTES` (기본 50GB)를 초과하면 LRU 기준으로 오래된 슬라이드 타일 디렉토리를 삭제.
- 삭제 후 `bool_tiles_ready=false`로 리셋 → tile_worker가 필요 시 재생성.
- **현재 열려 있는 슬라이드**(slide_manager에 활성)는 보호 대상에서 제외.
- LRU 판단: 타일 서빙 시 `.complete` 마커의 mtime을 갱신.
- 환경변수 `TILE_CACHE_QUOTA_BYTES=0`으로 비활성화 가능.

---

## 11. 관리자 페이지

admin 역할만 접근 가능. 4개 탭.

### 탭 1 — 승인 대기

- 승인 대기 사용자 목록 표시.
- 승인 시 역할 지정(viewer/doctor/admin).
- 거부 시 사유 입력.

### 탭 2 — 사용자 관리

- 전체 사용자 목록 페이지네이션(20/page).
- 필터: 상태(approved/pending/rejected) + 검색(아이디/이름/부서).
- 행 단위 작업:
  - **수정** — 이름/부서/비밀번호 다이얼로그
  - **역할 변경** — 인라인 select
  - **활성 토글** — `bool_is_active` on/off
  - **잠금 해제** — 5회 실패로 잠긴 계정 수동 복구
  - **삭제** — 삭제 시 해당 사용자 모든 세션도 revoke
- 모든 작업은 변경 전/후 값을 감사 로그에 기록.

### 탭 3 — 사용자 생성

- admin이 직접 계정 생성 (즉시 approved + active).
- 비밀번호 정책 동일(8자+ 대/소/숫/특수).

### 탭 4 — 활동 로그

- 로그인 이력 역순 페이지네이션.
- 열: **시간 / 아이디 / 이름·역할 / IP / 위치 / 디바이스 / 상세 활동**
- **위치** — geo enrichment 결과 (국가 + 도시).
- **디바이스** — User-Agent 파싱.
- **행 클릭** — 해당 사용자 활동 상세 다이얼로그 열림:
  - 4개 카테고리 탭: **전체 / 로그인 / 슬라이드 조회 / AI 분석** (각 count 배지)
  - 카테고리 필터 + 페이지네이션
  - 각 이벤트는 action pill(색상) + 상세 텍스트 + 시간 + IP로 표시

### 시간 표시

- 모든 시각은 한국시간(KST)으로 표시. UTC ISO → `Asia/Seoul` 변환.

---

## 12. 반응형 UI (모바일 / 태블릿)

`@media (max-width: 900px)` 기준:

- **좌/우 패널 → 슬라이드 drawer** — absolute positioning + translateX 애니메이션.
- **햄버거 토글** — 메뉴바 좌측/우측 버튼으로 drawer 열고 닫기.
- **Backdrop** — 반투명 오버레이 클릭 시 닫힘 + ESC 핫키.
- **자동 정리** — matchMedia change 이벤트로 브레이크포인트 역방향 이동 시 drawer 상태 초기화.
- **툴바** — 가로 스크롤 허용, 상태/사용자 이름 숨김.
- 480px 이하 추가 규칙 — drawer 폭 90/94%, 슬라이드 이름 ellipsis.
- **핀치줌 방어** — 뷰어 영역 `touch-action: none` + viewport meta `user-scalable=no` → 페이지 자체 핀치줌 차단, 뷰어 내부 줌만 동작.

---

## 13. UX 보조 기능

### 마우스 좌표 오버레이

뷰어 우하단 반투명 `x: Npx, y: Npx` — 슬라이드 픽셀 좌표 기준.

### UX 기능 설명 모달

툴바의 `?` 버튼 → 모든 단축키/제스처 설명 팝업.

### 키보드 단축키

| 키 | 동작 |
| -- | ---- |
| ESC | 그리기 모드 해제 / 모달 닫기 |
| +/- | 확대/축소 |

### 자동 재로그인 방어

- **Refresh rotation grace** — 모바일 백그라운드 탭이 깨어나 이전 토큰으로 재시도해도 5분 안에는 정상 처리.
- **Cache-Control: no-cache** — `.js/.html/.css`는 항상 재검증. 배포 직후 하드 리프레시 없이 새 버전 반영.

### Drag & Drop 업로드

뷰어 영역에 WSI 파일 드롭 → 자동 업로드 시작 다이얼로그.

### 뷰어 리사이즈 대응

- window resize → 캔버스 리사이즈 + 마지막 뷰 중심 유지.
- 좌패널 resizer로 사이드바 폭 조정 가능 (160~500px).

---

## 부록 A — 엔드포인트 일람

### 인증

```
POST   /api/auth/register               회원가입 (첫 사용자만 즉시 admin)
POST   /api/auth/login                  아이디/비밀번호 로그인
POST   /api/auth/refresh                토큰 갱신 (rotation + reuse 탐지)
POST   /api/auth/logout                 세션 전체 폐기
GET    /api/auth/me                     현재 사용자
POST   /api/auth/change-password        비밀번호 변경
GET    /api/auth/media-ticket           단기 HMAC 미디어 티켓 발급
```

### 사용자 (Admin 전용)

```
GET    /api/users/list                  사용자 목록
GET    /api/users/pending                승인 대기
POST   /api/users/approve                승인 (before/after 감사 기록)
POST   /api/users/reject                 거부 (before/after 감사 기록)
POST   /api/users/create                 직접 생성
POST   /api/users/update                 수정 (before/after 감사 기록)
DELETE /api/users/delete/{user_id}       삭제 (before 스냅샷 감사 기록)
POST   /api/users/role                   역할 변경 (before/after 감사 기록)
POST   /api/users/toggle-active          활성 토글 (before/after 감사 기록)
POST   /api/users/unlock/{user_id}       잠금 해제 (before/after 감사 기록)
GET    /api/users/audit-logs             원시 감사 로그
GET    /api/users/audit-logs/verify-chain  HMAC 체인 무결성 검증
GET    /api/users/activity/logins        로그인 활동
GET    /api/users/{user_id}/activity     사용자별 상세 활동
```

### 슬라이드

```
GET    /api/slides/                      슬라이드 전체 조회
GET    /api/slides/browse                폴더 트리
POST   /api/slides/folder/create         폴더 생성
POST   /api/slides/folder/rename         폴더 이름 변경
POST   /api/slides/folder/delete         폴더 삭제
POST   /api/slides/file/delete           파일 삭제
POST   /api/slides/file/status           상태 플래그
POST   /api/slides/file/move             파일 이동
POST   /api/slides/open                  업로드된 슬라이드 열기
POST   /api/slides/open-local            로컬 절대경로 열기 (admin)
POST   /api/slides/upload/start          청크 업로드 시작
POST   /api/slides/upload/chunk          청크 업로드
POST   /api/slides/upload/complete       청크 업로드 완료
GET    /api/slides/tile-progress/{id}    타일 생성 진행률
GET    /api/slides/{id}/info             슬라이드 메타 정보
GET    /api/slides/folder-config         폴더 AI 설정 조회
POST   /api/slides/folder-config         폴더 AI 설정 저장 (not viewer)
DELETE /api/slides/folder-config         폴더 AI 설정 삭제 (not viewer)
DELETE /api/slides/{id}                  슬라이드 닫기
POST   /api/slides/{id}/annotations/save annotation 저장 (not viewer)
GET    /api/slides/{id}/annotations/load annotation 로드 (not viewer)
```

### 타일 (미디어 티켓 인증)

```
GET    /api/tiles/{slide_id}/{level}/{x}/{y}.jpeg   타일 JPEG
GET    /api/tiles/{slide_id}/stage-level            현재 stage level 정보
```

### AI

```
POST   /api/ai/detect                    HE-Fit (not viewer)
POST   /api/ai/pd-score                  PD-Score (not viewer)
POST   /api/ai/precise-ihc               Precise-IHC — HER2/ER_PR/KI_67 (not viewer)
POST   /api/ai/virtual-stain             VS-IHC (not viewer)
GET    /api/ai/virtual-stain/{id}/{type}.png  가상염색 PNG (미디어 티켓)
GET    /api/ai/active-tasks              실행 중 태스크 목록
GET    /api/ai/task/{task_id}            태스크 진행률/상태
POST   /api/ai/task/{task_id}/cancel     태스크 취소
GET    /api/ai/task/{task_id}/result     태스크 결과 조회
POST   /api/ai/save-result               결과 수동 저장
```

## 부록 B — 캐시 디렉토리 구조

```
backend/
├── uploads/                                     # WSI 원본 (UPLOAD_DIR)
│   ├── HnE/
│   └── IHC/
├── tiles/                                       # 프리생성 JPEG 타일 (TILES_DIR)
│   └── {slide_id}/
│       ├── {level}_{x}_{y}.jpeg
│       └── .complete                            # LRU mtime 마커
└── ai_results/                                  # AI 결과 캐시 (AI_RESULTS_DIR)
    ├── HE-Fit/
    │   └── {slide_stem}_HE-Fit_{tissue_type}.json
    ├── PD-Score/
    │   └── {slide_stem}_PD-Score_{tissue_type}.json
    ├── Precise-IHC/
    │   └── {slide_stem}_Precise-IHC_{marker}.json   # marker: HER2, ER_PR, KI_67
    └── VS-IHC/
        ├── {slide_stem}_VS-IHC_{stain_type}_mpp{N.N}.png
        ├── {slide_stem}_VS-IHC_{stain_type}_mpp{N.N}.json
        └── tiles/{slide_stem}_{stain_type}_mpp{N.N}/
```
