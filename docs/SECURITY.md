<!-- markdownlint-disable MD024 MD031 MD032 MD036 MD040 -->
# MeDIAuto Studio SaaS — 보안 설계

병원 On-Premise 배포 전제. 환자 WSI(조직 슬라이드)·AI 분석 결과·로그인 이력 등을 다루는 의료정보 시스템이며, **SaMD (Software as a Medical Device) 2등급** 인허가를 목표로 설계된다. 인증/인가/감사/암호화 네 축에 더해, IEC 62304·ISO 14971·21 CFR Part 11·식약처 의료기기 사이버보안 가이드라인의 기술 통제 항목을 우선 구현했다.

## 2026-10-08 체크리스트 보완 코드 적용

- KP07: 새 비밀번호 최소 9자리, 영문 대·소문자·숫자·특수문자 조합. 변경일에서 90일 경과 또는 변경일 미상 시 비밀번호 변경만 허용하며 일반 기능과 미디어 접근은 차단한다. 신규 설치 관리자는 설치 비밀번호를 반드시 변경한다. 새 로그인은 이전 접속의 access·refresh·미디어 티켓을 무효화한다.
- KP18: 서버의 마지막 사용자 입력 시각에서 30분 경과 시 access·refresh·미디어·activity 요청을 차단한다. 키보드·포인터·스크롤 입력만 `/api/auth/activity`에 전송하며, 토큰 갱신·타일 로드·polling은 활동 시각을 연장하지 않는다. 클라이언트에서도 유휴 시 토큰을 지우고 로그인으로 이동한다.
- KP26: ZIP 다운로드는 사유를 필수로 검증한다. 로컬 ROI JSON·분석 PDF 출력은 사유를 서버에 기록한 뒤 저장한다. 사용자 ID·대상 파일·시각·IP·사유를 감사로그에 남기며 기록 실패 시 반출을 중단한다. 로그는 완료 기록이 아닌 다운로드 요청 기록이다. 이미 브라우저에 표시한 데이터를 개발자 도구로 추출하는 행위까지 방지하는 DLP 기능은 아니다.

배포 시 앱을 중지하고 현재 설정·DB를 백업한 다음, 기존 실행 환경과 `POSTGRES_URI`를 사용하여 `cd backend && python -m alembic upgrade head`를 실행한다. 이후 동일 버전의 프런트엔드와 백엔드로 재시작한다. Native runner는 시작 시 migration을 수행한다. 기존 로그인은 모두 다시 로그인해야 하고 비밀번호 변경일이 없는 계정은 변경 화면으로 이동한다. 실제 운영 DB migration과 재시작은 코드 검증과 별도 단계다. 이 변경에서는 운영 DB를 수정하지 않았다.

검증: `PYTHONPATH=backend python -m pytest backend/tests/test_security_checklist.py backend/tests/test_auth_store.py backend/tests/test_access_boundaries.py backend/tests/test_audit_v2.py backend/tests/test_activity_audit.py backend/tests/test_postgres_foundation.py`. 브라우저 검증은 `frontend`를 임시 로컬 HTTP로 제공하고 `/tests/security-session-browser.html`을 연다. 임시 SQLite 회귀 테스트 72개와 별도 PostgreSQL 12 인스턴스의 migration 및 보안 테스트 24개를 통과했다. 브라우저 검증 11개를 통과했다. 실제 운영 PostgreSQL에는 migration을 실행하지 않았으며 운영 배포 여부와 구분한다.

## 목차

