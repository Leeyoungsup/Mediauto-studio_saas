# MeDIAuto Studio SaaS

병원 온프레미스(On-Premise) 배포용 디지털 병리 WSI(Whole Slide Image) 뷰어 + AI 분석 플랫폼.

PyQt5 기반 데스크톱 앱(MeDICus Studio)의 코어 로직을 FastAPI 백엔드 + Vanilla JS 프론트엔드로 포팅한 웹 버전. 단일 프로세스에서 멀티 사용자, 멀티 AI 모델, 대용량 WSI(최대 20 GB)를 다루기 위해 CPU 파티셔닝·뷰어 우선순위 게이팅·idle-aware 자동 추론·HMAC 체인 감사 로그까지 담고 있다.

## 주요 기능

| 기능 | 설명 |
|------|------|
| WSI 뷰어 | OpenSlide 기반 3-stage 타일 피라미드 (downsample 1/4/8). 1024 px JPEG 타일을 `<img src>` 로 서빙. SVS/NDPI/TIFF/VMS/VMU/SCN/MRXS 지원 |
| Annotation | Canvas 기반 polygon-lasso / rectangle / point. 슬라이드별 JSON 업서트, viewer 역할은 저장 불가 |
| HE-Fit | H&E 슬라이드 세포 검출 (YOLOv11-M, 8 class). Stomach·Breast 는 Tumor/Benign epithelial 재분류 |
| PD-Score | PD-L1 IHC scoring — Stomach CPS / Lung TPS 자동 계산 |
| Precise-IHC | HER2 / ER·PR Allred / Ki-67 Labeling Index — 염색 강도 0+~3+ 분류 |
| VS-IHC | Virtual Staining (H&E → IHC membrane/nucleus). 타일 스트리머로 큰 SVS 도 ~100 MB 메모리 |
| 폴더 자동 AI | `folder_ai_configs` 기반, 60초 주기로 미완 (model, variant) 자동 추론. idle 600초·업로드·뷰어 활동 시 양보 |
| 사용자 편집본 | 셀 수정·저장본을 사용자별로 분리 저장 (`user_ai_edits`). 원본 추론 캐시는 보존 |
| 인증·인가 | MongoDB + JWT (Access 15분 + Refresh 7일). RBAC 3단계 + 가입 승인 워크플로 + 5회 실패 30분 잠금 |
| 2차 인증 (MFA) | RFC 6238 TOTP 자체 구현. AES-256-GCM 으로 시드 암호화 저장 |
| 미디어 URL 서명 | `<img src>` 타일·썸네일에 단기(10분) HMAC 티켓 (`?mt=`) — JWT URL 노출 제거 |
| 감사 로그 | 로그인·슬라이드 뷰·AI 분석·관리자 작업을 HMAC 체인으로 기록. IP geo enrichment + before/after 변경 추적 |
| 파일 무결성 | 업로드 시 스트리밍 SHA-256 계산, `verify-integrity` API 로 재계산·비교 |

## 기술 스택

- **Backend**: Python 3.12, FastAPI, Uvicorn (ASGI)
- **Frontend**: Vanilla JS (ES Modules), HTML5 Canvas — 빌드 도구 없음
- **Database**: MongoDB 7.x+ (motor async driver). DB 미연결 시 일부 기능만 비활성화되고 뷰어는 동작
- **인증**: JWT HS256 + bcrypt(cost=12) + pepper, RFC 6238 TOTP, AES-256-GCM, HMAC-SHA256 미디어 티켓
- **슬라이드**: OpenSlide, Pillow, ICC profile 지원, Hamamatsu NDP.view2 색 매칭
- **AI**: PyTorch (CUDA AMP), YOLOv11-M (HE-Fit / PD-Score / Precise-IHC), pix2pix U-Net (VS-IHC)

## 프로젝트 구조

