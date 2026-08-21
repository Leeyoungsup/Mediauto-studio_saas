# MeDIAuto Studio SaaS 페이지별 기능 정리

> 기준일: 2026-08-21  
> 기준: 현재 프론트엔드 화면과 실제 이벤트·API 코드  
> 전체 기술·보안·데이터 구조는 [PROJECT_FEATURE_ANALYSIS.md](PROJECT_FEATURE_ANALYSIS.md) 참고

## 페이지 목록

| 페이지 | URL | 주요 목적 |
| --- | --- | --- |
| 시작 | `/` | 로그인 상태에 따른 자동 이동 |
| 로그인·가입 | `/login` | 인증, 회원가입, MFA |
| Home | `/home` | 대시보드, 최근 슬라이드, 빠른 작업 |
| Project | `/project` | 프로젝트 조회·생성·수정·삭제 |
| Data Linkage | `/data-linkage` | 케이스별 슬라이드·임상정보 연결 |
| AI | `/ai` | WSI 확인과 AI 분석·결과 편집 |
| Tissue Annotation | `/annotation`, `/tissue-annotation` | WSI 영역 주석과 검토 워크플로 |
| Cell Annotation | `/cell-annotation` | 패치 기반 세포 라벨링 워크플로 |
| Upload | `/upload` | 대용량 WSI 청크 업로드 |
| Profile | `/profile` | 내 정보와 비밀번호 변경 |
| Admin | `/admin` | 사용자·활동·백그라운드 워커 관리 |

## 1. 시작 페이지

### URL

`/`

### 역할

애플리케이션에 처음 접근했을 때 로그인 상태를 확인하는 진입점이다.

### 동작

- Access Token이 있으면 `/home`으로 이동
- Access Token이 없으면 `/login`으로 이동
- 별도의 사용자 입력이나 화면 기능은 없음

## 2. 로그인·회원가입 페이지

### URL

`/login`

### 목적

로그인, 신규 계정 신청, MFA 인증을 한 화면에서 처리한다.

### 로그인 기능

- Login ID와 Password 입력
- MFA가 활성화된 계정은 첫 로그인 응답 후 6자리 TOTP 입력란 표시
- 로그인 성공 시 Access Token, Refresh Token, 사용자 정보를 localStorage에 저장
- 로그인 완료 후 Home으로 이동
- 이미 Access Token이 있으면 자동으로 Home으로 이동

### 회원가입 기능

- Sign in / Sign up 모드 전환
- Name 필수
- Department 선택 입력
- Login ID 규칙:
  - 4~30자
  - 영문, 숫자, 밑줄만 허용
- Password 규칙:
  - 8자 이상
  - 영문 대문자 포함
  - 영문 소문자 포함
  - 숫자 포함
  - 특수문자 포함
- 첫 가입자는 자동 승인된 Admin으로 생성
- 이후 가입자는 Viewer·Pending·Inactive 상태로 생성되어 관리자 승인이 필요

### 오류·보안 처리

- FastAPI validation 오류를 사용자 메시지로 변환
- 승인 대기, 거절, 비활성, 잠금 상태 메시지 표시
- 로그인 5회 실패 시 계정이 30분 잠김
- 로그인·가입 요청은 IP당 5분 10회 제한

### 관련 API

- `POST /api/auth/login`
- `POST /api/auth/register`
- `POST /api/auth/refresh`

### 현재 제한

- MFA 활성화·비활성화 화면은 없으며 로그인 시 코드 입력만 제공

## 3. Home 페이지

### URL

`/home`

### 목적

로그인 후 전체 현황을 확인하고 최근 작업이나 주요 메뉴로 빠르게 진입한다.

### 상단 헤더

- Home 활성 표시
- Project, Data Linkage, AI 메뉴
- Annotation 하위 Tissue/Cell 메뉴
- Admin 사용자에게 Admin 메뉴 표시
- 사용자 이름에서 Profile 이동
- 로그아웃
- 현재 버전 표시

### 저장공간 현황

- 사용 중인 저장공간
- 전체 저장공간
- 사용률 progress bar

### 최근 슬라이드

- 최근 열어본 슬라이드 카드
- 슬라이드 썸네일
- 파일명, 크기, 마지막 접근 시각
- AI 또는 Annotation 상태 badge
- 마지막으로 열었던 AI/Tissue/Cell 작업공간으로 다시 열기
- 미디어 티켓을 이용한 인증 썸네일

### 빠른 작업

