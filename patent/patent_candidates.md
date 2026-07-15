# Patent Filing Candidates

본 문서는 MeDICus Studio SaaS의 특허 출원 후보 기술을 정리한 초안이다.
출원 전략은 큰 발명군을 4개로 잡고, 각 출원 안에서 독립항과 종속항으로 세부 기술을 나누는 방향을 권장한다.

## 1. WSI Viewer 및 Adaptive Tile Streaming 방법

### 핵심 발명 방향

대용량 WSI(Whole Slide Image)를 웹 환경에서 부드럽게 탐색하기 위한 viewport 기반 타일 렌더링 및 동시접속 대응형 adaptive tile streaming 방법.

### 포함 기술

- 현재 viewport 중심의 tile 요청, queueing, 우선순위 조정
- child tile 우선 요청 및 parent/fallback tile 표시
- slide 이동, zoom, pan 시 stale tile 요청 abort 및 generation 분리
- cache hit/miss에 따른 hybrid tile serving
- 서버 부하, viewer queue, 동시 사용자 수, background tile generation 상태에 따른 inline tile generation 제한
- tile miss 시 priority queue 등록 후 fallback/retry 처리
- 여러 사용자가 동시에 접근할 때 현재 보고 있는 위치의 타일을 우선 생성하는 scheduling
- Philips/iSyntax 등 특수 포맷에서 bridge 기반 tile extraction과 viewer thread별 slide handling

### 청구항 후보

- viewport 기반으로 표시 대상 tile을 산출하고, 현재 viewport와 가까운 tile을 우선 요청하는 방법
- 요청된 tile이 없을 때 parent tile 또는 thumbnail 기반 fallback을 표시하면서 target tile을 비동기 생성하는 방법
- 서버 부하 조건에 따라 inline tile generation과 queued tile generation을 전환하는 방법
- viewer 이동 또는 slide 변경 시 진행 중인 tile 요청을 abort하고 새로운 viewport 기준으로 재정렬하는 방법
- background full tiling보다 사용자 viewport tile을 우선 생성하는 방법

### 분리 가능 포인트

필요하면 "multi-user adaptive tile scheduling"을 별도 출원으로 분리 가능하다. 다만 현재는 viewer/tile streaming과 하나로 묶는 것이 중복을 줄이는 데 유리하다.

## 2. 대규모 병리 AI 정량 결과의 실시간 시각화 방법

### 핵심 발명 방향

Quanti 모델 또는 병리 AI 모델의 대량 cell/patch/heatmap 결과를 WSI viewer 위에서 렉 없이 표시, 필터링, 탐색하는 방법.

### 포함 기술

- AI detection result를 viewport 기준으로 선별하여 렌더링
- spatial index 또는 grid 기반 cell lookup
- confidence threshold, class visibility, hidden cell 표시 제어
- bounding box, point, heatmap, patch 단위 overlay 표시
- large-scale AI result를 canvas 기반으로 빠르게 갱신하는 rendering pipeline
- 사용자 zoom level과 viewport 상태에 따른 표시 밀도/레이어 조절
- Quanti HE, Quanti PD-L1, Quanti IHC 등 모델별 결과를 동일한 viewer framework에서 표시하는 구조

### 청구항 후보

- WSI 좌표계의 AI cell result를 spatial index로 구성하고 viewport와 교차하는 결과만 렌더링하는 방법
- AI result class, confidence, visibility 조건에 따라 실시간 overlay를 갱신하는 방법
- patch-level, cell-level, heatmap-level 결과를 동일 viewer coordinate system에서 결합 표시하는 방법
- 대량 병리 AI 결과를 pan/zoom interaction 중에도 지연 없이 표시하기 위한 culling 및 cache 방법

### 분리 가능 포인트

모델 자체의 학습 방법보다는 "모델 결과를 WSI viewer에서 실시간으로 표시하고 탐색하는 방법"에 초점을 두는 것이 좋다.

## 3. Virtual Stain 생성 및 WSI Overlay 표시 방법

### 핵심 발명 방향

H&E 또는 IHC 등 입력 슬라이드로부터 virtual stain 결과를 생성하고, 이를 WSI viewer에서 원본과 정렬된 overlay 또는 split view로 표시하는 방법.

### 포함 기술

