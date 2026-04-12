# MeDICus Studio SaaS

병원 온프레미스(On-Premise) 배포를 위한 디지털 병리 WSI(Whole Slide Image) 뷰어 + AI 분석 플랫폼

## 주요 기능

| 기능 | 설명 |
|------|------|
| WSI 뷰어 | OpenSlide 기반 멀티 레벨 타일 렌더링 (SVS, NDPI, TIFF 등) |
| HE-Fit | 조직 유형별 핏 분석 (Stomach, Breast, Other) |
| VS-IHC | Virtual Staining — HE → IHC membrane/nucleus 변환 |
| 계정 관리 | MongoDB + JWT 기반 인증/인가 (RBAC) |
| 감사 로그 | 모든 사용자 행위를 audit_logs 컬렉션에 기록 (5년 보존) |
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
│   │   ├── database.py        # MongoDB 연결 (motor, 싱글톤)
│   │   ├── models.py          # User 모델, bcrypt 해싱, UserRole enum
│   │   ├── auth.py            # JWT 생성/검증, get_current_user, require_role
│   │   ├── audit.py           # 감사 로그 유틸리티
│   │   ├── encryption.py      # AES-256-GCM 필드 암호화/복호화
│   │   ├── slide_manager.py   # OpenSlide 래퍼 (캐싱, 메타데이터)
│   │   ├── tile_generator.py  # 타일 프리제네레이션
│   │   └── routers/
│   │       ├── auth.py        # 인증 API (register, login, refresh, logout)
│   │       ├── users.py       # 관리자 전용 사용자 관리 API
│   │       ├── slides.py      # 슬라이드 업로드/열기/타일 API
│   │       ├── tiles.py       # 프리타일 서빙 API
│   │       └── ai.py          # AI 분석 (HE-Fit, VS-IHC) API
│   ├── uploads/               # 업로드된 WSI 원본 (HnE/, IHC/)
│   ├── tiles/                 # 프리제네레이트 타일 캐시
│   └── ai_results/            # AI 분석 결과 JSON 캐시
├── frontend/
│   ├── index.html             # 인증 리다이렉트 (토큰 확인)
│   ├── login.html             # 로그인/회원가입 페이지
│   ├── app.html               # 메인 뷰어 페이지
│   ├── css/style.css
│   └── js/
│       ├── api.js             # REST API 클라이언트 (JWT 자동 관리)
│       ├── app.js             # 메인 앱 로직
│       ├── tile-viewer.js     # Canvas 타일 렌더러
│       └── visualization.js   # AI 결과 오버레이 시각화
├── install.bat                # 의존성 설치 스크립트
└── start.bat                  # 서버 시작 스크립트
```

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
| 역할 | 설명 |
|------|------|
| `admin` | 모든 권한 + 사용자 관리 |
| `doctor` | 슬라이드 조회 + AI 분석 |
| `technician` | 슬라이드 업로드 + 조회 |
| `viewer` | 조회만 가능 |

### API 엔드포인트
| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/auth/register` | 회원가입 — 아이디/비밀번호/이름/부서 (최초 가입자 = admin) |
| POST | `/api/auth/login` | 아이디/비밀번호 로그인 |
| POST | `/api/auth/refresh` | 토큰 갱신 |
| POST | `/api/auth/logout` | 로그아웃 (모든 세션 폐기) |
| GET | `/api/auth/me` | 현재 사용자 정보 |
| POST | `/api/auth/change-password` | 비밀번호 변경 |
| GET | `/api/users/list` | 사용자 목록 (admin) |
| POST | `/api/users/role` | 역할 변경 (admin) |

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
