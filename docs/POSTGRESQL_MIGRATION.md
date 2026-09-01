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
3. `audit_logs`, `ip_geo_cache`, 임상정보 전환
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

현재 첫 revision은 `users`, `sessions`를 생성한다. PostgreSQL Repository는
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

## 운영 전환 조건

- 모든 Repository parity 테스트 통과
- MongoDB와 PostgreSQL의 컬렉션/테이블별 레코드 수 일치
- 사용자 비밀번호 해시, MFA 암호문과 영구 `.secrets.json` 보존
- 로그인, 토큰 회전, 계정 잠금, 감사 로그 체인 회귀 테스트 통과
- 백업 복구 연습 및 롤백 테스트 통과