- AI Viewer 열기
- Upload 팝업 열기
- Profile 열기
- Admin 열기
- Viewer에게는 Upload 빠른 작업이 숨겨짐
- Admin 빠른 작업은 Admin에게만 표시

### 프로젝트 현황

- 프로젝트 목록
- 프로젝트별 슬라이드 수
- 상태 badge
- Slides by Project 차트
- Slides by Hospital 차트
- 차트 hover 상세 정보
- 프로젝트 목록 10개 단위 페이지 이동

### 프로젝트 동작

- 프로젝트 Open
- 프로젝트 Info/Edit
- 빈 프로젝트 Delete
- Open 시 진입 위치 선택:
  - AI
  - Tissue Annotation
  - Cell Annotation

### 권한

| 동작 | Admin | Doctor | Labeler | Viewer |
| --- | :---: | :---: | :---: | :---: |
| 현황·최근 슬라이드 보기 | O | O | O | O |
| 프로젝트 생성·수정 | O | O | - | - |
| 프로젝트 삭제 | O | - | - | - |
| 빠른 Upload | O | O | O | 숨김 |
| Admin 진입 | O | - | - | - |

### 관련 API

- `GET /api/slides/dashboard`
- `GET /api/slides/projects`
- `GET /api/slides/folder-tree`
- 프로젝트 생성·수정·삭제 API
- 썸네일·미디어 티켓 API

## 4. Project 페이지

### URL

`/project`

### 목적

프로젝트 메타데이터와 자동화 설정을 관리한다.

### Home과의 관계

- Home과 같은 HTML 구조 및 `home.js` 사용
- Project 메뉴가 활성화된다는 점이 주요 차이
- 최근 슬라이드, 저장공간, 차트, 빠른 작업도 함께 표시됨

### 프로젝트 생성·수정 필드

- Title
- Hospital/Institution
- Department
- Owner
- Status:
  - Active
  - In Progress
  - Review
  - Done
  - Archived
- Due Date
- Description

### 프로젝트 자동 AI

- 자동 AI 활성화 여부
- 여러 AI 작업 동시 선택 가능
- Quanti HE:
  - Stomach
  - Breast
  - Other
- Quanti PD-L1:
  - Stomach CPS
  - Lung TPS
- Quanti IHC:
  - HER2
  - ER/PR Allred
  - KI-67
- VS IHC:
  - IHC → Virtual H&E
  - Target MPP 4.0 / 2.0 / 1.0 / 0.5 µm/px

### Cell Annotation AI assistance

- Assistance 활성화 여부
- 한 프로젝트에 한 모델 선택
- Inherited AI:
  - Quanti HE Breast/Stomach/Other
  - PD-L1 Stomach/Lung
  - IHC HER2/ER_PR/KI_67
- Non-inherited AI:
  - HnE
  - IHC Membrane
  - IHC Nucleus
  - IHC Membrane (Breast)
  - IHC Nucleus (Breast)

### 프로젝트 삭제 조건

- Admin만 가능
- 프로젝트가 비어 있어야 함
- 삭제 전 confirm 표시

### 부분 구현 기능

- 프로젝트 이름변경 API와 함수가 있음
- 프로젝트를 다른 폴더로 이동하는 API·dialog 코드가 있음
- 현재 기본 프로젝트 행에는 이름변경·이동 버튼이 직접 노출되지 않음

### 관련 API

- `POST /api/slides/project/create`
- `POST /api/slides/project/update`
- `POST /api/slides/project/rename`
- `POST /api/slides/project/move-folder`
- `POST /api/slides/project/delete`

## 5. Data Linkage 페이지

### URL

`/data-linkage`

### 목적

파일명에서 추출한 케이스를 기준으로 관련 슬라이드를 묶고 공통 임상정보를 입력한다.

### 검색·필터

- Project 필터
- Hospital 필터
- Sample No 검색
- Sample No에서 Enter로 검색 실행
- 15/30/50행 페이지 크기

### 케이스 목록

- 순번
- Case ID
- Clinical Information 보유 여부
- Last Activity
- Case ID, 임상정보 여부, 최근 활동 정렬
- 이전/다음과 숫자 페이지 이동
- 페이지가 많으면 ellipsis 표시

### 케이스 ID 처리

- `CODIPAI-` 형식은 이후 3개 구간으로 케이스 ID 구성
- 일반 파일명은 첫 3개 하이픈 구간을 케이스 ID로 사용
- 같은 케이스의 임상정보는 연결된 모든 슬라이드가 공유

