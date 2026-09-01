# MeDIAuto Studio SaaS 전체 기능·구조 분석

> 분석 기준: 2026-09-01 현재 저장소 코드
> 버전 메타데이터: `2.0.0` / production / 2026-09-01
> 분석 대상: 프론트엔드 화면·이벤트, FastAPI 라우트, AI 파이프라인, PostgreSQL 스키마, 운영 스크립트

이 문서는 기존 README나 사용자 가이드를 요약한 문서가 아니라, 현재 소스 코드에서 실제 동작을 교차 확인해 정리한 기능 인벤토리다. 사용자에게 노출되는 기능뿐 아니라 단축키, 마우스 조작, 역할별 제한, 조건부 기능, 백엔드 전용 기능, 자동화 및 현재 코드의 주의점까지 포함한다.

## 1. 제품 한눈에 보기

MeDIAuto Studio SaaS는 병원 온프레미스 환경을 대상으로 하는 디지털 병리 WSI(Whole Slide Image) 관리·뷰어·AI 분석·주석 플랫폼이다.

주요 업무 흐름은 다음과 같다.

1. 계정 가입 및 관리자 승인
2. 프로젝트 생성과 슬라이드 업로드
3. WSI 타일 뷰어에서 슬라이드 탐색
4. AI 분석 또는 Tissue/Cell Annotation 수행
5. 검토·종결 워크플로 진행
6. 임상정보 연결, 결과 시각화·PDF 내보내기, 관리자 감사

핵심 특징은 다음과 같다.

- 최대 20 GB WSI의 청크 업로드와 OpenSlide/Philips iSyntax 열기
- 3단계 JPEG 타일 피라미드와 미니맵 기반 WSI 뷰어
- Quanti HE, PD-L1, IHC 및 IHC→Virtual H&E 변환
- 사용자별 AI 결과 편집본과 원본 AI 캐시의 분리
- Tissue Annotation과 패치 기반 Cell Annotation의 별도 워크플로
- 폴더·프로젝트 단위 자동 AI, 백그라운드 타일 생성, 캐시 정리
- JWT, 승인형 계정, 역할 기반 권한, TOTP MFA API, 감사 로그

## 2. 구현 상태 표기

이 문서에서는 기능 상태를 다음처럼 구분한다.

| 표기 | 의미 |
| --- | --- |
| UI | 현재 화면에서 사용 가능 |
| 조건부 | 역할, 프로젝트 설정, 슬라이드 종류 또는 특정 계정 조건에서만 표시 |
| API | 백엔드에는 구현됐지만 현재 일반 UI에서 직접 진입할 수 없음 |
| 레거시 | 코드가 남아 있으나 현재 UI에서 연결되지 않음 |
| 주의 | 문서 불일치, 권한 누락 또는 운영상 위험이 확인됨 |

## 3. 기술 구조

### 3.1 기술 스택

| 영역 | 구현 |
| --- | --- |
| 백엔드 | Python 3.12, FastAPI 0.115, Uvicorn 0.30 |
| 프론트엔드 | Vanilla JavaScript ES Modules, HTML, CSS, Canvas; 별도 빌드 도구 없음 |
| 데이터베이스 | PostgreSQL 18, SQLAlchemy async, asyncpg, Alembic |
| WSI | OpenSlide, Pillow, OpenCV, ICC 색상 프로파일 |
| Philips | 별도 Python 3.7 SDK 브리지, persistent/CLI 모드, shared memory 지원 |
| AI | PyTorch, torchvision, YOLO 계열 검출, segmentation-models-pytorch, CUDA AMP |
| 인증 | JWT HS256, bcrypt cost 12 + pepper, Refresh Token, TOTP, AES-GCM |
| 기본 서비스 포트 | 8091 |

### 3.2 화면 라우트

| URL | 화면 |
| --- | --- |
| `/` | 토큰 유무에 따라 로그인 또는 홈으로 이동 |
| `/login` | 로그인·회원가입·MFA 코드 입력 |
| `/home` | 대시보드와 최근 슬라이드 |
| `/project` | 프로젝트 관리; 현재 홈과 거의 같은 화면·로직 |
| `/data-linkage` | 케이스별 슬라이드와 임상정보 연계 |
| `/ai` | AI 분석 WSI 워크스페이스 |
| `/annotation`, `/tissue-annotation` | Tissue Annotation 워크스페이스 |
| `/cell-annotation` | 패치 기반 Cell Annotation 워크스페이스 |
| `/upload` | 팝업형 대용량 업로드 화면 |
| `/profile` | 내 프로필·비밀번호 변경 |
| `/version` | 전체 버전 이력 검색·필터·변경 내용 조회 |
| `/admin` | 관리자 화면 |

기존 `.html` 주소는 현재 라우트로 308 리다이렉트된다.

### 3.3 공통 헤더

- Home, Project, Data Linkage, AI 메뉴
- Annotation 하위 Tissue Annotation, Cell Annotation 메뉴
- 관리자에게만 Admin 메뉴 표시
- 사용자 이름 클릭으로 Profile 이동
- 버전 배지 표시 및 클릭 시 Version History 이동
- 로그아웃 시 로컬 토큰 및 사용자 정보 제거

## 4. 계정·로그인·프로필

### 4.1 회원가입 및 승인

- 이름 필수, 부서 선택 입력
- 로그인 ID: 영문·숫자·밑줄만 허용, 4~30자
- 비밀번호: 8자 이상이며 대문자·소문자·숫자·특수문자를 모두 포함
- DB에 등록된 사용자가 없는 경우 첫 가입자가 자동 승인된 `admin`이 됨
- 이후 가입자는 기본 `viewer`, `pending`, 비활성 상태로 생성
- 관리자가 승인하면서 역할을 지정해야 로그인 가능
- 가입 거절 시 사유를 기록할 수 있음

### 4.2 로그인·세션

