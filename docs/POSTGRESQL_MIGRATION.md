# PostgreSQL 전환 완료 상태

MeDIAuto Studio SaaS의 기준 저장소는 PostgreSQL 하나다. 인증, 세션, 감사 로그,
IP 위치 캐시, 임상정보, 프로젝트, 슬라이드, AI 상태 및 annotation을 모두 PostgreSQL에
저장한다. 애플리케이션은 별도의 데이터베이스 백엔드 선택 변수를 사용하지 않는다.

## 현재 구성

- `users`, `sessions`: 계정, MFA, 잠금, Refresh Token 회전
- `audit_logs`, `audit_integrity_seals`: 행위 기록과 HMAC 무결성 검증
- `ip_geo_cache`: IP 위치 캐시
- `case_clinical_info`: 케이스별 임상정보
- `application_documents`: 프로젝트·슬라이드·AI·annotation JSONB 문서
- `application_data_migrations`: 과거 전환 완료 검증 마커

대용량 WSI 원본, 타일 및 AI 이미지 산출물은 파일 저장소에 두며 PostgreSQL에는
경로, 상태, 체크섬과 사용자 편집 메타데이터를 저장한다.

## 설치 방식

기본 Docker 모드:

```bash
./install.sh
```

Linux에서 Docker 없이 프로젝트 전용 PostgreSQL 18을 설치하려면:

```bash
export MEDIAUTO_POSTGRES_MODE=native
./install.sh
```

외부 PostgreSQL을 사용하려면:

```bash
export MEDIAUTO_POSTGRES_MODE=external
export POSTGRES_URI='postgresql+asyncpg://user:encoded-password@db-host:5432/medicus_studio'
./install.sh
```

설치기는 `.env.postgres`를 소유자 전용 권한으로 만들고, 서비스를 준비한 뒤
`alembic upgrade head`와 런타임 bootstrap을 실행한다. 기존 Conda 환경에 남은
Motor/PyMongo는 설치 과정에서 제거된다.

## 스키마 관리

스키마 변경은 Alembic revision으로만 수행한다.

```bash
set -a
source .env.postgres
set +a
cd backend
alembic upgrade head
```

현재 head는 `20260901_0004`다. 배포 전 다음 명령으로 확인한다.

```bash
cd backend
alembic current
alembic heads
```

## 백업

데이터베이스와 애플리케이션 영구 키를 같은 복구 시점으로 보존한다.

```bash
pg_dump --format=custom --file=medicus_studio.dump "$POSTGRES_URI_FOR_PG_TOOLS"
pg_restore --list medicus_studio.dump
```

SQLAlchemy의 `postgresql+asyncpg` URI는 `pg_dump`가 직접 받지 않으므로 pg 도구에는
`postgresql://` 형식의 URI를 사용한다. `.secrets.json` 또는 동일한 환경변수 키가
없으면 기존 비밀번호, MFA 암호문 및 감사 무결성 검증을 정상 복구할 수 없다.

## 전환 후 호환 데이터

과거 데이터에서 가져온 문자열 ID와 감사 로그 서명 시각은 PostgreSQL에 그대로
보존된다. 감사 검증 코드에 남아 있는 과거 정밀도 보정과 전환 봉인 이름은 기존
감사 기록을 검증하기 위한 데이터 호환 규칙이며 외부 데이터베이스 연결이 아니다.

과거 전환 스크립트와 롤백 덤프는 제거됐다. 새 설치와 현재 런타임에는 Motor,
PyMongo 또는 별도 MongoDB 서비스가 필요하지 않다.

## 운영 확인

```bash
conda run -n medicus-saas python -m pip check
curl --fail http://127.0.0.1:8092/api/health
```

추가로 로그인, 토큰 회전, 계정 잠금, 임상정보, 슬라이드 목록, AI 결과,
annotation 저장 및 감사 로그 검증을 릴리스 회귀 테스트에 포함한다.