### 선택 케이스 상세

- Year
- Sample ID
- 연결된 슬라이드 thumbnail 목록
- 현재 선택 슬라이드 이름
- 선택 슬라이드 큰 preview

### Preview 조작

- `+` Zoom In
- `-` Zoom Out
- `H` 모양 버튼으로 Reset
- `[]` 모양 버튼으로 Fit; 현재 구현은 Reset과 같은 동작
- 마우스 휠 cursor 중심 zoom
- 좌클릭·pointer drag로 preview 이동
- 현재 zoom percentage 표시

`H`와 `[]`는 버튼에 쓰인 표기이며 키보드 단축키는 아니다.

### 임상정보

- ER proportion score
- ER intensity score
- PR proportion score
- PR intensity score
- Ki67 index
- PD-L1 CPS score
- ISH for HER2:
  - ISH negative
  - ISH positive
  - not tested
  - na
- IHC for C-erbB2
- 변경 전 Not saved 상태 표시
- Save 버튼으로 케이스 공통 정보 저장
- 미저장 변경이 있으면 페이지 이탈 경고

### 관련 API

- `GET /api/slides/cases`
- `PATCH /api/slides/cases/{case_name}/clinical-info`
- thumbnail·preview API

### 주의사항

- 케이스 임상정보 변경 API에는 현재 역할 제한이 없어 Viewer의 직접 호출 가능성을 점검해야 함

## 6. AI 페이지

### URL

`/ai`

### 목적

WSI를 탐색하고 ROI 또는 전체 슬라이드에 AI를 실행한 뒤 결과를 확인·편집·저장·시각화한다.

### 6.1 프로젝트 선택 화면

URL에 slide/path 정보가 없으면 Project Gate가 먼저 표시된다.

- 프로젝트·담당자·병원·부서 통합 검색
- Hospital, Owner, Status 필터
- 10/30/50행 설정
- 추가 조건:
  - Has slides
  - Has folders
  - Min slides
- Project, Hospital, Owner, Slides, AI Analyzed, Folders, Status 정렬
- 첫/이전/다음/마지막 페이지
- Open으로 프로젝트 진입

### 6.2 왼쪽 슬라이드 패널

- Breadcrumb 폴더 이동
- New Folder
- 프로젝트 이름변경·삭제 버튼; 역할에 따라 비활성
- 슬라이드 이름 검색
- 목록/그리드 보기 전환
- 폴더와 슬라이드 thumbnail
- 임상정보 badge
- AI 상태 badge
- AI 실행 상태 polling
- 우클릭 파일·폴더 메뉴
- 파일·폴더 drag & drop 이동
- 운영체제 파일 drop upload
- Ctrl+휠로 thumbnail 크기 변경
- Ctrl/Cmd 클릭 다중 선택
- Shift 클릭 범위 선택
- 빈 영역 marquee 선택

### 6.3 상단 툴바

- Slide Info
- Same Case
- Fit
- Zoom In / Out
- Polygon ROI
- Polygon Brush ROI
- Rectangle ROI
- 고정 1 mm² Rectangle
- 고정 1 mm² Circle
- Ruler
- Shortcuts 도움말
- Scanner/vendor, 배율, MPP 표시

AI 페이지에는 Point와 Cut 도구가 없다.

### 6.4 Viewer

- 3-stage WSI tile rendering
- thumbnail 및 인접 stage fallback
- tile fade-in
- 미니맵 이동·크기 변경·접기
- 좌우 panel 크기 변경·접기
- 모바일 drawer
- Hamamatsu NDP 색보정
- VS overlay/split rendering
- AI 결과 cell overlay
- ROI annotation overlay

### 6.5 Slide Info

- 파일명
- Vendor
- Magnification
- Pixel dimensions
- MPP
- Physical dimensions
- 임상정보 8개 필드 편집
- 변경된 상태로 닫기 또는 Esc 시 자동 저장

### 6.6 Same Case / Multi View

- 현재 슬라이드와 같은 케이스를 모든 프로젝트에서 검색
- AI 결과 보유 badge
- 최대 4개 선택
- 단일 View 또는 Multi View 선택
- 각 pane별 Fit
- pane 클릭으로 활성 슬라이드 선택
- 활성 pane에서 AI/Annotation/Info 기능 수행
- 종료 시 원래 화면 복원

### 6.7 AI 주제

