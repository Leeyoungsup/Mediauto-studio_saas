# PostgreSQL 단계적 전환

이 브랜치는 MongoDB 서비스를 중단하지 않고 기능군별로 PostgreSQL로 이전한다.
전환이 완료될 때까지 기본값은 `DATABASE_BACKEND=mongodb`이며, PostgreSQL을
준비했다는 이유만으로 운영 트래픽을 PostgreSQL에 보내지 않는다.

## 원칙

- WSI 원본, 타일, AI 이미지와 대용량 산출물은 DB에 넣지 않는다.
- 기존 MongoDB ObjectId 문자열을 PostgreSQL `VARCHAR(36)` ID에 그대로 보존한다.
- 기능 단위로 Repository를 만들고 MongoDB/PostgreSQL 동작의 동등성 테스트를 통과시킨다.
- 테이블 변경은 Alembic revision으로만 수행한다.
- MongoDB 제거 전 전체 데이터 건수, 참조 관계와 핵심 필드를 교차 검증한다.

## 진행 단계

1. PostgreSQL 연결, Alembic, Docker Compose 기반 구성
2. `users`, `sessions`와 인증 API 전환 — **Repository 구현 완료**
3. `audit_logs`, `ip_geo_cache`, 임상정보 전환 — **Repository 및 이관 도구 구현 완료**
4. 프로젝트, 슬라이드, AI 상태와 annotation 전환
5. MongoDB → PostgreSQL 이관 도구, 검증 보고서와 롤백 절차 작성
6. 운영 안정화 후 Motor/PyMongo/MongoDB 제거

## 로컬 PostgreSQL 준비

실제 비밀번호가 들어가는 `.env.postgres`는 Git에 커밋하지 않는다.

```bash
cp .env.postgres.example .env.postgres
# .env.postgres의 비밀번호와 POSTGRES_URI를 같은 값으로 수정
docker compose --env-file .env.postgres -f compose.postgres.yml up -d
```

최초 인증 스키마를 적용한다.

```bash
set -a
source .env.postgres
set +a
cd backend
alembic upgrade head
```

현재 Alembic revision은 `users`, `sessions`, `audit_logs`, `ip_geo_cache`,
`case_clinical_info`, `audit_integrity_seals`를 생성한다. PostgreSQL Repository는
로그인, 계정 잠금, 토큰 회전 CAS, 로그아웃, 비밀번호 변경, MFA와 관리자 사용자
관리를 지원한다. 나머지 데이터는 계속 MongoDB를 사용하므로 전환 기간에는 두 DB가
모두 실행되어야 한다.

## 인증 데이터 이관 및 전환

데이터 이관 직전에는 회원가입과 사용자 관리 작업을 잠시 중지한다. 현재 단계는
dual-write가 아니므로 이관 중 변경된 계정은 자동 동기화되지 않는다.

```bash
cd backend

# 충돌과 예상 이관 건수 확인
python scripts/migrate_auth_to_postgres.py --dry-run

# 사용자와 활성/기존 Refresh Session 이관
python scripts/migrate_auth_to_postgres.py
```

사용자만 옮기고 모든 클라이언트를 다시 로그인시키려면 다음 옵션을 사용한다.

```bash
python scripts/migrate_auth_to_postgres.py --skip-sessions
```

검증을 통과한 후 애플리케이션의 인증 저장소를 전환한다.

```bash
export DATABASE_BACKEND=postgresql
export POSTGRES_URI='postgresql+asyncpg://mediauto:<url-encoded-password>@localhost:5432/medicus_studio'
./start.sh
```

비밀번호 해시는 재해시하지 않고 그대로 복사한다. MFA 암호문을 해독하려면 MongoDB
운영 당시의 `backend/.secrets.json` 또는 같은 `FIELD_ENCRYPTION_KEY`와
`AUTH_PEPPER`가 반드시 유지되어야 한다.

PostgreSQL 전환 후 MongoDB의 사용자 데이터는 더 이상 갱신되지 않는다. 되돌려야 할
경우 단순히 환경변수만 변경하지 말고, 전환 후 사용자 변경분을 먼저 역이관하거나
점검 시간 동안 PostgreSQL 쓰기를 중단해야 한다.

## 감사·IP 캐시·임상정보 이관

이 세 기능도 dual-write가 아니므로 전환 직전에는 로그인 및 임상정보 편집을 잠시
중지한다. 먼저 충돌과 예상 건수를 확인한 뒤 이관한다.

```bash
cd backend
python scripts/migrate_operational_to_postgres.py --dry-run
python scripts/migrate_operational_to_postgres.py
```

스크립트는 MongoDB ObjectId와 감사 로그 HMAC/이전 HMAC, IP 캐시 만료 시각,
임상정보 생성·수정 시각을 보존한다. 여러 번 실행해도 같은 ID 또는 자연키(IP,
case name)는 건너뛰며, 내용 충돌은 오류로 중단한다.

이관은 과거 감사 서명을 재생성하거나 덮어쓰지 않는다. 과거 MongoDB 구현은 Python
`datetime`을 HMAC에 사용한 뒤 BSON의 밀리초 정밀도로 저장하여 마지막
0~999마이크로초가 유실됐다. 이관 도구는 가능한 1,000개 값만 역검증해 원본 HMAC과
일치하는 정확한 서명 시각을 복원하고 `dt_hmac_created_at`에 보관한다. HMAC 값 자체는
변경하지 않는다. 앞으로 생성되는 로그는 저장 가능한 밀리초 값으로 먼저 정규화한 뒤
서명한다.

서명 기능 도입 전 로그와 과거 동시 요청으로 분기된 체인은 원래 서명이 있었다고
소급해서 만들지 않는다. 대신 이관된 MongoDB 감사 로그 전체를 정규 직렬화한 SHA-256
스냅샷과 HMAC 봉인을 `audit_integrity_seals`에 기록한다. 따라서 과거의 서명 유무를
정직하게 구분하면서도 이관 시점 이후의 수정·삭제·순서 변경은 탐지할 수 있다.
`/api/users/audit-logs/verify-chain`은 원본 HMAC, 복원된 서명 시각, 이관 봉인과 봉인
이후 신규 체인을 함께 검사해 `bool_integrity_intact`를 반환한다.

현재 슬라이드 본문은 MongoDB에 남아 있다. 임상정보의 기준 저장소는 PostgreSQL로
전환되지만, 기존 슬라이드 문서의 임상정보 읽기 fallback과 호환용 갱신은 다음 단계가
끝날 때까지 유지한다. 따라서 `DATABASE_BACKEND=postgresql`인 동안에도 MongoDB를
중지하면 안 된다.

## 운영 전환 조건

- 모든 Repository parity 테스트 통과
- MongoDB와 PostgreSQL의 컬렉션/테이블별 레코드 수 일치
- 사용자 비밀번호 해시, MFA 암호문과 영구 `.secrets.json` 보존
- 로그인, 토큰 회전, 계정 잠금, 감사 로그 체인 회귀 테스트 통과
- 백업 복구 연습 및 롤백 테스트 통과