```text
├── backend/
│   ├── main.py                    # FastAPI 진입점 (Uvicorn, port 8091)
│   ├── requirements.txt           # Python 의존성
│   ├── .secrets.json              # 0600, JWT/암호화/pepper 영속화 (gitignore)
│   ├── app/
│   │   ├── config.py              # 시크릿 로딩, 디렉토리, JWT, 업로드 한계
│   │   ├── database.py            # MongoDB 연결 + 인덱스/마이그레이션
│   │   ├── models.py              # User 모델, bcrypt + pepper, UserRole / ApprovalStatus
│   │   ├── auth.py                # JWT 생성/검증, get_current_user, RBAC, 30s 캐시
│   │   ├── totp.py                # RFC 6238 TOTP MFA (의존성 0)
│   │   ├── audit.py               # HMAC 체인 감사 로그
│   │   ├── geo.py                 # IP → 국가/도시 geolocation 캐시 (TTL 30일)
│   │   ├── encryption.py          # AES-256-GCM 필드 암호화 (TOTP 시드)
│   │   ├── url_signer.py          # 단기 HMAC 미디어 티켓
│   │   ├── csrf.py                # Pure ASGI CSRF 미들웨어 (X-Requested-With)
│   │   ├── rate_limit.py          # Pure ASGI Rate Limiting (고정 윈도우)
│   │   ├── cpu_layout.py          # viewer/bg/ai 코어 파티셔닝 (Linux affinity)
│   │   ├── slide_manager.py       # OpenSlide 핸들 캐시 + generation counter
│   │   ├── slide_store.py         # slides/user_ai_edits 컬렉션 helper + 대시보드 집계
│   │   ├── tile_generator.py      # 3-stage 타일 프리젠 (69 tile / 1 read)
│   │   ├── tile_worker.py         # 백그라운드 타일 워커 + startup 마커 검증
│   │   ├── tile_janitor.py        # LRU 디스크 쿼터 eviction
│   │   ├── thread_slide_pool.py   # thread-local OpenSlide 핸들 풀 (LRU + stale 감지)
│   │   ├── auto_ai.py             # 폴더별 AI 자동 추론 워커 (idle-aware)
│   │   ├── priority.py            # 뷰어 활동 → AI 양보 게이팅
│   │   ├── ndp_color_match.py     # Hamamatsu NDP.view2 톤 매칭 LUT
│   │   ├── svs_to_hamamatsu.py    # SVS → Hamamatsu 색공간 역변환 (VS-IHC 입력)
│   │   ├── ai_pipelines/
│   │   │   ├── detection.py       # HE-Fit 워커 (조직마스크, 멀티스레드 I/O, 배치 GPU)
│   │   │   ├── marker_pipeline.py # PD-Score / Precise-IHC 공용 파이프라인
│   │   │   ├── virtual_stain.py   # VS-IHC + VSTileStreamer (메모리 상한)
│   │   │   ├── scoring.py         # CPS / TPS / HER2 / Allred / Ki-67 수식
│   │   │   ├── tissue_mask.py     # H-DAB color deconvolution + Otsu
│   │   │   ├── cache_paths.py     # ai_results/ 경로 헬퍼
│   │   │   └── task_state.py      # task dict + cancel 협의
│   │   └── routers/
│   │       ├── auth.py            # 회원가입/로그인/refresh/logout/MFA/media-ticket
│   │       ├── users.py           # 관리자 사용자/역할/잠금/감사 로그/체인 검증
│   │       ├── slides.py          # 슬라이드 업로드/열기/이동/삭제/annotation/folder-config
│   │       ├── tiles.py           # 타일·NDP 변형 타일 서빙
│   │       ├── ai.py              # AI 4종 트리거 + task 상태/취소
│   │       └── ai_user_edits.py   # 사용자별 셀 편집본 저장/조회/삭제
│   ├── uploads/                   # WSI 원본 (UPLOAD_DIR)
│   ├── tiles/                     # 프리생성 JPEG 타일 + ndpmatch 변형 (TILES_DIR)
│   ├── ai_results/                # AI 결과 캐시 + user_edits/ (AI_RESULTS_DIR)
│   └── model/                     # PyTorch 가중치 (.pt / .pth)
├── frontend/
│   ├── index.html                 # 토큰 확인 → 리다이렉트
│   ├── login.html                 # 로그인 / 회원가입 / MFA
│   ├── home.html                  # 대시보드
│   ├── upload.html                # 청크 업로드 다이얼로그
│   ├── app.html                   # 메인 뷰어
│   ├── admin.html                 # 관리자 페이지 (승인/사용자/활동 로그)
│   ├── css/
│   │   ├── style.css              # 메인 + 반응형 (≤900px drawer)
│   │   ├── home.css               # 대시보드 전용
│   │   └── admin.css              # 관리자 전용
│   └── js/
│       ├── api.js                 # REST 클라이언트 + JWT 자동 관리 + 미디어 티켓
│       ├── home.js                # 대시보드 로직
│       ├── app.js                 # 메인 앱 (뷰어 + AI + annotation + UX)
│       ├── tile-viewer.js         # Canvas 타일 렌더러 (3-stage, fallback, fade-in)
│       ├── visualization.js       # AI 결과 다이얼로그 (4탭) + PDF export
│       ├── color-correction.js    # NDP 색보정 토글
│       └── admin.js               # 관리자 페이지 로직
├── docs/
│   ├── README.md                 # 문서 목차와 읽는 순서
│   ├── PRODUCT_BROCHURE.md       # 제품 소개서
│   ├── USER_GUIDE.md             # 사용자 가이드 + IFU 초안
│   ├── DATABASE.md                # MongoDB 스키마 (7 컬렉션 + 인덱스 일람)
│   ├── SECURITY.md                # 인증·인가·암호화·감사 로그·운영 가이드
│   ├── FEATURES.md                # 사용자/내부 동작 관점 전체 기능 명세
│   ├── COMPLIANCE_STATUS.md       # IEC 62304 / ISO 14971 / 21 CFR Part 11 충족 현황
│   └── color_match_analysis.md    # NDP 색 매칭 분석
├── install.bat / install.sh       # 의존성 설치
├── start.bat / start.sh           # 서버 시작
└── claudy_log.md                  # 작업 로그
```