- WSI patch 단위 virtual stain inference
- patch overlap blending 및 tile boundary artifact 완화
- uncovered/uncertain 영역 처리
- generated virtual stain 결과의 tile pyramid cache 생성
- 원본 WSI와 virtual stain 결과의 coordinate alignment
- overlay opacity 조절 및 split view 표시
- virtual stain 결과를 기존 tile viewer와 동일한 viewport/pan/zoom interaction으로 탐색
- virtual stain cache 재사용 및 모델 결과 상태 표시

### 청구항 후보

- WSI를 patch 단위로 분할하여 virtual stain inference를 수행하고 overlap 영역을 blending하는 방법
- virtual stain 결과를 tile pyramid로 변환하여 viewer에서 on-demand streaming하는 방법
- 원본 slide tile과 virtual stain tile을 동일 좌표계에서 overlay 또는 split view로 표시하는 방법
- virtual stain 결과의 불확실 영역 또는 미처리 영역을 시각적으로 구분하는 방법

### 분리 가능 포인트

모델 architecture 자체가 충분히 독창적이면 별도 출원 가능하다. 현재 후보는 inference 결과 생성, cache, viewer 표시까지 포함한 시스템 방법으로 정리한다.

## 4. AI-assisted WSI Annotation Workflow

### 핵심 발명 방향

WSI annotation 생성, 수정, patch 작업, cell-level assistance, AI 결과 수정 및 human feedback loop를 하나의 병리 workflow로 통합하는 방법.

### 포함 기술

- polygon, brush, rectangle, ruler, point 등 WSI annotation 도구
- required region 지정 및 patch 생성 workflow
- patch list와 labeling 상태 관리
- cell-level assistance 결과 표시 및 사용자 수정
- AI 결과와 사용자 annotation의 연결
- undo/redo, merge, cut, class 변경 등 annotation editing
- AI assistance를 통해 labeling 대상 또는 cell 후보를 제안하고 사용자가 검수/수정하는 흐름
- 수정된 annotation 또는 cell edit를 이후 분석/검수 workflow에 반영하는 구조

### 청구항 후보

- 사용자가 WSI 상에서 required region을 지정하고 해당 영역 기반 patch labeling task를 생성하는 방법
- AI assistance가 patch 또는 cell 후보를 생성하고 사용자가 이를 검수/수정하는 방법
- WSI annotation, patch annotation, cell annotation을 동일 좌표계와 작업 상태로 연결하는 방법
- 사용자 수정 이력을 undo/redo 및 audit 가능한 형태로 관리하는 방법
- AI 결과와 human annotation feedback을 결합하여 다음 분석 또는 검수 단계에 반영하는 방법

### 분리 가능 포인트

annotation 자체와 AI assistance feedback loop를 별도 출원으로 나눌 수 있으나, 현재는 workflow 중복이 많으므로 하나의 출원 후보로 묶는 것이 적절하다.

## 권장 출원 구조

### 1차 출원 우선순위

1. WSI Viewer 및 Adaptive Tile Streaming 방법
2. Virtual Stain 생성 및 WSI Overlay 표시 방법
3. AI-assisted WSI Annotation Workflow
4. 대규모 병리 AI 정량 결과의 실시간 시각화 방법

### 이유

- Viewer/tile streaming은 제품 전체 UX와 서버 성능의 기반 기술이다.
- Virtual stain은 의료 AI 제품에서 독립적인 차별성이 크다.
- Annotation workflow는 데이터 생성, 검수, AI assistance를 연결하는 제품 핵심 workflow다.
- Quanti visualization은 모델 결과 표시 기술로 중요하지만, viewer 기반 기술과 일부 겹치므로 청구항 경계를 명확히 해야 한다.

## 변리사 상담 시 확인할 질문

- 각 후보를 단일 시스템 특허로 묶을지, 방법 특허와 장치/시스템 특허를 병행할지
- viewer/tile streaming과 Quanti visualization 사이의 청구항 중복 가능성
- virtual stain에서 모델 architecture까지 청구할지, inference/cache/viewer pipeline 중심으로 청구할지
- annotation workflow에서 AI assistance와 human feedback loop를 얼마나 넓게 잡을지
- 공개된 OpenSeadragon, QuPath, ASAP, PathPresenter 등 기존 prior art 대비 차별 포인트