| 주제 | 기능 |
| --- | --- |
| VirtualStain | IHC를 Virtual H&E로 변환 |
| Quanti | HE, PD-L1, IHC 정량 분석 |
| Dx | 현재 placeholder |
| Px | 현재 placeholder |

### 6.8 Quanti HE

- Breast, Stomach, Other 선택
- ROI가 있으면 ROI만, 없으면 전체 슬라이드 분석
- 세포 분류:
  - Neutrophil
  - Epithelial
  - Lymphocyte
  - Plasma
  - Eosinophil
  - Stromal cell
  - Tumor Epithelial
  - Benign Epithelial
- Breast/Stomach은 epithelial segmentation 재분류
- Stromal cell 기본 숨김
- 50,000개 초과 가시 셀은 raster rendering

### 6.9 Quanti PD-L1

- Stomach CPS
- Lung TPS
- Stomach:
  - 음성/양성 Epithelial
  - 음성/양성 Lymphocyte
  - 음성/양성 Macrophage
  - Other
- Lung:
  - Negative Tumor
  - Positive Tumor
  - Non-Tumor
- Other/Non-Tumor는 기본 숨김 및 score 제외
- confidence score 기준 0.1 고정

### 6.10 Quanti IHC

- HER2:
  - 0+, 1+, 2+, 3+, Other
  - weighted score와 dominant class
- ER/PR:
  - Allred PS + IS = TS
  - TS 3 이상 Positive
- KI-67:
  - Positive / Total labeling index
  - 14% 이상 High

### 6.11 VS IHC

- 실제 변환 방향: IHC → Virtual H&E
- `ihc_membrane` 모델
- 4.0 / 2.0 / 1.0 / 0.5 µm/px
- Overlay on/off
- Split View: IHC | Virtual H&E
- divider 5~95% drag
- ROI가 있으면 ROI 안에만 표시
- 실행 중 같은 버튼을 누르면 cancel 요청

### 6.12 AI 결과 패널

- 클래스별 count
- 개별 클래스 표시/숨김
- 전체 클래스 표시/숨김
- 결과 cell 추가·삭제·재분류
- 다중 cell lasso 편집
- 숨겨진 Other cell 승격
- 점수 즉시 재계산
- Clear Results
- Save Results
- Load Results
- 사용자별 저장본 목록
- 본인 저장본 삭제
- 원본 AI cache는 사용자 편집본과 분리

### 6.13 시각화

- Class Distribution bar/pie
- 모델별 분석 카드
- Spatial Heatmap
- Segmentation overlays
- Confidence histogram
- A4 landscape PDF export
- File System Access API 또는 browser download

### 6.14 주요 단축키

| 입력 | 동작 |
| --- | --- |
| 휠 | viewport 중앙 기준 zoom |
| 좌클릭/가운데 버튼 drag | pan |
| Ctrl+Z | ROI 또는 AI cell 편집 undo |
| Ctrl+Y, Ctrl+Shift+Z | redo |
| Esc | draw mode·popup·Alt lasso 취소 |
| Delete | 선택 ROI 삭제 |
| Alt+좌클릭 | 가까운 AI cell 편집 |
| Alt+좌drag | 가시 AI cell lasso |
| Alt+우클릭 | AI cell 추가 |
| Alt+우drag | 숨겨진 Other cell lasso |
| Alt+A | sticky class picker |
| 1~9/0 | 열린 cell popup 클래스 선택 |
| Delete/D | 선택 AI cell 삭제 |
| Shift+ROI drag | ROI 전체 이동 |
| Alt+polygon edge click | vertex 삽입 |
| Ctrl+같은 클래스 polygon click | 병합 |
| Alt+휠 | Brush 크기 변경 |

### 권한

- Admin/Doctor: AI 실행, 결과 편집, Save/Load 가능
- Labeler: AI 실행 가능, 결과 직접 편집과 Save/Load 불가
- Viewer: AI 실행과 ROI 편집 불가

### 관련 API

- `POST /api/ai/detect`
- `POST /api/ai/pd-score`
- `POST /api/ai/precise-ihc`
- `POST /api/ai/virtual-stain`
- AI task 상태·취소·결과 API
- AI user edit save/list/load/delete API

### 주의사항

- PDF용 jsPDF를 외부 CDN에서 불러오므로 폐쇄망에서 실패할 수 있음

## 7. Tissue Annotation 페이지

### URL

`/annotation`, `/tissue-annotation`

두 URL은 같은 화면을 연다.

### 목적

WSI 조직 영역을 클래스별로 주석하고 Annotation→Review→Termination 상태를 관리한다.