- Access Token 기본 수명 360분, Refresh Token 7일
- API 클라이언트는 Access Token 만료 시 Refresh Token으로 한 번 자동 갱신 후 요청 재시도
- Refresh Token rotation과 재사용 탐지 구현
- 5회 로그인 실패 시 30분 계정 잠금
- 로그인·회원가입은 IP당 5분 10회, 일반 API는 분당 200회, 업로드 API는 분당 2,000회 제한
- 타일·썸네일·일부 대시보드 요청은 일반 API rate limit에서 제외
- 이미지 URL에는 JWT 대신 10분짜리 HMAC 미디어 티켓 사용
- 상태 변경 요청은 `X-Requested-With` 헤더를 요구하는 CSRF 방어 적용

### 4.3 MFA

- 로그인 화면은 MFA가 활성화된 계정에만 6자리 TOTP 입력란을 표시
- TOTP 시드는 AES-GCM으로 암호화 저장
- MFA 설정, 최초 코드 검증, 상태 조회, 비활성화 API가 구현됨
- **API:** 현재 Profile 화면에는 MFA를 켜거나 끄는 UI가 없음

### 4.4 Profile

- 로그인 ID와 역할은 읽기 전용
- 이름과 부서 수정
- 현재 비밀번호 확인 후 새 비밀번호 변경
- 비밀번호 변경 시 모든 세션을 폐기하고 로그인 화면으로 이동

## 5. 역할과 권한

현재 실제 역할은 `admin`, `doctor`, `labeler`, `viewer` 네 가지다.

| 기능 | Admin | Doctor | Labeler | Viewer |
| --- | :---: | :---: | :---: | :---: |
| 관리자 화면·사용자 관리 | O | - | - | - |
| 프로젝트 생성·수정·이름변경·이동 | O | O | - | - |
| 빈 프로젝트 삭제 | O | - | - | - |
| AI 분석 실행 | O | O | O | - |
| AI 셀 결과 직접 편집 | O | O | - | - |
| AI 사용자 편집본 저장·불러오기 | O | O | - | - |
| Tissue Annotation 편집 | O | O | 제한적 | - |
| 주석 클래스 관리 | O | O | - | - |
| Cell WSI 필수·제외 영역 설정 | O | O | - | - |
| Cell 패치 라벨링 | O | O | 조건부 | - |
| Cell Review·Termination | O | O | - | - |
| 슬라이드 조회 | O | O | O | O |

Labeler의 세부 조건은 다음과 같다.

- AI 실행 자체는 가능하지만 AI 검출 셀 편집 및 사용자 저장본 Save/Load는 차단됨
- 프로젝트 생성·수정은 불가
- Cell Annotation에서는 Annotation이 Running이거나 Review가 Rejected인 패치만 편집 가능
- WSI 필수 영역 설정, 패치 제거, Review, Termination, 메모 변경은 불가

**주의:** 프론트엔드의 Viewer 제한과 백엔드 권한이 완전히 일치하지 않는다. 현재 코드상 폴더 생성·이름변경·삭제, 파일 삭제·상태변경·이동, 일부 업로드 및 임상정보 변경 API는 로그인만 확인하고 역할을 확인하지 않는다. 따라서 Viewer도 UI를 우회해 직접 API를 호출하면 변경이 가능할 수 있다. 운영 전 서버 측 역할 검사를 보강해야 한다.

## 6. Home 및 Project

`/home`과 `/project`는 같은 HTML 구조와 `home.js`를 사용하며 활성 메뉴만 달라진다.

### 6.1 대시보드

- 전체 저장공간 사용량, 총량, 사용률 표시
- 최근 열어본 슬라이드 카드와 썸네일
- 최근 슬라이드의 마지막 작업 화면(AI/Tissue/Cell)으로 다시 열기
- 프로젝트·폴더 트리 탐색
- 빠른 작업: AI Viewer, Upload, Profile, Admin
- Viewer에게는 빠른 Upload가 숨겨짐

### 6.2 프로젝트 목록과 통계

- 프로젝트 제목·설명, 병원, 담당자, 상태, 슬라이드 수, 기본 AI 설정 표시
- 프로젝트당 10개 페이지네이션
- Slides by Project, Slides by Hospital 도넛 차트와 hover 정보
- Open, Info/Edit, Delete 동작
- 프로젝트를 열 때 AI, Tissue Annotation, Cell Annotation 중 진입 화면 선택

### 6.3 프로젝트 생성·수정

- 제목, 병원/기관, 부서, 담당자, 상태, 마감일, 설명
- 상태: Active, In Progress, Review, Done, Archived
- 프로젝트 자동 AI 활성화와 복수 작업 선택
- Cell Annotation AI assistance 활성화와 단일 모델 선택
- 프로젝트 삭제는 Admin만 가능하고 폴더가 비어 있어야 함
- **API/부분 UI:** 프로젝트 rename·folder 이동 API와 대화상자 로직은 있지만 현재 홈 프로젝트 행의 주 동작에는 직접 노출되지 않음

### 6.4 프로젝트 자동 AI 선택지

- Quanti HE: Stomach, Breast, Other
- Quanti PD-L1: Stomach CPS, Lung TPS
- Quanti IHC: HER2, ER/PR Allred, KI-67
- VS IHC: `ihc_membrane`, 4.0 / 2.0 / 1.0 / 0.5 µm/px

### 6.5 Cell Annotation assistance 선택지

Inherited AI:

- Quanti HE Breast/Stomach/Other
- Quanti PD-L1 Stomach/Lung
- Quanti IHC HER2/ER_PR/KI_67

Non-inherited AI:

- HnE
- IHC Membrane
- IHC Nucleus
- IHC Membrane (Breast)
- IHC Nucleus (Breast)

## 7. 워크스페이스 진입 전 Project Gate

AI, Tissue Annotation, Cell Annotation URL에 슬라이드·경로 파라미터가 없으면 먼저 프로젝트 선택 화면을 표시한다.