- [SaMD 2등급 인허가 컨텍스트](#samd-2등급-인허가-컨텍스트)
1. [시크릿 관리](#1-시크릿-관리)
2. [비밀번호 저장](#2-비밀번호-저장)
3. [JWT 인증 & 세션](#3-jwt-인증--세션)
4. [계정 생애주기 & 잠금 정책](#4-계정-생애주기--잠금-정책)
5. [RBAC (역할 기반 접근 제어)](#5-rbac-역할-기반-접근-제어)
6. [미디어 URL 서명 (HMAC 티켓)](#6-미디어-url-서명-hmac-티켓)
7. [필드 레벨 암호화](#7-필드-레벨-암호화)
8. [TOTP 2차 인증 (MFA)](#8-totp-2차-인증-mfa)
9. [감사 로그 (Audit Trail)](#9-감사-로그-audit-trail)
10. [네트워크 레이어](#10-네트워크-레이어)
11. [파일 무결성 (SHA-256 체크섬)](#11-파일-무결성-sha-256-체크섬)
12. [성능 최적화와 보안 균형](#12-성능-최적화와-보안-균형)
13. [알려진 한계 & 운영 가이드](#13-알려진-한계--운영-가이드)
- [부록 C — SaMD 2등급 보안 통제 매트릭스](#부록-c--samd-2등급-보안-통제-매트릭스)

---

## SaMD 2등급 인허가 컨텍스트

본 시스템은 **SaMD Class 2 (식약처 의료기기 2등급)** 인허가를 목표로 한다. 이 섹션은 그 분류 근거와 적용 규격을 정리하고, 이후 1~13장이 어떤 규제 통제를 어떻게 구현하는지 한 눈에 보이도록 한다.

### SaMD 등급 분류 (IMDRF + 식약처)

IMDRF 의 "정보 사용 ↔ 의학적 상태 심각도" 매트릭스로 등급이 결정된다:

| 등급 | 정보 사용 | 의학적 상태 심각도 |
| :-: | --- | --- |
| 1 | 임상 관리 정보 제공 | 비중대 |
| **2** | **임상 관리에 정보 제공** | **중대** (암 진단 보조 등) |
| 3 | 임상 관리 의사결정 주도 | 중대 |
| 4 | 임상 관리 의사결정 주도 | 생명 위협 |

본 시스템의 AI 기능 (Quanti HE Tumor/Benign 분류, Quanti PD-L1 CPS/TPS, Quanti IHC HER2 / Allred / Ki-67 score) 은 병리의의 진단을 **보조** 하는 도구이며, 최종 진단·치료 결정은 의사가 수행한다. 따라서 "중대 상태에 정보 제공" → **SaMD 2등급** 으로 분류된다. 같은 사유로 21 CFR Part 11 의 "예측 가능한 임상적 영향" 트리거에 해당하므로 전자기록·전자서명 통제가 필수적이다.

### 적용 규격

| 규격 | 적용 영역 | 본 문서에서 다루는 부분 |
| --- | --- | --- |
| **IEC 62304** | 의료기기 SW 수명주기 | §3 JWT, §4 계정 생애주기, §13 운영 |
| **ISO 14971** | 위험 관리 (해저드 분석) | §11 무결성, §13 알려진 한계 |
| **ISO 13485** | 품질경영시스템 | §4 승인 워크플로 |
| **IEC 62366-1** | 사용성 엔지니어링 | §5 RBAC UI 게이팅 |
| **IEC 81001-5-1** | Health software 보안 | 본 문서 전체 |
| **21 CFR Part 11** | 전자기록·전자서명 (FDA) | §9 감사 로그, §11 무결성 |
| **식약처 사이버보안 가이드라인** | 의료기기 사이버보안 | §1~§11 보안 통제 전반 |
| **IMDRF SaMD N41** | SaMD 임상 평가 | (별도 임상 평가 보고서) |

### SaMD 2등급용 핵심 기술 통제 (현재 구현됨)

| 통제 영역 | 구현 | 근거 §장 |
| --- | --- | :-: |
| 다중 요소 인증 | ID/PW + RFC 6238 TOTP | §8 |
| 세션 관리 | JWT 기본 360분 + Refresh 7일, 단일 로그인 식별자, 30분 무활동 종료 | §3 |
| 계정 잠금·승인 | 5회 실패 30분 잠금, admin 승인 워크플로 | §4 |
| 권한 분리 | RBAC 3단계 (admin/doctor/viewer), 이중 게이팅 | §5 |
| 감사 추적 | HMAC 체인 + 변경 전/후 값 + IP geo | §9 |
| 데이터 무결성 | SHA-256 체크섬 + 검증 API | §11 |
| 민감 데이터 암호화 | bcrypt + pepper, AES-256-GCM, HMAC 미디어 티켓 | §2, §6, §7 |
| 네트워크 통제 | CSRF, Rate Limit, TRUSTED_PROXIES, 디렉토리 탈출 방어 | §10 |

### 본 문서가 다루지 **않는** 인허가 산출물

기술적 보안 통제는 인허가 패키지의 일부일 뿐이다. 식약처 SaMD 2등급 신청 시 **별도 산출물** 이 필요하다:

- [ ] **위험 분석 보고서** (ISO 14971) — 해저드 시나리오, 잔여 위험, 위험 통제 측정
- [ ] **소프트웨어 안전 등급 분류** (IEC 62304 5.3) — Class A/B/C 결정 (AI 보조 진단은 통상 Class B)
- [ ] **사용 적합성 평가 보고서** (IEC 62366-1) — 사용자 인터페이스 위험 분석
- [ ] **임상 평가 보고서** (IMDRF SaMD N41) — AI 모델 성능 검증 (감도/특이도/AUC, 외부 검증 데이터셋)
- [ ] **소프트웨어 V&V 문서** — 단위/통합/시스템 테스트 결과 + 추적성 매트릭스
- [ ] **변경 관리 절차** (ISO 13485) — 모델 업데이트·코드 변경 시 평가·승인 SOP
- [ ] **사이버보안 위험 관리 계획** (IEC 81001-5-1, 식약처) — SBOM, 취약점 모니터링, 사고 대응 절차
- [ ] **사용자 매뉴얼 / IFU** (Instructions for Use) — 의료기기 라벨링 요건, 사용 한계·금기 명시
- [ ] **시판 후 감시 계획 (PMS)** — 시판 후 성능 모니터링·이상사례 수집

기술 충족 항목별 상세 매트릭스는 [docs/COMPLIANCE_STATUS.md](COMPLIANCE_STATUS.md) 의 표를, SaMD 통제 ↔ 본 문서 §장 매핑은 본 문서의 [부록 C](#부록-c--samd-2등급-보안-통제-매트릭스) 를 참조.

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

- **bcrypt** — work factor 12 (~250 ms/해시). 병렬 brute-force 비용이 충분히 높음.
- **pepper** — bcrypt 입력 전 사전 연결. DB만 탈취되고 서버 파일(`.secrets.json`)은 안전한 경우 rainbow table 공격 무력화.
- **저장** — `users.str_hashed_password` 필드. 서버에선 평문을 일절 로깅하지 않음.
- **응답 차단** — 사용자 Repository 조회와 응답 직렬화에서 비밀번호 해시를 제외한다.

### 비밀번호 정책

- 최소 9자, 대/소문자 + 숫자 + 특수문자 포함 (정규식 패턴 검증).
- 아이디는 4~30자 영문/숫자/언더스코어만 허용.
- 계정 열거 방지 — 아이디 존재 여부 / 승인 상태에 따라 메시지를 다르게 반환하지 않고 "아이디 또는 비밀번호가 올바르지 않습니다"로 통일. 승인 상태 검증은 비밀번호 검증 **이후**에 수행.

---

## 3. JWT 인증 & 세션

### 토큰 구성

| 토큰 | 알고리즘 | 수명 | 저장 | 페이로드 |
| ---- | ------- | ---- | ---- | -------- |
| Access | HS256 | 기본 360분 (환경변수 설정) | 매 요청마다 사용자·현재 세션·유휴 시각 검증 | `sub`, `sid`, `role`, `type=access`, `exp`, `iat`, `jti` |
| Refresh | HS256 | 7일 | `sessions` 컬렉션에 원본 저장 | `sub`, `sid`, `type=refresh`, `exp`, `iat`, `jti` |

- `jti` — 매 발급마다 `secrets.token_urlsafe(16)` (replay 추적·취소 시 사용).
- 서명 키: `JWT_SECRET_KEY` (위 시크릿 관리 참조).

### 토큰 전달

- **API 요청**: `Authorization: Bearer <access>` 헤더만 허용.
- **`?token=` query parameter 금지** — 과거엔 img.src 호환을 위해 허용했으나 JWT가 브라우저 히스토리/프록시 로그/Referer에 남아 계정 탈취 위험. 제거됨.
- **미디어(img.src)** — JWT 대신 **단기 HMAC 티켓**(`?mt=...`) 사용. 아래 6번 참조.

### Refresh 로테이션 + 재사용 탐지

`POST /api/auth/refresh`는 DB 의 **원자적 CAS** 연산으로 경쟁 상태를 처리한다:

1. `(str_refresh_token, bool_is_revoked=false)` 조건으로 `bool_is_revoked=true` + `str_replaced_by=<새 토큰>` 기록.
2. CAS 승리자: 새 세션 insert 후 새 토큰 반환.
3. CAS 패자(이미 revoked): `dt_rotated_at` 과 현재 시각의 차가 **5분 grace window** 이내면 → `str_replaced_by` 포인터를 따라가 replacement 세션 토큰을 반환(모바일 탭 suspend/재개 대응).
4. grace window를 초과한 이전 rotation 토큰은 해당 요청을 거부한다. 현재 로그인 식별자가 다른 토큰은 rotation 처리 전에 거부한다. 현재 로그인 식별자의 미등록 refresh 토큰 사용은 전체 세션 폐기 대상으로 처리한다.

### 로그아웃

`POST /api/auth/logout`은 현재 사용자의 refresh 세션을 폐기하고 활성 로그인 식별자를 비운다. 기존 access JWT와 미디어 티켓도 이후 요청에서 거부한다. 새 로그인 시 이전 로그인 식별자를 교체하므로 동일 계정의 이전 접속은 계속 사용할 수 없다.

### 세션 TTL

`sessions.dt_expires_at` 인덱스를 사용해 만료 세션을 조회·정리한다.

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
- 5회 초과 시 `bool_is_locked=true` + `dt_locked_until = now + 30분`.
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

사용자 역할은 `admin` / `doctor` / `viewer` 세 단계.

| 역할 | 관리자 페이지 | AI 분석 | Annotation 저장 | 폴더 설정 | 슬라이드 조회 |
| ---- | :-----------: | :-----: | :-------------: | :-------: | :-----------: |
| `admin`  | O | O | O | O | O |
| `doctor` | X | O | O | O | O |
| `viewer` | X | X | X | X | O |

### 의존성 계층

- **사용자 인증 의존성** — 모든 보호된 엔드포인트의 기반. 활성/잠금/승인 상태 재검증. 30초 TTL 인메모리 캐시로 대량 요청 시 DB 부하 방지.
- **역할 제한 의존성** — 특정 역할만 통과 (예: 관리자 API).
- **viewer 차단 의존성** — viewer를 제외한 전부. annotation 저장, 폴더 설정, AI 분석 엔드포인트에 적용.

### 이중 방어

- **서버(소스 진실)**: 역할 제한 의존성으로 403 반환.
- **프론트엔드 게이팅**: viewer 계정으로 로그인 시 AI/annotation 버튼을 비활성화하고 배너 표시. 서버가 거절해도 사용자가 "깨진 버튼"을 누르지 않도록 UX 보호.
- **"technician" role 폐기** — 기존 사용자는 startup 마이그레이션에서 `viewer`로 downgrade(권한 확대 금지 원칙).

### DB 미연결 Fallback

PostgreSQL 연결이 끊기면 영구 인증·세션 기능이 정상 동작하지 않는다. 운영에서는 `/api/health`를 감시하고 데이터베이스 장애 시 트래픽을 차단하는 fail-closed 구성을 사용한다.

---

## 6. 미디어 URL 서명 (HMAC 티켓)

### 문제 배경

타일/썸네일/프리뷰는 `<img src>`로 로드되므로 `Authorization` 헤더를 붙일 수 없다. 과거에는 `?token=<JWT>` fallback을 허용했으나:

- JWT가 브라우저 히스토리·Referer·프록시 로그·CDN 캐시 키에 노출 → 계정 탈취 시나리오.
- 7일 유효 Refresh 자격의 full-power 토큰이 이미지 URL에 실려 감.

### 해결

1. 로그인 직후 `/api/auth/media-ticket`에서 **단기 HMAC 티켓** 발급.
2. 프론트는 `<img src="/api/tiles/...?mt=<ticket>">`로 요청.
3. 서버는 미디어 인증 의존성에서 티켓 검증 후 해당 사용자로 처리.
4. **API 엔드포인트는 절대 티켓을 받지 않음** — 미디어 엔드포인트(tiles, ai-media, slides-media)에만 주입되어 있어 스코프가 분리되어 있다.

### 구현 세부

- **포맷**: `<b64url(user_id|exp)>.<b64url(hmac_sha256)>`
- **서명 키 파생**: `SHA256("media-ticket-v1|" || JWT_SECRET_KEY)` — 도메인 분리를 위해 JWT 키를 그대로 쓰지 않고 컨텍스트 문자열로 해시. `MEDIA_SIGNING_KEY` 환경변수가 있으면 그것이 우선.
- **TTL**: 600초(10분). 누출 시 블래스트 반경 = 10분 x 미디어 엔드포인트만.
- **검증**: 상수 시간(timing-safe) 비교로 서명 검증. 만료 확인은 `exp` 필드.
- **스테이트리스**: DB 조회 없음 — 서명만으로 통과.

---

## 7. 필드 레벨 암호화

- **알고리즘**: AES-256-GCM — 암호화 + 인증(tag) 동시 제공.
- **키**: `FIELD_ENCRYPTION_KEY`에서 base64url 디코드 후 32바이트 정렬.
- **Nonce**: 매 암호화마다 OS 난수원에서 12 바이트(96 비트) 새 값. **nonce 재사용은 GCM 보안을 파괴하므로 절대 재사용하지 않음.**
- **저장 형식**: `base64url(nonce || ciphertext || tag)` — 단일 문자열.
- **현재 적용 필드**: `users.str_totp_secret_enc` (TOTP base32 시드). 평문 시드는 메모리 외부로 절대 나가지 않음.

### 한계

- 검색 불가(AES-GCM은 비결정적) — 인덱스 검색이 필요한 필드는 암호화 대신 해시 별도 컬럼 + 원본 암호화 조합이 필요.
- 키 유출 시 과거 데이터 전부 복호화 가능 — 정기 roll-over 계획 권장(envelope encryption으로 업그레이드 여지).

---

## 8. TOTP 2차 인증 (MFA)

RFC 6238 TOTP — 외부 라이브러리 의존 없이 자체 구현 (HMAC-SHA1, 6자리, 30초 step).

### 활성화 플로우

1. 로그인된 사용자가 `POST /api/auth/mfa/setup` 호출 → 서버가 16바이트 랜덤 시드 생성 + `users.str_totp_secret_enc` 에 AES-GCM 암호화 저장. 이 시점엔 `bool_mfa_enabled=false` 라 로그인 영향 없음.
2. 응답으로 시드 + `otpauth://` URI 반환. 사용자는 Google Authenticator 등에 등록.
3. `POST /api/auth/mfa/verify {str_totp_code}` — 첫 코드 검증 통과 시 `bool_mfa_enabled=true`.
4. 이후 `/login` 응답이 분기:
   - 평문 비밀번호만 맞고 `str_totp_code` 가 비어 있으면 → `202 {bool_mfa_required: true}` (토큰 미발급)
   - 코드까지 맞으면 → 일반 토큰 응답
5. `POST /api/auth/mfa/disable` — 활성 세션에서만 호출 가능. `bool_mfa_enabled=false` + 시드 폐기.

### 검증 상세

- TOTP 검증 시 현재 step ± 1 step 허용 → 클라이언트 시계 ±30초 오차 흡수.
- 코드 비교는 상수 시간(timing-safe) 비교.
- TOTP 실패 시 `user.mfa_failed` 감사 로그 기록.

### 위협 모델

- **시드 유출 (DB 탈취)**: 시드는 AES-256-GCM 암호화 상태로 저장 → `FIELD_ENCRYPTION_KEY` 까지 함께 유출돼야 의미 있음.
- **시드 유출 (백업/덤프)**: 디스크 백업에 `.secrets.json` 이 포함되지 않으면 복호화 불가 — 백업 정책에 시크릿 분리 필수.
- **시간 동기화 공격**: ±30초 window 만 허용. 더 넓히면 brute-force 위험 (10⁶ 코드 → window 확대 시 추측 공격 표면 증가).

---

## 9. 감사 로그 (Audit Trail)

### 기록 원칙

- 병원 환경 기준 **최소 5년 보존** (규정 준수).
- **불변** — 앱 로직에 update/delete가 존재하지 않음. PostgreSQL 권한 수준에서도 감사 기록의 update/delete를 제한하는 역할 분리를 권장.
- **보안 이벤트 + 행위 이벤트 모두 기록**.

### 기록 대상 actions

| action | 트리거 |
| ------ | ------ |
| `user.register` | 회원가입 |
| `user.login_success` | 로그인 성공 (+ geo enrichment) |
| `user.login_failed` | 비밀번호 오류 (실패 횟수 포함) |
| `user.login_locked` | 잠금 상태 로그인 시도 |
| `user.login_pending` / `user.login_rejected` | 승인 전/거부된 계정의 로그인 시도 |
| `user.logout` | 로그아웃 — revoke 된 세션 수 포함 |
| `user.password_changed` | 비밀번호 변경 — 모든 세션 revoke |
| `user.mfa_enabled` / `user.mfa_disabled` | TOTP MFA 활성/비활성 |
| `user.mfa_failed` | TOTP 코드 검증 실패 |
| `security.token_reuse_detected` | 알 수 없는 refresh token 재사용 — 사용자 전체 세션 revoke |
| `security.refresh_stale_rotation` | grace window 지난 revoked 토큰 재요청 — 단건 401 |
| `admin.user_approved` / `admin.user_rejected` | 관리자 승인/거부 (before/after 기록) |
| `admin.user_created` | 관리자 사용자 생성 |
| `admin.user_updated` | 관리자 사용자 수정 (변경 필드별 before/after) |
| `admin.user_deleted` | 관리자 사용자 삭제 (삭제 전 스냅샷 보관) |
| `admin.role_changed` | 역할 변경 (before/after) |
| `admin.user_activated/deactivated` | 활성 토글 (before/after) |
| `admin.user_unlocked` | 잠금 해제 (before/after) |
| `slide.view` | 슬라이드 열기 — rel_path, filename 포함 |
| `ai.analyze` | AI 4종 엔드포인트 호출 — model, variant, task_id 포함 |

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

클라이언트 IP 추출은 두 단계로 동작:

1. TCP peer 가 환경변수 `TRUSTED_PROXIES` 화이트리스트에 들어 있으면 → `X-Forwarded-For` (첫 항목) → `X-Real-IP` 헤더를 신뢰.
2. 그 외에는 헤더를 무시하고 peer 주소만 반환.

기본(빈 환경변수) 동작이 안전 측. 외부에 직접 노출된 서버에서 위조 헤더로 Rate Limit 우회·감사 로그 IP 위조를 차단한다. 리버스 프록시 뒤에 두려면 프록시 IP 만 정확히 등록할 것. 같은 추출 로직은 감사 로그 모듈과 Rate Limit 미들웨어 양쪽에서 공유한다.

### Geo Enrichment

로그인 성공 직후 fire-and-forget 비동기 태스크로 IP 지리정보를 추가한다:

- **외부 API**: `ip-api.com` (free tier, 45 req/min, no key required).
- **캐시**: `ip_geo_cache` 컬렉션에 30일 TTL — IP당 1회만 외부 호출.
- **사설 IP 스킵**: 127./10./192.168./172.16-31./169.254./::1/fe80:/fc00:/fd00: — 외부 API 호출 없이 즉시 반환.
- **비블로킹**: 응답 경로를 차단하지 않음. 실패해도 로그는 남고 geo 필드만 비어있게 됨.

---

## 10. 네트워크 레이어

### CSRF 방어

Pure ASGI 미들웨어로 구현. 상태 변경 요청(POST/PUT/PATCH/DELETE)에 `X-Requested-With` 헤더가 있는지 검증한다. ASGI scope 의 헤더만 직접 읽는 구조라 body 버퍼링 오버헤드가 없다.

- 안전한 메서드(GET/HEAD/OPTIONS)는 검증 생략
- 인증 경로(`/api/auth/login`, `/api/auth/register`, `/api/auth/refresh`, `/api/health`)는 화이트리스트 제외
- 미디어 경로(tiles, 썸네일 등 GET 요청)는 해당 없음

### Rate Limiting

Pure ASGI 미들웨어로 구현. IP별 **고정 윈도우** 카운터 방식 (O(1) 판정, 메모리 최소):

- **로그인 엔드포인트** (`/api/auth/login`, `/api/auth/register`): 10회/5분 (brute-force 방어)
- **일반 API**: 200회/분
- **공개/정적 경로 반복 404**: 기본 30회/분. 한도 도달 후 해당 IP의 비-API 요청에 429 반환
- **명시적 IP/CIDR 차단**: 모든 예외 경로보다 먼저 403 반환. `BLOCKED_IPS`로 목록 추가
- 인메모리 카운터 (IP → 윈도우 시작 시각 + 카운트). 5,000 요청마다 만료된 윈도우 정리.
- 순수 ASGI 구조라 body 버퍼링 없음.
- **타일 / 썸네일 / virtual-stain 미디어**는 면제 — 인증(media ticket)으로 보호되며 뷰어 체감에 직결.

> 윈도우 경계에 burst (10초 안에 윈도우 두 번에 걸쳐 2배 트래픽 가능) 가능성이 있으나 단일 프로세스 보안용으론 충분. 멀티 프로세스 배포 시 외부 store(Redis 등) 필요.

### TRUSTED_PROXIES 화이트리스트

`X-Forwarded-For` / `X-Real-IP` 헤더는 **위조 가능**하므로 직접 노출된 서버에서 그대로 신뢰하면 rate limit 우회·감사 로그 IP 위조가 가능하다. 정책:

- 환경변수 `TRUSTED_PROXIES=10.0.0.5,127.0.0.1` 에 등록된 peer IP 에서 들어오는 요청만 헤더를 신뢰.
- 기본(빈 값)은 헤더 무시 — TCP peer 주소만 사용.
- 감사 로그 모듈과 Rate Limit 미들웨어가 동일한 추출 로직을 공유.

### CORS

환경변수 `CORS_ORIGINS`로 허용 origin 지정. 비어 있으면 same-origin 전용(StaticFiles 서빙이므로 CORS 불필요).

### 정적 파일 캐싱

`.js/.html/.css/.mjs`에 `Cache-Control: no-cache, must-revalidate`를 강제. ETag는 유지되어 304 가능. API 계약 변경 후 사용자가 "하드 리프레시해도 안 되는" 상황을 방지한다. 보안상 장점: 취약점 패치된 JS가 즉시 반영됨.

### 미설정 항목

- **CSP / HSTS / X-Frame-Options**: 현재 미설정. 리버스 프록시 레이어에서 추가 권장.
- **업로드 한계**: `MAX_UPLOAD_BYTES = 20 GB` (환경변수로 조정). WSI 파일 크기 고려값. 청크 조립 전 합계 크기를 사전 검증해 초과 시 즉시 413.

---

## 11. 파일 무결성 (SHA-256 체크섬)

### 업로드 시 계산

청크 조립 단계에서 **스트리밍으로** SHA-256 을 계산해 `slides.str_sha256` 에 저장한다. 메모리에 전체 파일을 올리지 않고 8 KB 블록 단위로 누적 → 20 GB 슬라이드도 일정 메모리.

- 신규 업로드: 청크 조립과 동시에 계산.
- 기존 파일이 이미 존재하지만 DB 에 체크섬이 없는 경우: `upload/complete` 단계에서 한 번 더 디스크 전체 read 로 계산.

### 검증 API

`GET /api/slides/{slide_id}/verify-integrity` — 디스크 파일을 다시 읽어 재계산한 hash 와 DB 저장값을 비교.

- 저장값이 비어 있으면 이번 호출에서 저장하고 `bool_integrity_ok=true`.
- 일치하지 않으면 `bool_integrity_ok=false` 와 함께 두 값을 모두 반환 → 운영자가 백업과 비교해 복구 결정.
- 21 CFR Part 11 11.10(c) (전자기록 진위·정확성·신뢰성 보장) 의 기술적 근거.

### 파일명·경로 보안

업로드/이동/삭제 모든 경로에서 두 검증 헬퍼가 적용된다:

- **경로 검증** — 업로드 루트의 하위 경로인지 표준 라이브러리의 path-relative 검사로 강제. unicode normalization / case 차이 / prefix 충돌까지 안전.
- **파일명 검증** — `/`, `\`, `..`, NUL, dotfile, 빈 문자열 거부. dotfile 거부로 `.env`/`.secrets.json` 같은 숨김 파일 노출 시도 차단.

---

## 12. 성능 최적화와 보안 균형

보안 미들웨어와 인증 로직이 타일 서빙 등 대량 요청에 미치는 성능 영향을 최소화하기 위해 다음 최적화를 적용했다:

### Pure ASGI 미들웨어

CSRF, Rate Limiting 미들웨어는 ASGI 프로토콜 레벨에서 직접 구현되어, 일반적인 미들웨어 베이스 클래스가 동반하는 request body 메모리 버퍼링이 없다. 타일 요청처럼 body가 없는 GET 트래픽이 대량으로 들어와도 인증·권한 검증 외 추가 오버헤드를 피한다.

### 사용자 정보 인메모리 캐시

인증·미디어 의존성은 인증된 사용자 정보를 30초 TTL 메모리 캐시에 보관한다. 한 화면에 수십~수백 개의 타일 요청이 발생하는 WSI 뷰어 특성상, 모든 요청마다 DB 조회를 하면 부하가 크다.

- 캐시 키: user_id 문자열
- TTL: 30초 (비활성화/잠금 반영 지연 허용 범위)
- 무효화: 관리자가 사용자 정보를 변경(승인/거부/수정/삭제/역할변경/활성토글/잠금해제)하면 해당 사용자의 캐시를 즉시 무효화

### 감사 로그 HMAC 체인 캐시

감사 로그의 HMAC 체인은 이전 로그의 HMAC을 참조해야 하므로 원래 매번 DB에서 마지막 로그를 조회해야 한다. 이를 메모리 캐시로 대체하여 앱 시작 후 첫 호출 시만 DB 조회, 이후에는 메모리에서 체인을 이어간다.

### 대시보드 통계 최적화

- 디스크 사용량 계산: 동기 walk 를 스레드 풀에서 실행 + 60초 캐시
- DB 집계: 9개 이상의 카운트 쿼리를 단일 aggregation 파이프라인으로 통합

---

## 13. 알려진 한계 & 운영 가이드

### 반드시 운영 배포 전 조치할 것

- [ ] 원격 `POSTGRES_URI`에 전용 계정 + TLS 설정
- [ ] `JWT_SECRET_KEY` / `FIELD_ENCRYPTION_KEY` / `AUTH_PEPPER`를 secret manager에서 환경변수로 주입
- [ ] CORS `allow_origins`를 실제 프론트엔드 도메인으로 제한
- [ ] 리버스 프록시에서 TLS 종료 + HSTS + CSP 헤더 추가
- [ ] `X-Forwarded-For` 신뢰 범위 확정 (내부망 프록시만)
- [ ] PostgreSQL `audit_logs` 테이블은 append-only 권한의 별도 역할로 분리
- [ ] 첫 번째 가입자가 admin이 되는 부트스트랩 규칙을 악용당하지 않도록, 첫 배포 직후 즉시 관리자 계정을 만들고 회원가입 엔드포인트를 보호
- [ ] 정기 백업: `users` + `audit_logs` + `.secrets.json`

### 설계상 한계

- **DB 미연결 시 인증 차단** — 인증 저장소가 연결되지 않으면 503을 반환한다. 로그인 세션 상태는 요청마다 DB에서 확인한다.
- **AES-GCM 필드 암호화는 검색 불가** — 암호화된 필드로는 쿼리할 수 없음. 필요 시 HMAC 인덱스 컬럼 추가.
- **Refresh rotation grace window 5분** — 너무 길면 reuse 탐지가 둔해지고, 너무 짧으면 모바일 백그라운드 탭이 깨어날 때 세션 무효화 경험. 현재 값은 경험적 절충.
- **요청별 사용자 조회** — access JWT와 미디어 티켓에 대한 계정·세션·유휴 시각 검증은 캐시를 우회한다. 타일 요청이 많은 환경에서는 DB 풀과 지연 시간을 점검해야 한다.
- **WebSocket 채널 없음** — 현재 모든 통신이 HTTP. 실시간 알림이 필요해지면 JWT over WS 설계 추가 필요.

### 취약점 대응 절차

1. **비밀번호 유출 의심**: 해당 사용자 강제 비밀번호 리셋 + 세션 revoke.
2. **JWT 시크릿 유출 의심**: `JWT_SECRET_KEY` 교체 → 모든 기존 토큰 무효화(전체 강제 재로그인).
3. **필드 암호화 키 유출 의심**: `FIELD_ENCRYPTION_KEY` 교체 + 과거 데이터 재암호화 스크립트 필요.
4. **관리자 계정 탈취**: admin 역할 사용자 전체 비밀번호 리셋 + `audit_logs`에서 해당 기간 행위 포렌식.

---

## 부록 A — 보안 아키텍처 레이어

요청은 아래 레이어를 위에서 아래로 통과한다. 각 레이어는 독립적으로 구현되어 한 레이어가 우회되어도 다음 레이어가 방어를 이어가는 defense-in-depth 구조.

```text
┌─────────────────────────────────────────────────────────────┐
│ 1. 네트워크 레이어 (리버스 프록시 — 운영 배포)               │
│    TLS 종료 / HSTS / CSP / X-Forwarded-For 정규화            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. ASGI 미들웨어 — Pure ASGI (body 버퍼링 없음)              │
│    ├ CSRF 검증 (X-Requested-With 헤더 강제)                  │
│    └ Rate Limiting (IP별 고정 윈도우, TRUSTED_PROXIES)       │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. 인증·인가 레이어                                           │
│    ├ JWT 검증 (Access 헤더 / 미디어는 HMAC 티켓)              │
│    ├ 사용자 상태 검증 (활성/잠금/승인) + 30s 메모리 캐시       │
│    ├ RBAC 의존성 (역할 제한 / viewer 차단)                   │
│    └ 2단계 (TOTP MFA, 사용자별 활성)                          │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. 입력 검증 레이어                                           │
│    ├ Pydantic 스키마 (Field 제약 + 정규식)                    │
│    ├ 경로 / 파일명 검증 헬퍼 (디렉토리 탈출, dotfile 차단)     │
│    └ 업로드 크기 사전 검증 (조립 전 합계 ≤ 상한)              │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. 도메인 로직 (라우터 / 서비스)                              │
│    인증·사용자 관리·슬라이드·타일·AI 분석                     │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. 영속화 레이어                                              │
│    ├ 비밀번호 (bcrypt cost=12 + pepper)                      │
│    ├ 민감 필드 (AES-256-GCM, 매 암호화 새 nonce)             │
│    ├ 파일 무결성 (SHA-256, 업로드 스트리밍 계산)             │
│    └ 감사 로그 (HMAC 체인, append-only 권장)                 │
└─────────────────────────────────────────────────────────────┘

[직교 통제]
 ├ 시크릿 관리 — 환경변수 → 파일(0600) → 자동 생성
 ├ 미디어 URL 서명 — <img src> 전용 단기 HMAC 티켓 (10분)
 └ Geo enrichment — 비블로킹 fire-and-forget, 30일 TTL 캐시
```

## 부록 B — 체크리스트 (배포 직전)

```
[ ] 원격 POSTGRES_URI 에 전용 계정 + TLS
[ ] JWT_SECRET_KEY / FIELD_ENCRYPTION_KEY / AUTH_PEPPER 환경변수 주입
[ ] .secrets.json 권한 0600 + 백업
[ ] CORS allow_origins 화이트리스트
[ ] 리버스 프록시 TLS + HSTS + CSP
[ ] X-Forwarded-For 신뢰 범위 확정
[ ] audit_logs 전용 append-only DB 유저
[ ] 첫 admin 생성 직후 /register 접근 제한
[ ] PostgreSQL 자동 백업 및 복구 검증 스케줄
[ ] 정기 보안 패치 (FastAPI / bcrypt / cryptography / python-jose)
```

## 부록 C — SaMD 2등급 보안 통제 매트릭스

식약처 의료기기 사이버보안 가이드라인 + IEC 81001-5-1 + 21 CFR Part 11 의 통제 항목과 본 문서 §장 / 구현 레이어를 매핑한 표. 인허가 심사 대응 시 이 표를 통제 ↔ 산출물 추적성 매트릭스로 활용한다. (구현 레이어는 부록 A 의 6 레이어 + 직교 통제를 가리킴.)

| # | 통제 항목 | 규격 근거 | §장 | 구현 레이어 | 상태 |
| :-: | --- | --- | :-: | --- | :-: |
| C-01 | 사용자 식별·인증 | IEC 81001-5-1, 식약처 §4.1, 21 CFR 11.10(d) | §3, §4 | 인증·인가 레이어 | ✅ |
| C-02 | 다중 요소 인증 (MFA) | IEC 81001-5-1, 식약처 §4.1.3 | §8 | 인증·인가 레이어 (TOTP) | ✅ |
| C-03 | 비밀번호 정책 강제 | 식약처 §4.1.2 | §2 | 입력 검증 레이어 (정규식) | ✅ |
| C-04 | 계정 잠금 (brute-force 방어) | 식약처 §4.1.4 | §4 | 인증·인가 레이어 (잠금 카운터) | ✅ |
| C-05 | 세션 관리 (만료·재인증) | IEC 81001-5-1, 21 CFR 11.10(g) | §3 | 인증·인가 레이어 (JWT 15분 + Refresh CAS rotation) | ✅ |
| C-06 | 권한 분리 (RBAC) | IEC 81001-5-1, 식약처 §4.2 | §5 | 인증·인가 레이어 (역할 의존성) | ✅ |
| C-07 | 승인 워크플로 | ISO 13485 7.3, 식약처 §4.2.2 | §4 | 도메인 로직 (사용자 관리) | ✅ |
| C-08 | 감사 로그 (보안 이벤트) | 21 CFR 11.10(e), 식약처 §5.1 | §9 | 영속화 레이어 (감사 모듈) | ✅ |
| C-09 | 변경 전/후 값 기록 | 21 CFR 11.10(e) | §9 | 도메인 로직 (사용자 관리) + 감사 모듈 | ✅ |
| C-10 | 로그 변조 방지 (HMAC 체인) | 21 CFR 11.10(e), 식약처 §5.2 | §9 | 영속화 레이어 (HMAC 체인) | ✅ |
| C-11 | 로그 무결성 검증 API | 21 CFR 11.10(e) | §9 | 도메인 로직 (체인 검증 엔드포인트) | ✅ |
| C-12 | 데이터 무결성 (체크섬) | 21 CFR 11.10(c), IEC 62304 | §11 | 영속화 레이어 (SHA-256 스트리밍 계산) | ✅ |
| C-13 | 무결성 재검증 API | 21 CFR 11.10(c) | §11 | 도메인 로직 (verify-integrity 엔드포인트) | ✅ |
| C-14 | 민감 데이터 at-rest 암호화 | IEC 81001-5-1, 식약처 §6.1 | §7 | 영속화 레이어 (AES-256-GCM, TOTP 시드) | ✅ (부분) |
| C-15 | 비밀번호 해싱 + salt + pepper | IEC 81001-5-1, 식약처 §4.1.5 | §2 | 영속화 레이어 (bcrypt cost=12 + pepper) | ✅ |
| C-16 | 시크릿 외부 주입 / 영속화 | 식약처 §6.2 | §1 | 직교 통제 (시크릿 관리, 0600 권한) | ✅ |
| C-17 | 전송 중 암호화 (TLS) | IEC 81001-5-1, 식약처 §6.1 | §10 | 네트워크 레이어 (리버스 프록시 종료) | ⚠ 운영 |
| C-18 | CSRF 방어 | OWASP, 식약처 §4.3 | §10 | ASGI 미들웨어 (X-Requested-With 검증) | ✅ |
| C-19 | Rate Limiting (DoS 완화) | IEC 62443-3-3 SR 7.1, 식약처 §4.4 | §10 | ASGI 미들웨어 (고정 윈도우) | ✅ |
| C-20 | 미디어 URL 단기 서명 | OWASP, 식약처 §6.3 | §6 | 직교 통제 (HMAC-SHA256 10분 TTL) | ✅ |
| C-21 | 디렉토리 탈출 방어 | OWASP, IEC 62304 | §11 | 입력 검증 레이어 (경로/파일명 헬퍼) | ✅ |
| C-22 | IP 헤더 위조 방어 | 식약처 §5.3 | §10, §9 | ASGI 미들웨어 + 감사 모듈 (TRUSTED_PROXIES) | ✅ |
| C-23 | 입력 검증 (스키마) | IEC 62304, OWASP | §3, §4 | 입력 검증 레이어 (Pydantic + 정규식) | ✅ |
| C-24 | 비활성·역할변경 즉시 반영 | 식약처 §4.2.3 | §5 | 인증·인가 레이어 (캐시 무효화 훅) | ✅ |
| C-25 | 비밀번호 변경 시 세션 폐기 | IEC 81001-5-1 | §4 | 도메인 로직 (비밀번호 변경 → 세션 revoke) | ✅ |
| C-26 | 토큰 재사용 탐지 | OWASP, 식약처 §4.1.6 | §3 | 인증·인가 레이어 (refresh CAS reuse 분기) | ✅ |
| C-27 | 보안 이벤트 알림 | 식약처 §5.4 | — | (미구현 — 외부 SIEM 연동 권장) | ❌ |
| C-28 | 자동 로그아웃 (idle) | IEC 81001-5-1 | §3 | 인증·인가 레이어 (서버 30분 무활동 검증 + 브라우저 입력 감지) | ✅ |
| C-29 | 보안 헤더 (HSTS/CSP/XFO) | OWASP | §10 | (네트워크 레이어 — 리버스 프록시에서 추가 필요) | ❌ |
| C-30 | 사이버보안 사고 대응 절차 | 식약처 §7, IEC 81001-5-1 | §13 | 본 문서 §13 "취약점 대응 절차" | ⚠ 문서화 |
| C-31 | SBOM (Software Bill of Materials) | 식약처 §8, FDA 가이드 | — | 의존성 명세 + pip-audit 자동화 권장 | ⚠ 운영 |
| C-32 | 시판 후 보안 모니터링 (PMS) | 식약처 §9 | — | (인허가 시 별도 PMS 계획서 필요) | ❌ |

**범례**: ✅ 충족 / ⚠ 부분 충족 (운영·문서화 보완 필요) / ❌ 미충족 (별도 산출물·인프라 필요)

### 인허가 심사 대응 팁

- **추적성 매트릭스**: 위 표의 각 통제 (C-01 ~ C-32) 가 위험 분석 보고서 (ISO 14971) 의 어떤 해저드 / 잔여 위험에 대응하는지 매핑한 별도 표를 작성한다.
- **시험 증적**: ✅ 항목들은 구현 레이어 명시만으론 부족하고 **시험 케이스 (V&V) 증적** 이 필요하다. 인증·잠금·HMAC 체인 검증·SHA-256 검증 등은 자동화 테스트 작성 우선순위가 높다 ([COMPLIANCE_STATUS.md](COMPLIANCE_STATUS.md) §5 참조).
- **운영 통제**: ⚠ 표시된 항목 (TLS, SBOM, 사이버보안 사고 대응 절차) 은 코드가 아닌 **운영 절차서·SOP** 로 충족해야 한다.
- **C-27 / C-29 / C-32**: 인허가 신청 전에 외부 SIEM 연동·리버스 프록시 보안 헤더·시판 후 모니터링 계획을 보강해야 한다.
