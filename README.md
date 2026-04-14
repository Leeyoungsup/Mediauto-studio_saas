# MeDICus Studio SaaS

병원 온프레미스(On-Premise) 배포를 위한 디지털 병리 WSI(Whole Slide Image) 뷰어 + AI 분석 플랫폼

## 주요 기능

| 기능 | 설명 |
|------|------|
| WSI 뷰어 | OpenSlide 기반 멀티 레벨 타일 렌더링 (SVS, NDPI, TIFF 등), Canvas 기반 annotation (polygon lasso / rectangle / point) |
| HE-Fit | 조직 유형별 핏 분석 (Stomach, Breast, Other) |
| PD-Score | PD-L1 scoring |
| Precise-IHC | IHC 정밀 정량 분석 |
| VS-IHC | Virtual Staining — HE → IHC membrane/nucleus 변환 |
| 폴더 자동 AI | `folder_ai_configs` 기반, 1분마다 미완 variant 자동 추론 |
| 계정 관리 | MongoDB + JWT 기반 인증/인가 (RBAC, 승인제) |
| 활동 로그 | 로그인·슬라이드 뷰·AI 분석을 `audit_logs`에 기록 + IP 지리정보 enrichment |
| 민감 데이터 암호화 | AES-256-GCM 필드 레벨 암호화 |

## 기술 스택

- **Backend**: Python 3.12, FastAPI, Uvicorn
- **Frontend**: Vanilla JS (ES Modules), HTML5 Canvas
- **Database**: MongoDB 8.x (motor async driver)
- **인증**: JWT (HS256) — Access Token 15분 / Refresh Token 7일, 아이디 기반 로그인
- **암호화**: bcrypt (cost=12 + pepper), AES-256-GCM, python-jose
- **슬라이드**: OpenSlide, Pillow

## 프로젝트 구조

```
├── backend/
│   ├── main.py                # FastAPI 진입점 (Uvicorn, port 8091)
│   ├── requirements.txt       # Python 의존성
│   ├── app/
│   │   ├── config.py          # 설정 (DB, JWT, 보안, 타일)
│   │   ├── database.py        # MongoDB 연결 + 인덱스/마이그레이션
│   │   ├── models.py          # User 모델, bcrypt 해싱, UserRole enum
│   │   ├── auth.py            # JWT 생성/검증, get_current_user, require_role, require_not_viewer
│   │   ├── audit.py           # 감사 로그 유틸리티 (log_audit_event)
│   │   ├── geo.py             # IP → 국가/도시 geolocation 캐시 (ip-api.com, TTL 30일)
│   │   ├── encryption.py      # AES-256-GCM 필드 암호화/복호화
│   │   ├── slide_manager.py   # OpenSlide 래퍼 (캐싱, 메타데이터)
│   │   ├── slide_store.py     # slides 컬렉션 helper (upsert/touch/mark_ai_result)
│   │   ├── tile_generator.py  # 타일 프리제네레이션
│   │   ├── auto_ai.py         # 폴더별 AI 자동 추론 워커
│   │   └── routers/
│   │       ├── auth.py        # 인증 API (register, login, refresh, logout) + geo enrich
│   │       ├── users.py       # 관리자 전용 사용자 관리 + 활동 로그 조회 API
│   │       ├── slides.py      # 슬라이드 업로드/열기/annotation/folder-config API
│   │       ├── tiles.py       # 프리타일 서빙 API
│   │       └── ai.py          # AI 분석 (HE-Fit, PD-Score, Precise-IHC, VS-IHC) API
│   ├── uploads/               # 업로드된 WSI 원본 (HnE/, IHC/)
│   ├── tiles/                 # 프리제네레이트 타일 캐시
│   └── ai_results/            # AI 분석 결과 JSON 캐시
├── frontend/
│   ├── index.html             # 인증 리다이렉트 (토큰 확인)
│   ├── login.html             # 로그인/회원가입 페이지
│   ├── app.html               # 메인 뷰어 페이지
│   ├── admin.html             # 관리자 페이지 (승인/사용자/활동 로그)
│   ├── css/
│   │   ├── style.css
│   │   └── admin.css          # 관리자 페이지 전용 스타일
│   └── js/
│       ├── api.js             # REST API 클라이언트 (JWT 자동 관리)
│       ├── app.js             # 메인 앱 로직
│       ├── tile-viewer.js     # Canvas 타일 렌더러 + annotation
│       ├── visualization.js   # AI 결과 오버레이 시각화
│       └── admin.js           # 관리자 페이지 로직
├── docs/
│   └── DATABASE.md            # MongoDB 스키마 문서 (6개 컬렉션)
├── install.bat                # 의존성 설치 스크립트
└── start.bat                  # 서버 시작 스크립트
```