- 검색 대상: 프로젝트 이름·경로·제목·병원·부서·담당자·상태·설명
- 병원, 담당자, 상태 드롭다운 필터
- 10/30/50행 페이지 크기, 기본 30행
- 추가 조건: 슬라이드 존재, 폴더 존재, 최소 슬라이드 수
- Project, Hospital, Owner, Slides, AI Analyzed, Folders, Status 열 정렬
- 첫/이전/다음/마지막 페이지 이동
- Cell Annotation에서는 프로젝트별 클래스 설정 진입
- **조건부:** 로그인 ID 또는 이름이 `YoungSeopLee`인 계정에 종결 완료 패치 ZIP 내보내기 제공

## 8. 슬라이드·폴더·업로드 관리

### 8.1 지원 형식

`.svs`, `.ndpi`, `.vms`, `.vmu`, `.scn`, `.mrxs`, `.tiff`, `.tif`, `.png`, `.jpg`, `.jpeg`, `.isyntax`, `.i2syntax`

### 8.2 슬라이드 목록

- 폴더 breadcrumb 이동, 폴더 생성·이름변경·삭제
- 슬라이드 이름 검색
- 목록/썸네일 그리드 보기 전환
- 목록에 임상정보, AI 상태, Annotation 워크플로 상태 표시
- Ctrl/Cmd 클릭 다중 선택, Shift 클릭 범위 선택
- 빈 영역 드래그 marquee 선택; modifier와 함께 추가 선택
- 선택 슬라이드를 폴더 또는 breadcrumb로 드래그해 이동
- 운영체제 파일을 목록에 드롭해 현재 폴더로 업로드
- 우클릭 컨텍스트 메뉴로 파일·폴더 작업
- Ctrl+휠로 슬라이드 썸네일 크기 조절
- AI 작업 상태는 약 4초 간격으로 polling

### 8.3 업로드 팝업

- 프로젝트 필수 선택, 하위 폴더 선택
- 파일 선택 또는 drag & drop, 여러 파일 큐
- 지원 확장자만 수용
- 같은 이름과 크기의 큐 중복을 사전 제거
- 파일당 5 MB 청크, 여러 파일은 순차 업로드
- 진행률은 업로드 구간을 90%까지 표시하고 이후 서버 등록 단계 표시
- 업로드 중 5분 간격 인증 keepalive 및 401 자동 갱신·재시도
- 업로드 중 창을 닫을 때 경고
- 완료 후 opener 창에 `upload-complete` 메시지를 보내 목록 갱신
- 동일 파일 충돌 시 파일별 Overwrite 또는 Skip 선택
- Overwrite는 기존 원본, 타일, AI 결과, 사용자 편집본, Tissue/Cell Annotation sidecar와 DB 레코드를 정리한 뒤 재업로드
- OpenSlide/Philips로 열 수 없는 파일은 실패 처리하고 다음 파일 계속 진행
- 최종 Uploaded / Failed / Skipped 요약

### 8.4 무결성 및 정리

- 업로드 완료 시 SHA-256 체크섬 저장
- **API:** 원본을 다시 읽어 체크섬과 비교하는 `verify-integrity`
- 삭제 시 원본, 타일, AI 캐시, 사용자 편집본, 주석, Cell sidecar 및 DB 메타데이터 정리
- 이동 시 경로 기반 캐시·sidecar 무효화 또는 정리

## 9. 공통 WSI 뷰어

### 9.1 렌더링

- 1024px JPEG 품질 85 타일
- downsample 1/4/8의 3-stage 피라미드
- 현재 stage 타일이 오기 전 썸네일 또는 인접 stage fallback
- 새 타일 fade-in과 현재 뷰포트 밖 요청 취소
- 슬라이드 바깥은 흰색으로 표시
- 줌 범위 0.001~40
- OpenSlide 레벨, 배율, MPP, 스캐너 vendor 표시
- Hamamatsu 슬라이드에 NDP.view2 색보정 토글과 별도 보정 타일 캐시
- Philips iSyntax/i2syntax는 별도 SDK 브리지 사용

### 9.2 탐색·보조 UI

- Fit, Zoom In, Zoom Out
- 좌클릭 또는 가운데 버튼 드래그 팬
- 마우스 휠 줌은 **커서가 아니라 뷰포트 중앙 기준**
- 터치 한 손가락 팬, 두 손가락 pinch zoom
- 미니맵 클릭·드래그로 이동
- 미니맵 크기 조절·접기
- 좌우 패널 크기 조절·접기, 폭을 localStorage에 보존
- 모바일에서는 좌우 패널을 drawer로 표시
- 좌표 오버레이 기능은 구현되어 있으나 기본은 숨김

### 9.3 슬라이드 정보와 임상정보

- 파일명, vendor, 배율, 픽셀 크기, MPP, 실제 물리 크기 표시
- 다음 임상정보 편집:
  - ER proportion score
  - ER intensity score
  - PR proportion score
  - PR intensity score
  - Ki67 index
  - PD-L1 CPS score
  - ISH for HER2 (FISH/SISH)
  - IHC for C-erbB2
- 다이얼로그를 닫거나 Esc를 누를 때 변경이 있으면 자동 저장
- 파일명에서 케이스 ID를 추출해 같은 케이스의 슬라이드들과 임상정보를 공유

### 9.4 Same Case 및 Multi View

- CODIPAI 파일명은 `CODIPAI-` 다음 3개 구간으로 케이스 ID를 구성
- 일반 파일명은 첫 3개 하이픈 구간을 케이스 ID로 사용
- 모든 프로젝트·marker 폴더를 검색해 같은 케이스 슬라이드 표시
- 현재 슬라이드와 AI 결과 보유 여부 배지
- 최대 4개 선택
- 1개는 단일 View, 2~4개는 Multi View
- 각 pane별 Fit, 클릭으로 활성 pane 선택
- 활성 pane에서 AI, Annotation, Info 동작
- Multi View 종료 시 원래 슬라이드·폴더·뷰 상태 복원

