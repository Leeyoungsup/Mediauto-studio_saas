<!-- markdownlint-disable MD024 MD031 MD032 MD036 MD040 -->
# MeDIAuto Studio SaaS — 보안 설계

병원 On-Premise 배포 전제. 환자 WSI(조직 슬라이드)·AI 분석 결과·로그인 이력 등을 다루는 의료정보 시스템이므로, 인증/인가/감사/암호화 네 축을 모두 커버한다.

## 목차

1. [시크릿 관리](#1-시크릿-관리)
2. [비밀번호 저장](#2-비밀번호-저장)
3. [JWT 인증 & 세션](#3-jwt-인증--세션)
4. [계정 생애주기 & 잠금 정책](#4-계정-생애주기--잠금-정책)
5. [RBAC (역할 기반 접근 제어)](#5-rbac-역할-기반-접근-제어)
6. [미디어 URL 서명 (HMAC 티켓)](#6-미디어-url-서명-hmac-티켓)
7. [필드 레벨 암호화](#7-필드-레벨-암호화)
8. [감사 로그 (Audit Trail)](#8-감사-로그-audit-trail)
9. [네트워크 레이어](#9-네트워크-레이어)
10. [성능 최적화와 보안 균형](#10-성능-최적화와-보안-균형)
11. [알려진 한계 & 운영 가이드](#11-알려진-한계--운영-가이드)

---

## 1. 시크릿 관리

환경변수 → `.secrets.json`(0600) → 기본 생성 순서로 해결된다. 앱 시작 시 한 번 호출.

| 시크릿 | 환경변수 | 파일 키 | 생성 방식 | 용도 |
| ------ | -------- | ------- | --------- | ---- |
| JWT 서명 키 | `JWT_SECRET_KEY` | `jwt_secret_key` | `secrets.token_urlsafe(64)` | HS256 JWT 서명/검증 |
| 필드 암호화 키 | `FIELD_ENCRYPTION_KEY` | `field_encryption_key` | `secrets.token_urlsafe(32)` | AES-256-GCM 필드 암호화 |
| 비밀번호 Pepper | `AUTH_PEPPER` | `pepper` | `secrets.token_urlsafe(32)` (신규) 또는 legacy 값(기존) | bcrypt 입력 사전 연결 |
| 미디어 서명 키 | `MEDIA_SIGNING_KEY`(선택) | — | JWT 키에서 SHA-256 파생 | 미디어 HMAC 티켓 |

### 영속화 규칙

- 파일이 없으면 모든 키를 새로 생성 후 `.secrets.json`에 저장 — 재시작 후에도 기존 토큰/암호화 필드가 유효.
- 파일은 0600(소유자 전용). 저장소 push 금지 — `.gitignore` 필수.
- 환경변수가 설정돼 있으면 항상 환경변수 우선. 운영에서는 secret manager에서 환경변수로 주입하는 것을 권장.
- legacy pepper(`"MeDICus_2024_P3pp3r"`)는 과거 하드코딩 소스에서 이관된 호환용. 신규 설치에선 무작위 pepper가 쓰인다.

### 위협 모델

소스 코드 유출 시에도 시크릿 노출을 막기 위해 일체 하드코딩 없음. 서버 침해 시에는 `.secrets.json` 파일 보호가 최후 방어선이므로 디스크 파티션 권한 + 정기 로테이션 계획을 마련해야 한다.

---

## 2. 비밀번호 저장

### 해싱 알고리즘

```
hashed = bcrypt(plain + pepper, cost=12)
```

- **bcrypt** — `BCRYPT_COST = 12` (~250ms/해시). 병렬 brute-force 비용이 충분히 높음.
- **pepper** — bcrypt 입력 전 사전 연결. DB만 탈취되고 서버 파일(`.secrets.json`)은 안전한 경우 rainbow table 공격 무력화.
- **저장** — `users.str_hashed_password` 필드. 서버에선 평문을 일절 로깅하지 않음.
- **응답 차단** — MongoDB 프로젝션에서 `{"str_hashed_password": 0}`으로 기본 제외. 사용자 API 응답에 해시가 섞여 나갈 수 없음.

### 비밀번호 정책

- 최소 8자, 대/소문자 + 숫자 + 특수문자 포함 (정규식 패턴 검증).
- 아이디는 4~30자 영문/숫자/언더스코어만 허용.
- 계정 열거 방지 — 아이디 존재 여부 / 승인 상태에 따라 메시지를 다르게 반환하지 않고 "아이디 또는 비밀번호가 올바르지 않습니다"로 통일. 승인 상태 검증은 비밀번호 검증 **이후**에 수행.

---

## 3. JWT 인증 & 세션

### 토큰 구성

| 토큰 | 알고리즘 | 수명 | 저장 | 페이로드 |
| ---- | ------- | ---- | ---- | -------- |
| Access | HS256 | 15분 | 서버는 무상태(JWT 자체 검증) | `sub`, `role`, `type=access`, `exp`, `iat`, `jti` |
| Refresh | HS256 | 7일 | `sessions` 컬렉션에 원본 저장 | `sub`, `type=refresh`, `exp`, `iat`, `jti` |

- `jti` — 매 발급마다 `secrets.token_urlsafe(16)` (replay 추적·취소 시 사용).
- 서명 키: `JWT_SECRET_KEY` (위 시크릿 관리 참조).

### 토큰 전달

- **API 요청**: `Authorization: Bearer <access>` 헤더만 허용.
- **`?token=` query parameter 금지** — 과거엔 img.src 호환을 위해 허용했으나 JWT가 브라우저 히스토리/프록시 로그/Referer에 남아 계정 탈취 위험. 제거됨.
- **미디어(img.src)** — JWT 대신 **단기 HMAC 티켓**(`?mt=...`) 사용. 아래 6번 참조.

### Refresh 로테이션 + 재사용 탐지

`POST /api/auth/refresh`는 **원자적 CAS**(`find_one_and_update`)로 경쟁 상태를 처리한다:

1. `{str_refresh_token, bool_is_revoked: false}` 조건으로 `bool_is_revoked=true` + `str_replaced_by=<새 토큰>` 기록.
2. CAS 승리자: 새 세션 insert 후 새 토큰 반환.
3. CAS 패자(이미 revoked): `dt_rotated_at`과 현재 시각의 차가 `REFRESH_ROTATION_GRACE_SECONDS=300`(5분) 이내면 **grace window** — `str_replaced_by` 포인터를 따라가 replacement 세션 토큰을 반환(모바일 탭 suspend/재개 대응).
4. grace window를 초과한 revoked 토큰 재사용: 진짜 **reuse 공격**으로 간주 → 해당 사용자의 **전체 세션 일괄 폐기**(전역 로그아웃).

### 로그아웃

`POST /api/auth/logout`은 현재 사용자의 모든 `sessions` 문서를 revoke한다. 서버 측 세션 삭제로 access token이 만료될 때까지의 최대 15분 갭만 남음.

### 세션 TTL

`sessions.dt_expires_at`에 MongoDB TTL 인덱스(`expireAfterSeconds=0`) → 만료된 세션 자동 삭제.

---

## 4. 계정 생애주기 & 잠금 정책

### 가입 → 승인 플로우

1. `POST /api/auth/register` — 아이디/비밀번호/이름/부서 검증 후 사용자 생성.
   - **첫 번째 사용자**: `role=admin`, `approval_status=approved`, `is_active=true` (부트스트랩).
   - **이후**: `role=viewer`, `approval_status=pending`, `is_active=false`.
2. 관리자가 관리자 페이지에서 승인(역할 지정 가능) 또는 거부 호출.
3. 승인 후 `is_active=true` + `dt_approved_at` 기록.

### 로그인 실패 → 잠금

- 연속 실패 카운터: `int_failed_login_attempts`.
- `MAX_LOGIN_ATTEMPTS=5` 초과 시 `bool_is_locked=true` + `dt_locked_until = now + 30분`.
- 잠금 시간 경과 후 로그인 시도 시 카운터와 잠금 플래그 자동 리셋.
- 잠금 상태에서의 로그인 시도도 `user.login_locked` 액션으로 감사 로그 기록.

### 검증 순서 (계정 열거 방지)

`POST /api/auth/login`은 아래 순서를 엄격히 따른다:

1. 아이디로 사용자 조회 — 존재하지 않으면 즉시 401 ("아이디 또는 비밀번호가 올바르지 않습니다").
2. 계정 잠금 확인.
3. `is_active` 확인.
4. **비밀번호 검증** — 실패 시 카운터 +1, 401.
5. **이후** 승인 상태 확인 (pending/rejected) — 올바른 비밀번호를 가진 사용자만 승인 상태를 볼 수 있음. 공격자가 "가입된 계정인지"를 아이디로만 탐색할 수 없게 함.

---

## 5. RBAC (역할 기반 접근 제어)

`UserRole` enum은 `admin` / `doctor` / `viewer` 세 단계.

| 역할 | 관리자 페이지 | AI 분석 | Annotation 저장 | 폴더 설정 | 슬라이드 조회 |
| ---- | :-----------: | :-----: | :-------------: | :-------: | :-----------: |
| `admin`  | O | O | O | O | O |
| `doctor` | X | O | O | O | O |
| `viewer` | X | X | X | X | O |

### 의존성 팩토리

- **`get_current_user`** — 모든 보호된 엔드포인트의 기반. 활성/잠금/승인 상태 재검증. 30초 TTL 인메모리 캐시로 대량 요청 시 DB 부하 방지.
- **`require_role(*roles)`** — 특정 역할만 통과 (예: 관리자 API).
- **`require_not_viewer`** — viewer를 제외한 전부. annotation 저장, 폴더 설정, AI 분석 엔드포인트에 적용.

### 이중 방어

- **서버(소스 진실)**: `require_*` 의존성으로 403 반환.
- **프론트엔드 게이팅**: viewer 계정으로 로그인 시 AI/annotation 버튼을 비활성화하고 배너 표시. 서버가 거절해도 사용자가 "깨진 버튼"을 누르지 않도록 UX 보호.
- **"technician" role 폐기** — 기존 사용자는 startup 마이그레이션에서 `viewer`로 downgrade(권한 확대 금지 원칙).

### DB 미연결 Fallback

MongoDB가 연결되지 않은 상태(개발/뷰어 모드)에서는 `get_current_user`가 익명 admin을 반환한다. **운영 배포에서는 절대 이 경로가 활성화되면 안 된다** — 반드시 Mongo가 연결되어 있어야 인증이 강제된다.

---

## 6. 미디어 URL 서명 (HMAC 티켓)

### 문제 배경

타일/썸네일/프리뷰는 `<img src>`로 로드되므로 `Authorization` 헤더를 붙일 수 없다. 과거에는 `?token=<JWT>` fallback을 허용했으나:

- JWT가 브라우저 히스토리·Referer·프록시 로그·CDN 캐시 키에 노출 → 계정 탈취 시나리오.
- 7일 유효 Refresh 자격의 full-power 토큰이 이미지 URL에 실려 감.

### 해결

1. 로그인 직후 `/api/auth/media-ticket`에서 **단기 HMAC 티켓** 발급.
2. 프론트는 `<img src="/api/tiles/...?mt=<ticket>">`로 요청.
3. 서버는 `get_media_user` 의존성에서 티켓 검증 후 해당 사용자로 처리.
4. **API 엔드포인트는 절대 티켓을 받지 않음** — 미디어 엔드포인트(tiles, ai-media, slides-media)에만 주입되어 있어 스코프가 분리되어 있다.

### 구현 세부

- **포맷**: `<b64url(user_id|exp)>.<b64url(hmac_sha256)>`
- **서명 키 파생**: `SHA256("media-ticket-v1|" || JWT_SECRET_KEY)` — 도메인 분리를 위해 JWT 키를 그대로 쓰지 않고 컨텍스트 문자열로 해시. `MEDIA_SIGNING_KEY` 환경변수가 있으면 그것이 우선.
- **TTL**: 600초(10분). 누출 시 블래스트 반경 = 10분 x 미디어 엔드포인트만.
- **검증**: `hmac.compare_digest`로 상수 시간 비교. 만료 확인은 `exp` 필드.
- **스테이트리스**: DB 조회 없음 — 서명만으로 통과.

---

## 7. 필드 레벨 암호화

- **알고리즘**: AES-256-GCM — 암호화 + 인증(tag) 동시 제공.
- **키**: `FIELD_ENCRYPTION_KEY`에서 base64url 디코드 후 32바이트 정렬.
- **Nonce**: 매 암호화마다 `os.urandom(12)`로 새 값. **nonce 재사용은 GCM 보안을 파괴하므로 절대 재사용하지 않음.**
- **저장 형식**: `base64url(nonce || ciphertext || tag)` — 단일 문자열.
- **용도**: TOTP 비밀키 등 민감 필드. 현재는 유틸 제공 상태이며 모델별 적용은 점진적.

### 한계

- 검색 불가(AES-GCM은 비결정적) — 인덱스 검색이 필요한 필드는 암호화 대신 해시 별도 컬럼 + 원본 암호화 조합이 필요.
- 키 유출 시 과거 데이터 전부 복호화 가능 — 정기 roll-over 계획 권장(envelope encryption으로 업그레이드 여지).

---

## 8. 감사 로그 (Audit Trail)

### 기록 원칙

- 병원 환경 기준 **최소 5년 보존** (규정 준수).
- **불변** — 앱 로직에 update/delete가 존재하지 않음. MongoDB 권한 수준에서도 append-only 롤을 쓰는 것을 권장.
- **보안 이벤트 + 행위 이벤트 모두 기록**.

### 기록 대상 actions

| action | 트리거 |
| ------ | ------ |
| `user.register` | 회원가입 |
| `user.login_success` | 로그인 성공 (+ geo enrichment) |
| `user.login_failed` | 비밀번호 오류 (실패 횟수 포함) |
| `user.login_locked` | 잠금 상태 로그인 시도 |
| `user.login_pending` / `user.login_rejected` | 승인 전/거부된 계정의 로그인 시도 |
| `admin.user_approved` / `admin.user_rejected` | 관리자 승인/거부 (before/after 기록) |
| `admin.user_created` | 관리자 사용자 생성 |
| `admin.user_updated` | 관리자 사용자 수정 (변경 필드별 before/after) |
| `admin.user_deleted` | 관리자 사용자 삭제 (삭제 전 스냅샷 보관) |
| `admin.role_changed` | 역할 변경 (before/after) |
| `admin.user_activated/deactivated` | 활성 토글 (before/after) |
| `admin.user_unlocked` | 잠금 해제 (before/after) |
| `slide.view` | 슬라이드 열기 — rel_path, filename 포함 |
| `ai.analyze` | AI 4종 엔드포인트 호출 — model, variant 포함 |

### 21 CFR Part 11 변경 전/후 값 기록

관리자의 모든 사용자 변경 작업에 `dict_before`/`dict_after` 필드를 기록한다:

- **승인**: approval_status, role, is_active 변경 전/후
- **거부**: approval_status, is_active 변경 전/후
- **수정**: 변경된 필드만 선택적으로 기록 (이름, 부서, 비밀번호는 마스킹)
- **삭제**: 삭제 전 사용자 전체 스냅샷을 dict_before에, dict_after는 null
- **역할 변경**: str_role 변경 전/후
- **활성 토글**: bool_is_active 변경 전/후
- **잠금 해제**: bool_is_locked, int_failed_login_attempts 변경 전/후

### HMAC 체인 무결성

각 감사 로그에 이전 로그의 HMAC을 포함하여 연쇄 서명한다:

- **서명 대상**: action, user_id, user_email, resource_type, resource_id, detail, ip_address, created_at, prev_hmac
- **알고리즘**: HMAC-SHA256
- **키 파생**: JWT 시크릿 + `:audit_log_chain` 문자열을 SHA-256으로 파생 (도메인 분리)
- **체인 캐싱**: 마지막 HMAC을 메모리에 보관하여 매 로그 기록 시 DB 조회 없이 체인 연결. 앱 시작 후 첫 호출 시만 DB에서 1회 로드.
- **검증**: `/audit-logs/verify-chain` 엔드포인트로 체인 무결성 일괄 검증. 중간 로그가 삭제/수정되면 체인이 끊어져 즉시 감지 가능.

### 클라이언트 IP 추출

`get_client_ip()`는 `X-Forwarded-For` → `X-Real-IP` → `request.client.host` 순으로 추출. 리버스 프록시(Nginx 등) 뒤에서도 원 클라이언트 IP를 얻을 수 있다. **단 프록시가 이 헤더를 신뢰할 수 있게 설정한 경우에만** — 외부로 노출된 서버라면 직접 client.host를 쓰도록 조정해야 한다.

### Geo Enrichment

로그인 성공 직후 fire-and-forget 비동기 태스크로 IP 지리정보를 추가한다:

- **외부 API**: `ip-api.com` (free tier, 45 req/min, no key required).
- **캐시**: `ip_geo_cache` 컬렉션에 30일 TTL — IP당 1회만 외부 호출.
- **사설 IP 스킵**: 127./10./192.168./172.16-31./169.254./::1/fe80:/fc00:/fd00: — 외부 API 호출 없이 즉시 반환.
- **비블로킹**: 응답 경로를 차단하지 않음. 실패해도 로그는 남고 geo 필드만 비어있게 됨.

---

## 9. 네트워크 레이어

### CSRF 방어

Pure ASGI 미들웨어로 구현. 상태 변경 요청(POST/PUT/PATCH/DELETE)에 `X-Requested-With` 헤더가 있는지 검증한다. `BaseHTTPMiddleware`를 사용하지 않고 ASGI scope의 headers를 직접 읽어 body 버퍼링 오버헤드를 제거했다.

- 안전한 메서드(GET/HEAD/OPTIONS)는 검증 생략
- 인증 경로(/api/auth/login, /api/auth/register)는 화이트리스트 제외
- 미디어 경로(tiles, 썸네일 등 GET 요청)는 해당 없음

### Rate Limiting

Pure ASGI 미들웨어로 구현. IP별 슬라이딩 윈도우 방식:

- **로그인 엔드포인트**: 10회/5분 (brute-force 방어)
- **일반 API**: 200회/분
- 인메모리 딕셔너리로 타임스탬프 관리, 주기적 만료 정리
- `BaseHTTPMiddleware` 대신 순수 ASGI로 body 버퍼링 없음

### CORS

환경변수 `CORS_ORIGINS`로 허용 origin 지정. 비어 있으면 same-origin 전용(StaticFiles 서빙이므로 CORS 불필요).

### 정적 파일 캐싱

`.js/.html/.css`에 `Cache-Control: no-cache, must-revalidate`를 강제. ETag는 유지되어 304 가능. API 계약 변경 후 사용자가 "하드 리프레시해도 안 되는" 상황을 방지한다. 보안상 장점: 취약점 패치된 JS가 즉시 반영됨.

### 미설정 항목

- **CSP / HSTS / X-Frame-Options**: 현재 미설정. 리버스 프록시 레이어에서 추가 권장.
- **업로드 한계**: `MAX_UPLOAD_BYTES = 20 GB` (환경변수로 조정). WSI 파일 크기 고려값.

---

## 10. 성능 최적화와 보안 균형

보안 미들웨어와 인증 로직이 타일 서빙 등 대량 요청에 미치는 성능 영향을 최소화하기 위해 다음 최적화를 적용했다:

### Pure ASGI 미들웨어

CSRF, Rate Limiting 미들웨어를 `BaseHTTPMiddleware` 대신 순수 ASGI 프로토콜로 구현했다. `BaseHTTPMiddleware`는 모든 요청에서 request body를 메모리로 버퍼링하는데, 타일 요청처럼 body가 없는 GET 요청에서도 이 오버헤드가 발생한다. Pure ASGI는 scope의 headers만 읽어 판단하므로 body 버퍼링이 없다.

### 사용자 정보 인메모리 캐시

`get_current_user`와 `get_media_user`는 인증된 사용자 정보를 30초 TTL 메모리 캐시에 보관한다. 한 화면에 수십~수백 개의 타일 요청이 발생하는 WSI 뷰어 특성상, 모든 요청마다 `db.users.find_one()`을 호출하면 DB 부하가 크다.

- 캐시 키: user_id 문자열
- TTL: 30초 (비활성화/잠금 반영 지연 허용 범위)
- 무효화: 관리자가 사용자 정보를 변경(승인/거부/수정/삭제/역할변경/활성토글/잠금해제)하면 해당 사용자의 캐시를 즉시 무효화

### 감사 로그 HMAC 체인 캐시

감사 로그의 HMAC 체인은 이전 로그의 HMAC을 참조해야 하므로 원래 매번 DB에서 마지막 로그를 조회해야 한다. 이를 메모리 캐시로 대체하여 앱 시작 후 첫 호출 시만 DB 조회, 이후에는 메모리에서 체인을 이어간다.

### 대시보드 통계 최적화

- 디스크 사용량 계산: 동기 `os.walk`를 `run_in_executor`로 스레드 풀에서 실행 + 60초 캐시
- DB 집계: 9개 이상의 `count_documents` 호출을 단일 `$facet` 파이프라인으로 통합

---

## 11. 알려진 한계 & 운영 가이드

### 반드시 운영 배포 전 조치할 것

- [ ] `MONGO_URI`에 실제 인증 + TLS 설정
- [ ] `JWT_SECRET_KEY` / `FIELD_ENCRYPTION_KEY` / `AUTH_PEPPER`를 secret manager에서 환경변수로 주입
- [ ] CORS `allow_origins`를 실제 프론트엔드 도메인으로 제한
- [ ] 리버스 프록시에서 TLS 종료 + HSTS + CSP 헤더 추가
- [ ] `X-Forwarded-For` 신뢰 범위 확정 (내부망 프록시만)
- [ ] `MONGO_URI`에서 `audit_logs` 컬렉션은 append-only 권한의 별도 유저로 쓰도록 분리
- [ ] 첫 번째 가입자가 admin이 되는 부트스트랩 규칙을 악용당하지 않도록, 첫 배포 직후 즉시 관리자 계정을 만들고 회원가입 엔드포인트를 보호
- [ ] 정기 백업: `users` + `audit_logs` + `.secrets.json`

### 설계상 한계

- **DB 미연결 시 anonymous admin** — 개발 편의용 fallback. 운영에서 Mongo가 잠시라도 끊기면 인증이 우회된다. Mongo 헬스체크로 앱이 unhealthy 상태가 되도록 orchestrator 레벨에서 보장할 것.
- **AES-GCM 필드 암호화는 검색 불가** — 암호화된 필드로는 쿼리할 수 없음. 필요 시 HMAC 인덱스 컬럼 추가.
- **Refresh rotation grace window 5분** — 너무 길면 reuse 탐지가 둔해지고, 너무 짧으면 모바일 백그라운드 탭이 깨어날 때 세션 무효화 경험. 현재 값은 경험적 절충.
- **사용자 캐시 30초 TTL** — 관리자 변경은 즉시 무효화되지만, 일반 사용자 상태 변경(비밀번호 변경 등)은 최대 30초 지연 가능. 보안상 민감한 작업(비밀번호 변경)은 세션 revoke로 추가 방어.
- **WebSocket 채널 없음** — 현재 모든 통신이 HTTP. 실시간 알림이 필요해지면 JWT over WS 설계 추가 필요.

### 취약점 대응 절차

1. **비밀번호 유출 의심**: 해당 사용자 강제 비밀번호 리셋 + 세션 revoke.
2. **JWT 시크릿 유출 의심**: `JWT_SECRET_KEY` 교체 → 모든 기존 토큰 무효화(전체 강제 재로그인).
3. **필드 암호화 키 유출 의심**: `FIELD_ENCRYPTION_KEY` 교체 + 과거 데이터 재암호화 스크립트 필요.
4. **관리자 계정 탈취**: admin 역할 사용자 전체 비밀번호 리셋 + `audit_logs`에서 해당 기간 행위 포렌식.

---

## 부록 A — 보안 관련 모듈 구조

```
backend/
├── .secrets.json                      # 0600, git ignore (시크릿 영속화)
├── app/
│   ├── config.py                      # 시크릿 로딩/생성
│   ├── models.py                      # bcrypt + pepper 비밀번호 해싱
│   ├── auth.py                        # JWT 생성/검증, 사용자 인증, RBAC, 인메모리 캐시
│   ├── audit.py                       # 감사 로그 기록 + HMAC 체인 + IP 추출
│   ├── geo.py                         # IP → geo 캐시 (ip-api.com)
│   ├── encryption.py                  # AES-256-GCM 필드 암호화
│   ├── url_signer.py                  # 미디어 HMAC 티켓
│   ├── csrf.py                        # Pure ASGI CSRF 미들웨어
│   ├── rate_limit.py                  # Pure ASGI Rate Limiting 미들웨어
│   └── routers/
│       ├── auth.py                    # 로그인/refresh/logout + 잠금 로직
│       └── users.py                   # 승인/관리 + 활동 로그 + 캐시 무효화
└── main.py                            # CORS, 미들웨어 등록, 정적 파일 캐시 정책
```

## 부록 B — 체크리스트 (배포 직전)

```
[ ] MONGO_URI 에 인증 + TLS
[ ] JWT_SECRET_KEY / FIELD_ENCRYPTION_KEY / AUTH_PEPPER 환경변수 주입
[ ] .secrets.json 권한 0600 + 백업
[ ] CORS allow_origins 화이트리스트
[ ] 리버스 프록시 TLS + HSTS + CSP
[ ] X-Forwarded-For 신뢰 범위 확정
[ ] audit_logs 전용 append-only DB 유저
[ ] 첫 admin 생성 직후 /register 접근 제한
[ ] MongoDB 자동 백업 스케줄
[ ] 정기 보안 패치 (FastAPI / bcrypt / cryptography / python-jose)
```