### 7.1 프로젝트·슬라이드 선택

- AI 페이지와 같은 Project Gate
- 프로젝트 검색·필터·정렬·페이지네이션
- 폴더 breadcrumb
- 슬라이드 검색 및 목록/그리드
- 임상정보, 메모, Annotation 상태 표시
- 파일·폴더 drag & drop
- 다중 선택과 context menu

### 7.2 툴바

- Slide Info
- Fit, Zoom In/Out
- Polygon
- Polygon Brush
- Rectangle
- Point
- Cut
- 고정 1 mm² Rectangle
- 고정 1 mm² Circle
- Ruler
- Slide Memo
- Shortcuts

### 7.3 주석 클래스

- 프로젝트별 클래스 목록
- 새 클래스 추가
- 이름 변경
- 색상 변경
- 삭제
- drag로 순서 변경
- 표시/숨김
- 현재 active class 선택
- 선택 주석에 active class 적용
- 최소 한 클래스 유지
- Admin/Doctor만 클래스 구조 관리

### 7.4 주석 목록

- 순번형 Annotation ID
- 클래스
- Memo
- 표시/숨김
- 삭제
- 행 선택 시 WSI 주석 선택
- ID 더블클릭 시 주석 중앙 이동
- 우클릭 시 Memo 열기
- 숫자 1~9/0으로 선택 주석 클래스 적용

### 7.5 주석 편집

- vertex/corner drag
- Shift+drag 전체 이동
- Alt+edge hover로 vertex 삽입 preview
- Alt+edge click으로 vertex 삽입
- Ctrl+overlap hover로 merge preview
- Ctrl+click으로 같은 클래스 polygon 병합
- Cut 도구로 선택 polygon 경계 재작성
- Brush 크기 Alt+휠 조절
- Ruler 수평·수직 ±2° snap

### 7.6 표시 스타일

- Line 1~12px
- Fill 0~80%, 5% 단위
- 계정 preference로 저장
- 같은 계정의 모든 Tissue Annotation에 적용

### 7.7 저장·불러오기

- 슬라이드 열 때 서버 저장 주석 자동 load
- Save 버튼으로 서버 내부 JSON 저장
- Ctrl/Cmd+S 저장
- Clear All은 현재 화면 주석 전체 제거
- JSON 파일 download/upload 함수는 코드에 있으나 현재 UI에는 연결되지 않음

### 7.8 Memo

- Slide Memo
- Annotation별 Memo
- 기존 Memo history
- 답변 작성
- 답변 accept
- 현재 Memo 삭제
- 과거 history 항목 삭제
- Memo가 있는 슬라이드에 M badge
- Ctrl/Cmd+M으로 Slide Memo 열기

### 7.9 Workflow

- Annotation
- Review
- Termination
- 현재 단계 클릭으로 Running/Done 상태 진행
- 완료 후 다음 단계 활성화
- 완료·Running·현재·Pending·Rejected 시각 상태
- 슬라이드 목록에도 단계별 상태 표시
- Labeler는 Annotation 중심으로 제한

### 7.10 AI assistance

- 오른쪽 AI 영역은 현재 CSS상 VS IHC만 노출
- IHC → Virtual H&E 생성
- Overlay 및 Split View
- 다른 Quanti markup과 로직은 HTML/JS에 남아 있지만 Tissue 화면에서는 숨겨짐

### 7.11 주요 단축키

| 입력 | 동작 |
| --- | --- |
| Ctrl+S | 저장 |
| Ctrl+M | Slide Memo |
| Ctrl+Z | undo |
| Ctrl+Y / Ctrl+Shift+Z | redo |
| 1~9/0 | 선택 주석 클래스 1~10 지정 |
| Delete | 선택 주석 삭제 |
| Esc | draw mode·popup 닫기 |
| Shift+drag | 주석 이동 |
| Ctrl+drag | 주석 위에서 pan |
| Alt+휠 | Brush 크기 |
| Alt+edge click | polygon vertex 삽입 |
| Ctrl+overlap click | 같은 클래스 polygon 병합 |

### 관련 API

- `GET/POST /api/slides/annotation-classes`
- `GET/POST /api/slides/{slide_id}/annotations/...`
- 슬라이드 상태·임상정보 API
- VS IHC API

## 8. Cell Annotation 페이지

### URL

`/cell-annotation`

### 목적

WSI에서 필요한 영역을 지정하고 고정 크기 패치 단위로 세포 bounding box와 클래스를 라벨링·검토·종결한다.