## 10. AI 워크스페이스

### 10.1 툴바·ROI

- Slide Info, Same Case, Fit, Zoom In/Out
- Polygon ROI, Polygon Brush, Rectangle ROI
- MPP 기반 고정 면적 1 mm² Rectangle/Circle
- Ruler
- 단축키 도움말과 미리보기 영상 UI
- AI 화면에는 Point와 Cut 도구가 없음
- ROI가 하나 이상 있으면 보이는 비-Point 주석 영역만 분석에 전달; 없으면 전체 슬라이드 분석

### 10.2 AI 메뉴

- 상위 주제: VirtualStain, Quanti, Dx, Px
- Dx와 Px는 현재 실질 동작이 없는 placeholder
- Quanti 하위: HE, PD-L1, IHC
- 실행 중인 버튼을 다시 누르면 취소 요청 가능
- 비동기 task 상태·진행률·취소·결과 다운로드
- 큰 결과 JSON은 완료 후 별도 스트리밍 응답으로 한 번 받아오며 수신 진행률 표시
- 결과 전달 후 서버 task 메모리를 해제
- 전체 슬라이드 결과는 캐시 재사용; ROI 분석은 일반적으로 원본 전체 캐시와 분리

### 10.3 Quanti HE

모드:

- Breast
- Stomach
- Other

기본 세포 클래스:

- Neutrophil
- Epithelial
- Lymphocyte
- Plasma
- Eosinophil
- Stromal cell
- Breast/Stomach에서는 Tumor Epithelial, Benign Epithelial 재분류 추가

동작:

- 조직 마스크로 유리 배경 패치를 건너뜀
- 1024px 패치, 겹침·경계 보정·전역 중복 제거
- Breast/Stomach는 별도 segmentation 결과로 epithelial을 Tumor/Benign으로 재분류
- UI에서는 Stromal cell을 기본 숨김
- 5만 개를 넘는 가시 셀은 raster 경로로 렌더링해 Canvas 부담을 줄임

### 10.4 Quanti PD-L1

Stomach CPS:

`min(100, (Positive Epithelial + Positive Lymphocyte + Positive Macrophage) / (Negative Epithelial + Positive Epithelial) × 100)`

- 7개 클래스: 음성/양성 Epithelial, Lymphocyte, Macrophage 및 Other
- Other는 숨김·점수 제외

Lung TPS:

`PD-L1 Positive Tumor / (PD-L1 Positive Tumor + PD-L1 Negative Tumor) × 100`

- 3개 클래스: Negative Tumor, Positive Tumor, Non-Tumor
- Non-Tumor는 숨김·점수 제외

점수 산출 시 confidence 기준은 0.1로 고정되어 있고 현재 UI에서 사용자가 변경할 수 없다.

### 10.5 Quanti IHC

HER2:

- HER2 0+, 1+, 2+, 3+, Other
- 0~3 가중 평균과 최다 클래스(dominant class) 표시
- Other 제외
- 결과 표시 confidence 기본 0.5

ER/PR Allred:

- 0+, 1+, 2+, 3+, Other
- Proportion Score: 0%, <1%, <10%, <33%, <66%, 그 이상을 0~5로 계산
- Intensity Score: 양성 셀 평균 강도를 0~3으로 구간화
- Total Score = PS + IS, 3 이상 Positive
- 결과 표시 confidence 기본 0.3

KI-67:

- Negative, Positive 1+/2+/3+, Other
- Labeling Index = Positive / Total × 100
- 14% 이상 High, 미만 Low
- 결과 표시 confidence 기본 0.3

### 10.6 VS IHC

- 현재 실제 방향은 **IHC 원본 → Virtual H&E**
- 모델 선택: `ihc_membrane`
- Target Resolution: 4.0, 2.0, 1.0, 0.5 µm/px
- 원본 위 Overlay 켜기/끄기
- IHC | Virtual H&E Split View
- split divider는 5~95% 범위에서 드래그
- ROI가 있으면 ROI에 clip
- Cell Annotation Patch View에서는 선택 패치 경계 안에만 clip
- 큰 슬라이드는 타일 스트리밍·bounded prefetch로 처리

### 10.7 AI 결과 셀 편집

- 클래스별 count, 색상, 표시/숨김
- 전체 클래스 표시/숨김
- 검출 셀 선택·재분류·삭제·추가
- 숨겨진 Other 셀을 lasso로 골라 가시 클래스로 승격
- 편집 즉시 CPS/TPS/HER2/Allred/KI-67 재계산
- undo/redo 최대 200단계
- 클래스 이름의 화면 세션 내 표시 변경 기능
- 결과 Clear는 현재 화면을 비우며 원본 서버 캐시를 삭제하지 않음
- Save는 현재 사용자의 편집본을 별도로 저장
- Load는 원본 AI 결과와 다른 사용자의 저장본 목록을 보여줌
- 본인 저장본만 삭제 가능
- Labeler와 Viewer는 결과 편집·Save/Load가 제한됨

### 10.8 시각화와 PDF

- 클래스 분포 bar·pie
- 모델별 종양 분석 또는 CPS/TPS/HER2/Allred/KI-67 분석
- 공간 heatmap 및 segmentation map
- confidence histogram
- AI 화면에 별도 heatmap on/off 버튼
- A4 landscape 다중 페이지 PDF
- File System Access API 지원 브라우저는 저장 위치 선택, 그 외 자동 다운로드
- **주의:** PDF 생성 시 jsPDF를 jsDelivr CDN에서 동적 import하므로 완전 폐쇄망에서는 PDF 내보내기가 실패할 수 있음

## 11. Tissue Annotation

### 11.1 도구