## 데이터베이스

전체 스키마·인덱스·관계는 [docs/DATABASE.md](docs/DATABASE.md) 참조. 7개 컬렉션:

| 컬렉션 | 목적 |
| ----- | ---- |
| `users` | 인증 계정·권한·승인 상태·MFA 시드(암호화) |
| `sessions` | Refresh Token 세션 (rotation + reuse 탐지, TTL 자동 삭제) |
| `audit_logs` | 모든 보안·행위 이벤트 + HMAC 체인 + IP 위치 |
| `ip_geo_cache` | IP → 국가/도시 (TTL 30일) |
| `slides` | WSI 메타·AI 결과 플래그·SHA-256 체크섬·리뷰 상태 |
| `folder_ai_configs` | 폴더별 자동 AI 추론 작업 |
| `user_ai_edits` | 사용자별 셀 편집본 메타 (원본 캐시 분리) |

## 설치 및 실행

### 사전 요구사항

- Python 3.12+
- MongoDB 7.0+ (로컬 설치 또는 Docker). 미연결 시 인증/감사/AI 결과 캐싱 등이 비활성화됨
- OpenSlide 라이브러리 (Windows 는 `libs/openslide_lib/bin/` 자동 인식)
- (선택) NVIDIA GPU + CUDA 11.8+ — AI 추론 가속

### 1. 의존성 설치

```bash
cd backend
pip install -r requirements.txt
```

또는 루트의 `install.bat` (Windows) / `install.sh` (Linux/macOS) 실행.

### 2. MongoDB 시작

```bash
mongod --dbpath /data/db
```

### 3. 환경 변수 (모두 선택 — 미설정 시 기본값 또는 `.secrets.json` 자동 생성)

