# MeDIAuto Studio SaaS — 기술 규제 충족 현황

> 최종 업데이트: 2026-04-16
>
> 대상 규격: IEC 62304 (의료기기 SW), ISO 14971 (위험관리), 21 CFR Part 11 (전자기록),
> IEC 62443 (산업 사이버보안), ISO 13485 (품질경영시스템)

---

## 범례

| 상태 | 의미 |
|------|------|
| **충족** | 코드 레벨에서 구현 완료 |
| **부분 충족** | 핵심 기능 구현됨, 일부 보완 필요 |
| **미충족** | 아직 구현되지 않음 |

---

## 1. 접근 제어 및 인증

| 항목 | 규격 근거 | 상태 | 구현 위치 | 비고 |
|------|-----------|------|-----------|------|
| 사용자 인증 (ID/PW) | 21 CFR 11.10(d) | **충족** | `backend/app/routers/auth.py` | bcrypt 해싱, 로그인 실패 잠금 |
| 역할 기반 접근 제어 (RBAC) | 21 CFR 11.10(d), IEC 62443 | **충족** | `backend/app/auth.py` | admin / doctor / viewer 3단계 |
| 2차 인증 (MFA/TOTP) | IEC 62443-3-3 SR 1.1 | **충족** | `backend/app/totp.py`, `auth.py` | RFC 6236 TOTP, AES-256-GCM 암호화 저장 |
| 세션 관리 (JWT + Refresh) | 21 CFR 11.10(g) | **충족** | `backend/app/routers/auth.py` | Access 30분 + Refresh 7일, 세션 폐기 지원 |
| 계정 잠금 정책 | IEC 62443 | **충족** | `backend/app/routers/auth.py` | 5회 실패 시 15분 잠금 |
| 비밀번호 복잡도 강제 | IEC 62443-3-3 SR 1.7 | **충족** | `backend/app/routers/users.py` | 대소문자+숫자+특수문자 8자 이상 |
| 승인 워크플로우 | ISO 13485 7.3 | **충족** | `backend/app/routers/users.py` | pending → approved/rejected, admin 승인 필요 |

## 2. 감사 추적 (Audit Trail)

| 항목 | 규격 근거 | 상태 | 구현 위치 | 비고 |
|------|-----------|------|-----------|------|
| 감사 로그 기록 | 21 CFR 11.10(e) | **충족** | `backend/app/audit.py` | 로그인, 슬라이드 조회, AI 분석, 관리자 작업 기록 |
| 변경 전/후 값 기록 | 21 CFR 11.10(e) | **충족** | `backend/app/routers/users.py` | dict_before/dict_after로 승인, 거부, 역할변경, 수정, 삭제, 활성화, 잠금해제 전후 값 기록 |
| 로그 변조 감지 (HMAC 체인) | 21 CFR 11.10(e) | **충족** | `backend/app/audit.py` | SHA-256 HMAC, 이전 로그 HMAC 참조 체인 |
| HMAC 체인 검증 API | 21 CFR 11.10(e) | **충족** | `backend/app/routers/users.py` | `/audit-logs/verify-chain` 엔드포인트 |
| 로그 불변성 (수정/삭제 방지) | 21 CFR 11.10(e) | **부분 충족** | `backend/app/audit.py` | Insert-only 패턴, DB 레벨 write protection 미적용 |
| 로그 보관 정책 (5년) | 21 CFR 11.10(e) | **부분 충족** | MongoDB | TTL 없음 (영구 보관), 별도 아카이브/백업 정책 필요 |

## 3. 데이터 무결성

| 항목 | 규격 근거 | 상태 | 구현 위치 | 비고 |
|------|-----------|------|-----------|------|
| 파일 체크섬 (SHA-256) | 21 CFR 11.10(c), IEC 62304 | **충족** | `backend/app/routers/slides.py` | 업로드 시 SHA-256 계산 및 DB 저장 |
| 무결성 검증 API | 21 CFR 11.10(c) | **충족** | `backend/app/routers/slides.py` | `/{slide_id}/verify-integrity` 엔드포인트 |
| 민감 데이터 암호화 (at-rest) | IEC 62443-3-3 SR 3.4 | **부분 충족** | `backend/app/encryption.py` | TOTP 비밀키 AES-256-GCM 암호화, DB 전체 암호화는 인프라 레벨 |
| 전송 중 암호화 (TLS) | IEC 62443-3-3 SR 3.1 | **부분 충족** | `backend/app/database.py` | TLS 옵션 존재 (현재 False), 프로덕션 배포 시 활성화 필요 |

## 4. 네트워크 보안