- Polygon: 드래그 궤적을 polygon으로 생성
- Polygon Brush: 브러시 폭을 가진 freeform polygon
- Rectangle
- Point
- Cut: 선택 polygon의 경계를 새 경로로 재구성
- 고정 1 mm² Rectangle/Circle
- Ruler: MPP 기반 거리 표시, 수평·수직 ±2° 자동 스냅
- Slide Memo

### 11.2 주석 편집

- 주석 선택, 삭제, 전체 지우기
- polygon vertex 또는 rectangle corner 드래그 편집
- Shift+드래그로 전체 주석 이동
- Alt+polygon edge 클릭으로 vertex 삽입
- 겹친 같은 클래스 polygon은 Ctrl+클릭으로 병합
- 주석 목록에서 표시/숨김, 클래스, 메모, 삭제
- 목록 ID 더블클릭으로 해당 주석 중앙 이동
- 프로젝트별 클래스 추가·삭제·이름·색상·순서 변경
- 클래스를 선택된 주석에 즉시 적용
- 클래스 표시/숨김
- 공통 선 두께 1~12px, fill 0~80%; 사용자 preference로 보존
- 클래스 관리는 Admin/Doctor만 가능

### 11.3 저장·메모·상태

- 슬라이드 열 때 서버 저장 주석 자동 로드
- Save 버튼 또는 Ctrl/Cmd+S로 전체 주석과 slide memo를 내부 JSON에 저장
- 슬라이드 메모와 각 주석 메모
- 메모 history, 답변, accept, 현재·과거 메모 삭제
- 메모가 있는 슬라이드는 목록에 M 배지
- Annotation → Review → Termination 워크플로
- 상태 버튼은 현재 단계를 Running/Done으로 순환시키고 다음 단계로 진행
- 완료, 실행 중, 현재, 대기, 반려 상태를 색·아이콘으로 구분
- Tissue Annotation 오른쪽 AI 패널은 CSS상 VS IHC만 노출
- **레거시:** JSON 파일 download/upload 함수는 남아 있으나 현재 화면 버튼에는 연결되지 않고 서버 내부 저장만 노출됨

## 12. Cell Annotation

### 12.1 좌표와 패치 규격

- 기준 해상도 0.5 µm/px
- 패치 실제 크기 512 µm × 512 µm
- 표준 패치 이미지 1024 × 1024px
- 좌표 기반 `patch_key`와 사람이 보는 순번형 `patch_N` ID를 함께 사용

### 12.2 WSI 단계

- Admin/Doctor가 Required 또는 Exclude polygon 영역을 그림
- Required는 초록, Exclude는 빨강
- 적용 전 pending 영역을 겹쳐 미리보기
- Apply는 기존 결과에 증분 반영:
  - Required와 교차하는 패치를 추가
  - Exclude와 교차하는 저장 패치를 제외
  - 적용한 pending 영역은 비움
- Ctrl/Cmd+Z로 아직 적용하지 않은 required/exclude 영역 실행 취소
- 전체 패치 삭제는 Admin/Doctor만 가능하고 5초 countdown 후 실행
- 전체 삭제 시 패치 상태, 셀 라벨, 이미지·sidecar까지 제거

### 12.3 패치 목록과 보기 전환

- Patch, Annotation, Review, Termination, Memo 열
- 각 열 정렬
- 대량 패치 목록은 렌더 개수를 제한
- Required, Running, Done, Rejected 등 상태 색상 overlay
- WSI 수준 상태는 패치별 상태의 완료율로 자동 계산
- 패치 클릭 선택, 더블클릭 또는 행 action으로 Patch View 진입
- `P`로 WSI View와 Patch View 전환하고 이전 WSI viewport 복원
- Patch View는 선택 패치 경계로 화면을 제한하고 Fit Patch 제공
- VS overlay/split도 선택 패치 안에만 표시

### 12.4 Cell 라벨링

- Patch View에서는 rectangle이 cell bounding box 도구
- 표시 방식은 BBox 또는 Point로 바꿀 수 있으나 저장 데이터는 bbox 유지
- 셀 클래스 목록, display 설정, cell annotation 목록, patch 목록을 각각 접거나 크기 조절
- 체크박스 및 Alt 선택으로 여러 셀 선택
- 선택 셀 일괄 클래스 변경·삭제
- 클래스 행을 클릭하면 현재 선택 셀에 즉시 적용
- Annotation 상태가 Running인 패치만 draft Save 가능
- Annotation을 Done으로 바꾸면 먼저 자동 저장
- Labeler는 Running 또는 Review Rejected 패치에서만 라벨 편집 가능

### 12.5 Patch Workflow

- Annotation: Required → Running → Done
- Review: Pending → Done → Rejected → Pending 순환
- Termination: Pending → Current → Done 순환
- Review Rejected는 다시 Annotation 편집을 허용
- WSI 목록과 상단 상태는 패치들의 완료율·반려 수를 요약
- Labeler는 Annotation 단계만 변경 가능
- 패치별 memo와 history, answer, accept, delete
- Labeler는 memo, Review, Termination을 변경할 수 없음

### 12.6 AI labeling assistance

- 프로젝트에서 assistance를 켜고 한 모델을 선택
- 필요한 WSI 패치 전체를 대상으로 AI 실행 및 진행률 표시
- 빈 Required 패치를 열 때 assistance label을 자동 로드
- 이미 수동 라벨이 있는 패치에는 자동 덮어쓰지 않음
- Inherited 모델은 모델 클래스를 프로젝트 기본 클래스로 상속
- Non-inherited 모델은 모델 결과를 프로젝트 Other 등에 매핑
- AI/필수 클래스와 Other는 이름·색상·삭제가 잠기지만 순서 변경은 가능
- 사용자 custom 클래스는 유지
- 후처리 버전이 바뀐 오래된 assistance cache는 무효화

### 12.7 내보내기 sidecar

슬라이드별로 다음 파일이 생성된다.

- `patches/*.jpeg`
- `labels/*.json`
- `info.json`
- `WSI_Labeling_assistance.json`