| 변수 | 기본값 | 설명 |
| ---- | ------ | ---- |
| `MONGO_URI` | `mongodb://localhost:27017` | MongoDB 연결 문자열 |
| `MONGO_DB_NAME` | `medicus_studio` | 데이터베이스 이름 |
| `JWT_SECRET_KEY` | `.secrets.json` 자동 생성 | 운영에서는 secret manager 로 주입 |
| `FIELD_ENCRYPTION_KEY` | `.secrets.json` 자동 생성 | AES-256-GCM 키 |
| `AUTH_PEPPER` | `.secrets.json` (legacy 또는 신규) | bcrypt pepper |
| `MEDIA_SIGNING_KEY` | JWT 키에서 파생 | 미디어 티켓 전용 키 (선택) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 15 | Access Token 수명 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | 7 | Refresh Token 수명 |
| `MAX_UPLOAD_BYTES` | 20 GB | 단일 파일 업로드 상한 |
| `TILE_CACHE_QUOTA_BYTES` | 50 GB | 타일 디스크 쿼터 (0 이면 janitor 비활성) |
| `CORS_ORIGINS` | "" (same-origin) | 쉼표 구분 origin 목록 |
| `TRUSTED_PROXIES` | "" (헤더 무시) | 신뢰 프록시 IP — `X-Forwarded-For` 인정 조건 |
| `UPLOAD_DIR` / `TILES_DIR` / `AI_RESULTS_DIR` | `backend/uploads,tiles,ai_results` | 캐시 위치 오버라이드 |

### 4. 서버 시작

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8091
```

또는 루트의 `start.bat` / `start.sh` 실행. 첫 가입자는 자동으로 admin + 즉시 승인된다.

## 인증 시스템

### RBAC 역할

| 역할 | 관리자 페이지 | AI 분석 | Annotation 저장 | 폴더 설정 | 슬라이드 조회 |
| ---- | :-----------: | :-----: | :-------------: | :-------: | :-----------: |
| `admin`  | ✅ | ✅ | ✅ | ✅ | ✅ |
| `doctor` | ❌ | ✅ | ✅ | ✅ | ✅ |
| `viewer` | ❌ | ❌ | ❌ | ❌ | ✅ |

> `technician` 역할은 폐지되었다. 기존 사용자는 startup 마이그레이션에서 `viewer` 로 자동 downgrade.
> `viewer` 제한은 백엔드 `require_not_viewer` 의존성 + 프론트엔드 `body.role-viewer` 게이팅으로 이중 적용.

### API 엔드포인트 (요약)

전체 일람은 [docs/FEATURES.md 부록 A](docs/FEATURES.md) 참조.

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/auth/register` | 회원가입 — 첫 사용자만 즉시 admin, 이후엔 `pending` |
| POST | `/api/auth/login` | 아이디/비밀번호 로그인 (+ TOTP 코드, geo enrichment 자동) |
| POST | `/api/auth/refresh` | 토큰 갱신 (CAS rotation + reuse 탐지 + 5분 grace) |
| POST | `/api/auth/logout` | 모든 세션 폐기 |
| POST | `/api/auth/change-password` | 비밀번호 변경 — 모든 세션 폐기 |
| GET | `/api/auth/media-ticket` | 미디어용 단기 HMAC 티켓 발급 |
| POST | `/api/auth/mfa/setup` | TOTP 시드 발급 + otpauth URI |
| POST | `/api/auth/mfa/verify` | 첫 코드 검증 → MFA 활성 |
| POST | `/api/auth/mfa/disable` | MFA 비활성 |
| GET | `/api/users/list` | 사용자 목록 (admin) |
| POST | `/api/users/approve` / `reject` | 가입 승인/거부 (admin, before/after 감사) |
| POST | `/api/users/role` / `toggle-active` / `unlock/{id}` | 역할/활성/잠금 (admin) |
| GET | `/api/users/audit-logs/verify-chain` | HMAC 체인 무결성 검증 (admin) |
| GET | `/api/users/activity/logins` / `{id}/activity` | 로그인·슬라이드·AI 활동 (admin) |
| GET | `/api/slides/{id}/verify-integrity` | SHA-256 체크섬 재계산 |

### 로그인·세션 정책