| 항목 | 규격 근거 | 상태 | 구현 위치 | 비고 |
|------|-----------|------|-----------|------|
| CORS 제한 | IEC 62443, OWASP | **충족** | `backend/main.py`, `config.py` | 환경변수 기반 화이트리스트 (와일드카드 제거) |
| CSRF 방어 | OWASP, IEC 62443 | **충족** | `backend/app/csrf.py` | X-Requested-With 헤더 검증 미들웨어 |
| Rate Limiting | IEC 62443-3-3 SR 7.1 | **충족** | `backend/app/rate_limit.py` | IP별 슬라이딩 윈도우 (로그인 10/5분, API 200/분) |
| HTTP 보안 헤더 | OWASP | **미충족** | — | X-Content-Type-Options, X-Frame-Options, CSP 등 미설정 |
| API 입력 검증 | IEC 62304, OWASP | **충족** | 각 라우터 Pydantic 모델 | Field 제약조건, 정규식 패턴 검증 |

## 5. 소프트웨어 수명주기 (IEC 62304)

| 항목 | 규격 근거 | 상태 | 구현 위치 | 비고 |
|------|-----------|------|-----------|------|
| 에러 핸들링 | IEC 62304 5.5 | **부분 충족** | 각 라우터 | HTTPException 사용, 글로벌 예외 핸들러 미구현 |
| 의존성 관리 | IEC 62304 8.1 | **부분 충족** | `backend/requirements.txt` | 패키지 목록 존재, 버전 고정(pinning) 확인 필요 |
| 자동화 테스트 | IEC 62304 5.7 | **미충족** | — | 단위/통합 테스트 미작성 |
| CI/CD 파이프라인 | IEC 62304 | **미충족** | — | 자동 빌드/테스트/배포 파이프라인 없음 |

## 6. 위험 관리 (ISO 14971)

| 항목 | 규격 근거 | 상태 | 구현 위치 | 비고 |
|------|-----------|------|-----------|------|
| 입력 데이터 검증 | ISO 14971 D.2 | **충족** | Pydantic 모델, 라우터 | 슬라이드 파일, 사용자 입력 검증 |
| 권한 검사 (권한 상승 방지) | ISO 14971 | **충족** | `backend/app/auth.py` | require_role 데코레이터, 자기 자신 역할변경/삭제 방지 |
| 마지막 관리자 보호 | ISO 14971 | **충족** | `backend/app/routers/users.py` | 마지막 admin 삭제/역할변경 차단 |

---

## 미충족 항목 상세 및 대응 방안

### P2: HTTP 보안 헤더 (미충족)

**필요 헤더:**
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Content-Security-Policy`
- `Strict-Transport-Security` (HTTPS 배포 시)
- `Referrer-Policy: strict-origin-when-cross-origin`

**구현 방법:** FastAPI 미들웨어로 응답 헤더 추가

### P2: 자동화 테스트 (미충족)

**필요 범위:**
- 인증 흐름 (로그인/로그아웃/MFA)
- RBAC 권한 검사
- 감사 로그 기록 및 HMAC 체인 검증
- 파일 업로드/무결성 검증
- CSRF/Rate Limiting 미들웨어

**구현 방법:** pytest + httpx AsyncClient

### P2: CI/CD 파이프라인 (미충족)

**필요 요소:**
- 린팅/정적분석 (ruff, mypy)
- 자동 테스트 실행
- 의존성 취약점 스캔
- 빌드 아티팩트 생성

### P3: 글로벌 예외 핸들러 (부분 충족)

**현재:** 개별 라우터에서 HTTPException 처리
**필요:** 미처리 예외의 안전한 응답 변환 + 로깅

### P3: DB 레벨 감사 로그 보호 (부분 충족)

**현재:** 애플리케이션 레벨 insert-only 패턴
**필요:** MongoDB 사용자 권한으로 audit_logs 컬렉션 update/delete 차단

---

## 요약

| 구분 | 충족 | 부분 충족 | 미충족 |
|------|------|-----------|--------|
| 접근 제어 및 인증 | 7 | 0 | 0 |
| 감사 추적 | 4 | 2 | 0 |
| 데이터 무결성 | 2 | 2 | 0 |
| 네트워크 보안 | 4 | 0 | 1 |
| 소프트웨어 수명주기 | 0 | 2 | 2 |
| 위험 관리 | 3 | 0 | 0 |
| **합계** | **20** | **6** | **3** |

> **P0~P1 기술 항목 전체 구현 완료.** 미충족 항목은 P2~P3 우선순위로 HTTP 보안 헤더, 자동화 테스트, CI/CD 파이프라인.