### 8.1 프로젝트 선택

- 공통 Project Gate
- 프로젝트 검색·필터·정렬
- 프로젝트별 Cell Annotation 클래스 설정
- Termination 완료 개수 표시
- 특정 계정 `YoungSeopLee`에게 완료 패치 ZIP export 표시

### 8.2 패치 규격

- Target MPP: 0.5 µm/px
- 물리 크기: 512 µm × 512 µm
- 표준 이미지: 1024 × 1024px
- 사용자 표시 ID: `patch_N`
- 내부 좌표 식별자: `patch_key`

### 8.3 WSI View

- Required 영역 polygon 그리기
- Exclude 영역 polygon 그리기
- Required 초록, Exclude 빨강
- 적용 전 pending patch preview
- Apply로 required patch 증분 추가 및 exclude patch 제거
- 적용 후 pending 영역 초기화
- Ctrl/Cmd+Z로 적용 전 영역 undo
- WSI 위 패치 상태 overlay
- 선택 패치 강조
- 전체 패치 삭제:
  - Admin/Doctor만 가능
  - 5초 countdown
  - 패치 상태, 라벨, 이미지, sidecar 제거

### 8.4 Patch 목록

- Patch
- Annotation
- Review
- Termination
- Memo
- 열별 정렬
- 대량 목록 render 제한
- click 선택
- Enter/Space 선택
- 더블클릭 Patch View 진입
- 우클릭 Memo/Remove Required 메뉴
- Required, Running, Done, Rejected 상태 표시

### 8.5 WSI/Patch 전환

- `P`로 WSI View와 Patch View 전환
- Patch View 종료 시 이전 WSI viewport 복원
- Patch View는 선택 patch 범위 밖으로 이동 제한
- Fit Patch
- patch 범위에서 pan과 zoom
- VS overlay/split을 patch 안으로 clip

### 8.6 Cell 그리기·선택

- Rectangle로 cell bbox 생성
- 화면 표시를 BBox 또는 Point로 변경
- 실제 저장 데이터는 bbox 유지
- 단일 셀 click 선택
- checkbox 다중 선택
- Alt+click 선택 toggle
- Alt+drag lasso 다중 선택
- 전체 선택 checkbox
- 선택 셀 클래스 일괄 적용
- 선택 셀 일괄 삭제
- 1~9/0으로 클래스 1~10 지정
- Delete/Backspace/D로 삭제
- Esc로 다중 선택 해제

### 8.7 클래스 패널