변경 사항은 coalesced background export로 디스크에 반영된다. 종결 완료 패치 ZIP은 특정 계정에만 노출되는 조건부 기능이다.

## 13. Data Linkage

- Project, Hospital, Sample No 필터
- Sample No 입력에서 Enter로 검색
- 15/30/50행 페이지 크기
- Case ID, Clinical Info 보유 여부, Last Activity 정렬
- 서버 페이지네이션과 클라이언트 fallback, 페이지 번호·ellipsis
- 케이스 선택 시 연도, Sample ID, 연결된 슬라이드 썸네일 표시
- 썸네일 선택 시 큰 preview
- preview 드래그 팬, 휠 cursor 중심 zoom, +/- zoom, reset/fit
- 케이스 공유 임상정보 편집·저장
- 저장하지 않은 변경이 있을 때 페이지 이탈 경고
- 임상 필드는 WSI Info와 같지만 ISH 선택지에 `not tested`가 포함되고 `equivocal`은 없음

## 14. Admin

### 14.1 Pending

- 승인 대기 사용자 목록
- 승인 시 Viewer, Labeler, Doctor, Admin 역할 지정
- 거절 시 선택적 사유 입력

### 14.2 Users

- 20명 단위 페이지네이션
- 승인 상태 필터 및 검색 debounce
- 이름·부서·선택적 비밀번호 변경
- 역할 변경
- 활성/비활성 전환
- 잠긴 계정 해제
- 사용자 삭제
- 본인 비활성·삭제 및 마지막 Admin 제거를 서버에서 방지

### 14.3 Create User

- 관리자가 즉시 승인된 사용자 생성
- Viewer, Labeler, Doctor, Admin 지정

### 14.4 Activity

- 로그인 활동 50건 단위 조회
- 사용자, 날짜, IP, 국가·지역·도시, 장치 표시
- 사용자 상세 활동 100건 단위 조회
- All, Login, Slides, AI, Projects, Files 카테고리와 건수 배지
- 날짜 범위와 페이지 이동
- IP 위치정보 TTL 캐시

### 14.5 Settings

- AI Worker enabled/running 상태
- Tile Worker enabled/running 상태
- 토글 변경 즉시 영속 설정 저장 및 워커 시작·중지
- **API:** 감사 로그 HMAC chain 검증은 구현됐지만 현재 Admin UI에 버튼이 없음

## 15. 전체 단축키·마우스 조작

macOS에서는 대부분의 `Ctrl` 조합을 `Cmd`로 사용할 수 있다.

### 15.1 공통 뷰어

| 입력 | 동작 | 적용/주의 |
| --- | --- | --- |
| 좌클릭 드래그 | 슬라이드 팬 | 도구·주석 hit와 충돌하지 않을 때 |
| 가운데 버튼 드래그 | 슬라이드 팬 | 공통 |
| 휠 | 줌 인/아웃 | AI/Tissue/Cell WSI는 viewport 중앙 기준 |
| 한 손가락 드래그 | 팬 | 터치 |
| 두 손가락 pinch | 줌 | 터치 |
| Esc | 현재 그리기, Alt lasso, 팝업·모바일 drawer 취소/닫기 | 상황별 |
| 우클릭 | 그리기 모드 해제 | 주석 위에서는 memo context 동작 가능 |
| Delete | 선택 주석 삭제 | 편집 권한 필요 |
| 더블클릭 | 선택 주석 중앙 이동 | canvas 또는 목록 ID |
| Ctrl+드래그 | 주석 위나 draw mode에서도 화면 팬 | 공통 |
| Ctrl+클릭 | draw mode 중에도 주석 선택 | 공통 |
| Shift+드래그 | 선택 주석 전체 이동 | 공통 |
| Alt+휠 | Polygon Brush 크기 변경 | Brush mode |
| Alt+polygon edge hover | vertex 삽입 위치 preview | Cell Patch View 제외 |
| Alt+polygon edge 클릭 | vertex 삽입 | Cell Patch View 제외 |
| Ctrl+겹친 polygon hover | merge 아이콘 표시 | 같은 클래스만, Cell Patch View 제외 |
| Ctrl+겹친 polygon 클릭 | 두 polygon 병합 | 같은 클래스만, Cell Patch View 제외 |
| Ctrl+Z | 주석 또는 AI 셀 편집 undo | Cell WSI에서는 pending region 우선 |
| Ctrl+Shift+Z | redo | 공통 편집 |
| Ctrl+Y | redo | 공통 편집 |
| Ctrl+휠 | 슬라이드 목록 썸네일 크기 변경 | 왼쪽 목록 위 |

### 15.2 Tissue/Cell Annotation