## 데이터베이스

전체 스키마·인덱스·관계는 [docs/DATABASE.md](docs/DATABASE.md) 참조. 컬렉션 6개:
`users` / `sessions` / `audit_logs` / `ip_geo_cache` / `slides` / `folder_ai_configs`

## 설치 및 실행

### 사전 요구사항
- Python 3.12+
- MongoDB 7.0+ (로컬 설치 또는 Docker)
- Conda (선택)

### 1. 의존성 설치
```bash
cd backend
pip install -r requirements.txt
```

### 2. MongoDB 시작
```bash
mongod --dbpath /data/db
```

### 3. 환경 변수 (선택 — 기본값 있음)
```bash
set MONGO_URI=mongodb://localhost:27017
set MONGO_DB_NAME=medicus_studio
set JWT_SECRET_KEY=<운영 시 반드시 고정 값 설정>
set FIELD_ENCRYPTION_KEY=<운영 시 반드시 고정 값 설정>
```

### 4. 서버 시작
```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8091
```
또는 `start.bat` 실행

## 인증 시스템

### RBAC 역할

| 역할 | 관리자 페이지 | AI 분석 | Annotation 저장 | 폴더 설정 | 슬라이드 조회 |
| ---- | :-----------: | :-----: | :-------------: | :-------: | :-----------: |
| `admin`  | ✅ | ✅ | ✅ | ✅ | ✅ |
| `doctor` | ❌ | ✅ | ✅ | ✅ | ✅ |
| `viewer` | ❌ | ❌ | ❌ | ❌ | ✅ |

> `technician` 역할은 폐지되었다. 기존 사용자는 startup 시 `viewer`로 자동 downgrade.
> `viewer` 제한은 백엔드 `require_not_viewer` 의존성 + 프론트엔드 `body.role-viewer` 게이팅으로 이중 적용.

### API 엔드포인트
| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/auth/register` | 회원가입 — 기본적으로 `pending` 상태 (admin 승인 필요) |
| POST | `/api/auth/login` | 아이디/비밀번호 로그인 (geo enrichment 자동) |
| POST | `/api/auth/refresh` | 토큰 갱신 (원자적 CAS rotation + 재사용 탐지) |
| POST | `/api/auth/logout` | 로그아웃 (모든 세션 폐기) |
| GET | `/api/auth/me` | 현재 사용자 정보 |
| POST | `/api/auth/change-password` | 비밀번호 변경 |
| GET | `/api/users/list` | 사용자 목록 (admin) |
| POST | `/api/users/{id}/approve` | 가입 승인 (admin) |
| POST | `/api/users/{id}/reject` | 가입 거부 (admin) |
| PATCH | `/api/users/{id}` | 사용자 수정 (admin) |
| GET | `/api/users/activity/logins` | 로그인 활동 로그 페이지네이션 (admin) |
| GET | `/api/users/{id}/activity` | 사용자 상세 활동 (login/slide/ai 카테고리별, admin) |

### 로그인 정책
- **로그인 ID**: 4~30자, 영문/숫자/언더스코어만 허용 (`^[a-zA-Z0-9_]{4,30}$`)
- **비밀번호**: bcrypt cost=12 + pepper, 8자 이상 (대/소/숫/특수)
- 로그인 실패: 5회 초과 시 30분 계정 잠금
- Refresh Token: 1회 사용 후 교체 (rotation), 재사용 시 모든 세션 폐기 (reuse detection)
- 이미지 URL: query parameter token 인증 (img.src 호환)
- 감사 로그: 로그인/로그아웃/비밀번호 변경 등 모든 보안 이벤트 기록

## 코드 규칙

`.claude/Claude.md` 참조 — Type-Prefix Naming 엄수
- `df_`: DataFrame, `np_`: ndarray, `str_`: 문자열, `int_`: 정수, `dict_`: 딕셔너리 등
- 클래스: PascalCase, 상수: SCREAMING_SNAKE_CASE