- 클래스 목록과 색상
- active class
- 클래스별 표시/숨김
- 전체 표시/숨김
- 클래스 행 클릭 시 선택 cell에 즉시 적용
- Ctrl/Cmd+1~9/0으로 클래스 visibility toggle
- Ctrl/Cmd+`로 전체 visibility toggle
- AI/필수 클래스와 Other:
  - 이름 변경 잠금
  - 색상 변경 잠금
  - 삭제 잠금
  - 순서 변경 가능
- Custom class 유지

### 8.8 저장 조건

- Annotation이 Running인 패치만 편집·draft Save 가능
- Annotation Done 변경 시 현재 라벨 자동 저장
- 빈 Required 패치만 AI assistance 자동 load
- 기존 수동 라벨이 있으면 assistance가 덮어쓰지 않음

### 8.9 패치 Workflow

Annotation:

- Required
- Running
- Done

Review:

- Pending
- Done
- Rejected

Termination:

- Pending
- Current
- Done

세부 동작:

- Review Rejected 시 Annotation 편집 재개 가능
- WSI 상단 상태는 전체 패치 완료율로 자동 계산
- 슬라이드 목록에 Annotation/Review/Termination 단계 요약
- 프로젝트 breadcrumb에 Termination 완료/전체 개수 표시

### 8.10 역할

Admin/Doctor:

- Required/Exclude 영역 관리
- 패치 추가·삭제
- Cell 라벨 편집
- Review/Termination
- Memo
- 전체 삭제

Labeler:

- WSI 영역 설정 불가
- Review/Termination 불가
- Memo 변경 불가
- Annotation Running 또는 Review Rejected 패치만 편집
- Annotation 단계만 변경

Viewer:

- 읽기 전용

### 8.11 AI assistance

- 프로젝트에서 설정된 한 모델 사용
- 전체 required patch 대상 AI 실행
- 진행률과 작업 상태 표시
- inherited/non-inherited class mapping
- hidden Other도 assistance 파일에 보존
- 오래된 후처리 cache 자동 무효화

### 8.12 Sidecar·내보내기

- `patches/*.jpeg`
- `labels/*.json`
- `info.json`
- `WSI_Labeling_assistance.json`
- 변경 사항 background coalesced export
- 조건 충족 시 Termination 완료 patch ZIP

### 8.13 주요 단축키

| 입력 | 동작 |
| --- | --- |
| P | WSI ↔ Patch View |
| Ctrl+S | 선택 patch 저장 |
| Ctrl+Z | pending region 또는 cell edit undo |
| Ctrl+Y / Ctrl+Shift+Z | redo |
| 1~9/0 | 선택 cell 클래스 지정 |
| Ctrl+1~9/0 | 클래스 표시/숨김 |
| Ctrl+` | 모든 클래스 표시/숨김 |
| Delete/Backspace/D | 선택 cell 삭제 |
| Alt+click | cell 선택 toggle |
| Alt+drag | cell lasso 선택 |
| Esc | 선택·draw mode 취소 |
| Patch 행 Enter/Space | patch 선택 |
| Patch 행 더블클릭 | Patch View |
| Patch 행 우클릭 | patch context menu |

### 관련 API

- 프로젝트 클래스 API
- grid config
- required regions
- patch list/delete/recompute
- patch cell load/save
- patch workflow update
- WSI labeling assistance options/run/task/result
- termination export

## 9. Upload 페이지

### URL

`/upload`

### 목적

프로젝트와 폴더를 선택해 대용량 WSI를 안정적으로 업로드한다. 일반적으로 팝업 창으로 열린다.

### 대상 위치

- Project 필수
- Project의 하위 Folder 선택
- 호출한 작업공간의 현재 경로를 기본 위치로 전달 가능

### 파일 선택

- Browse
- Drag & Drop
- 여러 파일 선택
- 지원 확장자만 queue에 추가
- 같은 이름·크기의 중복 queue 제거

### 지원 확장자

`.svs`, `.ndpi`, `.vms`, `.vmu`, `.scn`, `.mrxs`, `.tiff`, `.tif`, `.png`, `.jpg`, `.jpeg`, `.isyntax`, `.i2syntax`

### 업로드 과정

1. Upload session 시작
2. 5 MB 단위 chunk 전송
3. 진행률 90%까지 upload 구간 표시
4. Complete 요청과 서버 등록
5. OpenSlide 또는 Philips validation
6. 성공 후 다음 파일 처리

### 인증·안정성

- 약 5분 간격 token keepalive
- 401 시 refresh 후 한 번 재시도
- 파일은 순차 처리
- 진행 중 창 닫기 경고
- 한 파일 실패 시 다음 파일 계속
- 최대 파일 크기 기본 20 GB

### 중복 파일

- 기존 파일과 충돌하면 conflict panel 표시
- 파일별 Overwrite 또는 Skip
- Overwrite 시 기존 파일 관련 데이터를 정리한 후 다시 업로드:
  - 원본
  - 타일
  - AI 결과
  - 사용자 AI 편집본
  - Tissue Annotation
  - Cell Annotation
  - DB metadata

### 완료

- Uploaded 수
- Failed 수
- Skipped 수
- opener에 `upload-complete` 메시지 전송
- 원래 페이지의 슬라이드 목록 자동 갱신

### 관련 API

- `POST /api/slides/upload/start`
- `POST /api/slides/upload/chunk`
- `POST /api/slides/upload/complete`
- 폴더·프로젝트 목록 API

### 주의사항

- 현재 일부 업로드 endpoint의 서버 측 역할 검사가 충분하지 않으므로 Viewer 직접 API 호출을 점검해야 함

## 10. Profile 페이지

### URL

`/profile`

### 목적

현재 사용자의 기본 정보와 비밀번호를 관리한다.

### Account Information

- Login ID: 읽기 전용
- Name: 수정 가능
- Department: 수정 가능
- Role: 읽기 전용
- Save Profile

### Change Password

- Current Password
- New Password
- Confirm New Password
- 비밀번호 정책 안내
- 현재 비밀번호 검증
- 새 비밀번호 일치 확인
- 변경 성공 시 모든 token·session을 폐기하고 로그인 화면으로 이동

### 관련 API

- `GET /api/auth/me`
- `POST /api/users/me`
- `POST /api/auth/change-password`

### 현재 빠진 기능

- MFA 설정 시작
- QR/otpauth 정보 표시
- MFA 최초 코드 검증
- MFA 비활성화

해당 기능은 API에는 있으나 Profile UI에는 없다.

## 11. Admin 페이지

### URL

`/admin`

### 접근 권한

Admin 전용이다. 비관리자는 화면과 API 모두 접근이 차단되어야 한다.

### 11.1 Pending 탭

- 승인 대기 사용자 목록
- 사용자 이름, ID, 부서, 가입 시각
- Approve
- 승인 시 역할 선택:
  - Viewer
  - Labeler
  - Doctor
  - Admin
- Reject
- 선택적 거절 사유

### 11.2 Users 탭

- 사용자 목록
- 20명 단위 페이지네이션
- 승인 상태 필터:
  - Approved
  - Pending
  - Rejected
- 이름·Login ID 검색과 debounce
- 사용자 Edit:
  - Name
  - Department
  - 선택적 New Password
- 역할 변경
- 활성/비활성 전환
- 계정 잠금 해제
- 사용자 삭제
- 본인 삭제·비활성 방지
- 마지막 Admin 제거 방지

### 11.3 Create 탭

- 관리자가 사용자 직접 생성
- 생성 즉시 승인·활성
- Login ID
- Name
- Department
- Password
- Role

### 11.4 Activity 탭

- 로그인 활동 50건 단위
- 사용자 필터
- 날짜·시간
- Login ID와 이름·역할
- IP
- 국가·지역·도시
- 브라우저·운영체제 형태의 device 정보
- Details로 사용자별 활동 dialog

사용자 상세 활동:

- 100건 단위
- 날짜 범위
- 페이지 이동
- 카테고리와 count badge:
  - All
  - Login
  - Slides
  - AI
  - Projects
  - Files
- action, 상세 정보, IP·위치 표시

### 11.5 Settings 탭

- AI Worker:
  - Enabled 상태
  - Running 상태
  - 즉시 on/off
- Tile Worker:
  - Enabled 상태
  - Running 상태
  - 즉시 on/off
- Refresh
- 설정은 MongoDB `app_settings`에 저장

### 관련 API

- 사용자 list/pending/create/approve/reject/update/delete
- role/toggle-active/unlock
- audit logs
- login activity
- user activity
- worker settings

### UI가 없는 관리자 API

- Audit Log HMAC chain 검증
- 파일 SHA-256 무결성 재검증
- 다른 사용자의 MFA 강제 해제 전용 UI

## 12. 전 페이지 공통 기능

### 인증

- 인증이 필요한 페이지는 Access Token이 없으면 Login으로 이동
- API 401 시 Refresh Token으로 자동 갱신
- 갱신 실패 시 localStorage를 정리하고 Login으로 이동
- Logout은 Refresh session 폐기 후 localStorage 정리

### 반응형 화면

- 작은 화면에서 좌·우 panel drawer
- overlay 클릭 또는 Esc로 drawer 닫기
- 터치 WSI pan/pinch
- panel width와 일부 UI 상태를 localStorage에 보존

### 공통 권한 주의

프론트엔드에서 버튼을 숨기거나 비활성화하는 기능과 서버 API의 권한 검사는 별개다. 현재 폴더·파일·일부 업로드·임상정보 endpoint에는 역할 검사가 누락된 부분이 있어 서버 측 보완이 필요하다.

### 공통 사용자 문구 주의

AI/Tissue 화면의 일부 loading, drop 안내, aria-label, UX 도움말에 `text text` 형태의 손상된 문자열이 남아 있다. 페이지별 기능 정리와 별도로 UI 문구 정비가 필요하다.

## 13. 페이지별 우선 개선 목록

| 페이지 | 우선 개선 |
| --- | --- |
| Login/Profile | MFA 설정·해제 UI 추가 |
| Home/Project | 중복 화면 구조 통합, rename/move 동작 노출 여부 결정 |
| Data Linkage | 임상정보 변경 서버 권한 보강 |
| AI | jsPDF 로컬화, 깨진 안내 문구 수정 |
| Tissue Annotation | 도움말의 줌 기준 수정, 숨겨진 레거시 AI/JSON 코드 정리 |
| Cell Annotation | 역할별 편집 조건을 UI에 더 명확하게 표시 |
| Upload | Viewer 업로드 정책 확정 후 서버 RBAC 적용 |
| Admin | Audit chain·파일 무결성·MFA 관리 UI 추가 |
| 전체 | MongoDB 장애 시 anonymous admin fallback 제거 |