| 입력 | 동작 |
| --- | --- |
| Ctrl+S | 현재 슬라이드 주석 또는 선택 패치 셀 저장 |
| Ctrl+M | Slide Memo 열기 |
| 1~9, 0 | 선택 주석/셀을 클래스 1~10으로 지정 |
| Delete | 선택 주석 삭제 |
| Delete / Backspace / D | Cell Patch View에서 선택 셀 삭제 |
| Annotation 목록 우클릭 | 해당 주석 memo 열기 |
| Annotation 목록 ID 더블클릭 | 해당 주석 중앙 이동 |
| Patch 행 Enter / Space | 패치 선택 |
| Patch 행 더블클릭 | Patch View 진입 |
| Patch 행 우클릭 | memo 또는 required 제거 메뉴 |
| P | WSI View ↔ Patch View 전환 |
| Ctrl+1~9/0 | Patch View 클래스 1~10 표시/숨김 |
| Ctrl+` | Patch View 모든 클래스 표시/숨김 |
| Esc | Patch View 다중 셀 선택 해제 포함 |

### 15.3 AI 결과 셀 편집

| 입력 | 동작 |
| --- | --- |
| Alt+좌클릭 | 가장 가까운 가시 셀 편집 |
| Alt+좌드래그 | 가시 셀 lasso 다중 선택 |
| Alt+우클릭 | 해당 위치에 새 셀 추가 |
| Alt+우드래그 | 숨겨진 Other 셀을 lasso 선택해 가시 클래스로 승격 |
| Alt 누름 | crosshair 및 현재 sticky class HUD 표시 |
| Alt+A | sticky class picker 열기 |
| 1~9, 0 | 열린 편집 popup에서 클래스 1~10 선택 |
| Delete / D | 선택한 AI 결과 셀 삭제 |
| Esc | 편집 popup 또는 선택 취소 |

### 15.4 목록·대화상자

| 입력 | 동작 |
| --- | --- |
| Ctrl/Cmd+슬라이드 클릭 | 선택 토글 |
| Shift+슬라이드 클릭 | 마지막 선택부터 범위 선택 |
| 빈 영역 드래그 | marquee 다중 선택 |
| Same Case 카드 더블클릭 | 열기 선택 대화상자 |
| Same Case 카드 focus 후 Enter | 열기 선택 대화상자 |
| 좌우 panel resizer Enter/Space | 접힌 패널 다시 열기 |
| Data Linkage Sample No Enter | 검색 실행 |

**문서 불일치:** Tissue/Cell 화면의 shortcut 도움말은 휠 줌을 “커서 기준”이라고 설명하지만, 실제 공통 TileViewer 코드는 viewport 중앙을 유지한다. Data Linkage preview만 실제 cursor 중심 zoom이다.

## 16. 자동화·성능·백그라운드 기능

### 16.1 자동 AI

- 폴더 또는 프로젝트에 지정된 AI task를 60초마다 검색
- 앱 시작 5초 뒤 첫 scan
- 사용자 AI/뷰어 활동이 10분 동안 없을 때 자동 실행
- 업로드 중에는 실행하지 않음
- 누락되었거나 현재 후처리 메타데이터와 다른 cache를 찾아 복구 가능
- viewer가 최근 활동하면 AI patch loading이 양보
- Admin Settings에서 worker를 즉시 켜고 끌 수 있음

### 16.2 타일 워커·캐시

- 업로드 후 background tile validation·generation
- 20초 scan, 15회마다 janitor 실행, 즉 약 5분 주기
- viewer가 최근 60초 이내 활동하면 낮은 병렬도, idle이면 높은 병렬도
- 기본 타일 디스크 quota 1 TB
- quota 초과 시 active slide를 제외하고 `.complete` mtime 기반 LRU eviction
- 기본 열린 slide handle 최대 4개, 300초 idle 시 close
- thread-local OpenSlide LRU와 generation counter로 stale handle 방지

### 16.3 AI 계산 최적화

- 조직 마스크로 배경 패치 제거
- 병렬 OpenSlide I/O와 GPU batch inference
- CUDA AMP
- 패치 간 겹침 및 내부 경계 결과 제거
- class-wise·spatial NMS, 가시 클래스 우선 중복 제거
- 결과 cache 후처리 메타데이터가 달라지면 stale 판정
- VS는 bounded prefetch와 타일 결과로 전체 이미지 메모리 폭증 방지
- Linux에서는 Web/Viewer/Tile/AI/Patch/Upload executor CPU affinity 분리

## 17. 데이터 저장 구조

### 17.1 파일 저장소

| 경로 | 목적 |
| --- | --- |
| `backend/uploads` | 원본 WSI와 프로젝트·폴더 구조 |
| `backend/tiles` | JPEG stage 타일과 NDP 보정 타일 |
| `backend/ai_results` | AI 원본 결과 cache 및 사용자 편집본 sidecar |
| `backend/annotations` | Tissue Annotation 및 프로젝트 클래스 JSON |
| `backend/cell_annotation` | 패치 이미지·라벨·assistance·manifest |
| `backend/model` | AI `.pt`, `.pth` weights |

환경변수로 Upload/Tiles/AI Results/Annotations 경로 일부를 재지정할 수 있다.

### 17.2 PostgreSQL 저장 구조

| 테이블/논리 문서 | 목적 |
| --- | --- |
| `users` | 계정, 역할, 승인, 잠금, MFA, preference |
| `sessions` | Refresh Token 세션과 만료 시각 |
| `audit_logs` | 행위·보안 이벤트와 HMAC chain |
| `ip_geo_cache` | IP 위치 TTL cache |
| `slides` | 슬라이드 경로·메타·checksum·상태·AI flag |
| `folder_ai_configs` | 폴더 자동 AI 설정 |
| `project_infos` | 프로젝트 정보와 프로젝트·Cell AI 설정 |
| `case_clinical_info` | 케이스 공유 임상정보 |
| `annotation_required_regions` | Cell required/exclude 영역 |
| `patch_annotation_status` | 패치별 workflow·memo 상태 |
| `patch_cell_annotations` | 패치별 cell label |
| `user_ai_edits` | 사용자별 AI 편집본 metadata |
| `app_settings` | AI/Tile worker runtime 설정 |

`slides`부터 `app_settings`까지의 유연한 문서는 `application_documents` JSONB
테이블에 논리 collection 이름으로 구분해 저장한다.

## 18. API 기능군

모든 세부 경로를 나열하기보다 기능 단위로 묶으면 다음과 같다.

- Auth: register, login, refresh, logout, me, password, media ticket, MFA
- Users/Admin: pending/list/create/approve/reject/update/delete/role/active/unlock, audit/activity, worker settings
- Projects/Folders: tree, projects, create/update/rename/move/delete, folder CRUD
- Slides: dashboard, browse, cases, open, chunk upload, local open, info, clinical info, integrity, list/delete
- Files: delete, status, move
- Media/Tiles: thumbnail, preview, standard/NDP tile, stage level
- Tissue Annotation: project classes, save/load
- Cell Annotation: classes, grid, regions, patches, workflow, cells, assistance, termination export
- AI: Quanti HE, PD-L1, IHC, VS, task status/cancel/result, VS media tiles
- User AI edits: save, list, load, delete

FastAPI의 `/docs`가 배포 설정에서 차단되지 않았다면 자동 OpenAPI 문서로 개별 요청 스키마를 확인할 수 있다.

## 19. 운영 스크립트

- Windows/Linux 설치 스크립트
- Windows/Linux 시작 스크립트
- AI 결과 JSON compact 변환
- AI 결과 cache 초기화
- AI와 Cell assistance cache 정리; dry-run 우선 및 `--quanti-only` 옵션
- Hamamatsu 색보정 cache 초기화
- 동시 사용자 부하 테스트

## 20. 현재 코드에서 확인된 문서·구현 차이

| 항목 | 현재 코드 | 기존 문서 일부 |
| --- | --- | --- |
| 역할 | Admin/Doctor/Labeler/Viewer 4개 | Labeler가 빠진 3개 역할 표가 있음 |
| VS IHC 방향 | IHC → Virtual H&E | H&E → IHC로 기술된 곳이 있음 |
| Access Token | 기본 360분 | 15분이라고 적힌 곳이 있음 |
| DB 컬렉션 | 최소 13개 명시 사용 | 7개라고 적힌 문서가 있음 |
| 화면 | Project, Data Linkage, Cell Annotation 포함 | 예전 USER_GUIDE에 누락 |
| 줌 기준 | 공통 WSI는 viewport 중앙 | Tissue/Cell 도움말은 cursor 기준이라 표기 |
| Annotation AI | Tissue 화면에는 VS만 CSS 노출 | HTML에는 다른 Quanti 탭 markup도 남아 있음 |
| MFA | 로그인 대응과 API 존재 | 사용자 설정 UI는 없음 |

## 21. 위험·개선 필요 사항

우선순위가 높은 순서로 정리하면 다음과 같다.

1. **DB 장애 시 인증 우회**  
   PostgreSQL 미연결 시 `get_current_user`와 미디어 인증이 anonymous admin을 반환하는 개발 fallback이 남아 있다. 운영에서는 DB 장애가 권한 우회로 이어지지 않도록 fail-closed 전환이 필요하다.

2. **서버 측 역할 검사 누락**  
   UI에서 숨긴 일부 폴더·파일·업로드·임상정보 변경 기능이 API에서는 로그인만 검사한다. UI 권한은 보안 경계가 아니므로 endpoint별 RBAC를 통일해야 한다.

3. **폐쇄망 PDF 의존성**  
   jsPDF가 외부 CDN 동적 import다. 온프레미스·망분리 환경을 위해 로컬 asset으로 고정해야 한다.

4. **사용자에게 보이는 placeholder/문자 깨짐**  
   `app.html`, `annotation.html`, CSS 일부에 `text text` 형태의 손상된 aria-label, loading 문구, drop-zone 문구, UX 도움말이 남아 있다. 기능 자체는 동작하지만 접근성·완성도에 직접 영향을 준다.

5. **문서 최신화 필요**  
   README, USER_GUIDE, FEATURES의 역할·토큰·DB·VS 방향이 현재 코드와 다르다. 이 문서를 기준으로 기존 문서들을 재작성해야 한다.

6. **UI가 없는 보안·운영 기능**  
   MFA 설정/해제, 파일 무결성 확인, audit chain 검증은 API만 있다. 운영자가 실제로 사용할 관리 UI가 필요하다.

7. **레거시·중복 화면 코드**  
   Home/Project가 거의 중복이고, Tissue Annotation의 숨겨진 AI markup과 연결되지 않은 JSON import/export 코드가 남아 있다. 유지보수 시 현재 노출 기능과 혼동될 수 있다.

8. **정적 자산 캐시 키 관리**
   제품 버전은 `version.json`의 2.0.0을 기준으로 한다. 프론트의 날짜형 asset query는 개별 캐시 무효화 키이므로 제품 버전과 별도로 관리된다.

9. **인메모리 rate limit**  
   단일 프로세스에서는 유효하지만 multi-worker/multi-instance에서는 카운터가 공유되지 않는다.

10. **CORS/TLS 운영 설정**
    CORS와 원격 PostgreSQL TLS는 배포 환경에서 명시해야 한다. 실제 병원 배포에서는 전용 DB 계정, PostgreSQL TLS, reverse proxy TLS와 보안 헤더가 필수다.

## 22. 검증 결과

이번 분석에서는 다음을 확인했다.

- 모든 `frontend/js/*.js`를 ES module 입력으로 구문 검사: 통과
- `backend` 전체 Python `compileall`: 통과
- FastAPI 라우트와 프론트 API 호출을 기능군별 교차 확인
- HTML 단축키 도움말과 실제 `keydown`/mouse handler 교차 확인
- 역할별 프론트 제한과 백엔드 dependency 교차 확인
- 현재 작업 트리는 분석 시작 시 clean 상태

실제 OpenSlide, Philips SDK, GPU 모델을 모두 사용한 end-to-end 실행 검증은 이번 정적 분석 범위에는 포함하지 않았다. 특히 업로드·AI 결과 정확도·Philips bridge·동시 사용자 성능은 배포 환경에서 별도 시나리오 테스트가 필요하다.

## 23. 다음 문서화 작업 권장 순서

1. 이 문서를 기준으로 역할별 사용자 매뉴얼을 분리
2. 화면 캡처를 추가한 Admin/Doctor/Labeler/Viewer 퀵 가이드 작성
3. 단축키 표를 앱 도움말과 단일 source로 통합
4. API-only 기능에 관리 UI를 붙일지 결정
5. 권한 누락과 DB fail-open을 먼저 수정
6. README, USER_GUIDE, FEATURES, DATABASE를 현재 코드에 맞춰 갱신
7. 실제 환경에서 E2E 회귀 테스트 체크리스트 작성
