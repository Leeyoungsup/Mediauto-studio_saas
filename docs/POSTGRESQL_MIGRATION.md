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
2. `users`, `sessions`와 인증 API 전환
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

현재 첫 revision은 `users`, `sessions`만 생성한다. 애플리케이션 인증 경로는
2단계 Repository 전환이 완료되기 전까지 계속 MongoDB를 사용한다.

## 운영 전환 조건

- 모든 Repository parity 테스트 통과
- MongoDB와 PostgreSQL의 컬렉션/테이블별 레코드 수 일치
- 사용자 비밀번호 해시, MFA 암호문과 영구 `.secrets.json` 보존
- 로그인, 토큰 회전, 계정 잠금, 감사 로그 체인 회귀 테스트 통과
- 백업 복구 연습 및 롤백 테스트 통과