- **로그인 ID**: 4~30자, 영문/숫자/언더스코어만 허용 (`^[a-zA-Z0-9_]{4,30}$`)
- **비밀번호**: bcrypt cost=12 + pepper, 8자 이상 (대/소/숫/특수문자 모두 포함)
- **계정 잠금**: 5회 실패 → 30분 잠금 (시간 경과 시 자동 해제)
- **계정 열거 방지**: 비밀번호 검증을 먼저, 승인 상태 검증은 그 다음
- **Refresh Token**: 1회 사용 후 교체 (CAS rotation), 알 수 없는 토큰 재사용 → 사용자 전체 세션 폐기. 5분 grace window 로 모바일 백그라운드 탭 대응
- **이미지 URL**: JWT 노출 금지. `<img src>` 는 `?mt=<10분 HMAC 티켓>` 으로 인증
- **감사 로그**: 로그인 성공/실패/잠금, 비밀번호 변경, MFA 활성/실패, refresh 재사용 탐지 등 모든 보안 이벤트 + 모든 관리자 변경 작업 (before/after 포함)

## 운영 가이드

### 보안 체크리스트 (배포 전)

- [ ] `MONGO_URI` 에 인증 + TLS
- [ ] `JWT_SECRET_KEY` / `FIELD_ENCRYPTION_KEY` / `AUTH_PEPPER` 를 secret manager 에서 환경변수로 주입
- [ ] `.secrets.json` 권한 0600 + 백업 (단, 일반 백업과 분리 보관)
- [ ] CORS `CORS_ORIGINS` 화이트리스트
- [ ] 리버스 프록시 TLS + HSTS + CSP 헤더
- [ ] `TRUSTED_PROXIES` 에 실제 프록시 IP 등록 (외부 노출 시 빈 값 유지)
- [ ] 첫 admin 생성 직후 `/register` 접근을 리버스 프록시에서 차단하거나 신중히 운영
- [ ] MongoDB 자동 백업 스케줄, audit_logs 는 append-only 권한 분리

자세한 내용은 [docs/SECURITY.md](docs/SECURITY.md) 의 11/13장 참조.

### 알려진 한계

- **DB 미연결 시 anonymous admin** — 개발용 fallback. 운영 배포에서 MongoDB 가 잠시라도 끊기면 인증이 우회됨. orchestrator 헬스체크 필수.
- **Rate Limit 인메모리** — 단일 프로세스 전제. 멀티 프로세스 배포 시 Redis 등 외부 store 필요.
- **CPU 파티셔닝은 Linux 전용** — `os.sched_setaffinity` 미지원 OS 에선 noop fallback.
- **AES-GCM 필드 암호화는 검색 불가** — 인덱스 검색이 필요한 필드는 별도 HMAC 컬럼 필요.

## 코드 규칙

`.claude/CLAUDE.md` 참조 — Type-Prefix Naming 엄수.

- **변수**: `str_` / `int_` / `float_` / `bool_` / `list_` / `dict_` / `set_` / `tuple_` / `dt_` / `np_` / `df_` / `ser_` / `tensor_` / `model_` / `path_` / `plt_` / `obj_`
- **클래스**: `PascalCase` (접두어 없음)
- **상수**: `SCREAMING_SNAKE_CASE` (접두어 없음)
- **금지**: 가변 기본 인자(`[]`/`{}`), C-style `m_`/`g_` 접두어, 전역 변수 남용
- **작업 로그**: 주요 변경은 `claudy_log.md` 에 누적 기록

## 추가 문서

- [docs/README.md](docs/README.md) — 문서 목차와 읽는 순서
- [docs/PRODUCT_BROCHURE.md](docs/PRODUCT_BROCHURE.md) — 제품 소개서
- [docs/USER_GUIDE.md](docs/USER_GUIDE.md) — 사용자 가이드 + IFU 초안
- [docs/FEATURES.md](docs/FEATURES.md) — 전체 기능 명세 (사용자/내부 동작)
- [docs/DATABASE.md](docs/DATABASE.md) — MongoDB 스키마 + 인덱스
- [docs/SECURITY.md](docs/SECURITY.md) — 인증·인가·암호화·감사 로그·운영
- [docs/COMPLIANCE_STATUS.md](docs/COMPLIANCE_STATUS.md) — 의료기기 SW 규격 충족 현황
- [docs/color_match_analysis.md](docs/color_match_analysis.md) — Hamamatsu NDP 색 매칭 분석
