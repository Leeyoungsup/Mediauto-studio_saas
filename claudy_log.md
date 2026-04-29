<!-- markdownlint-disable MD001 MD024 MD031 MD032 MD036 MD040 -->
# MeDIAuto Studio SaaS — Claude 작업 로그

> 형식: CLAUDE.md 규칙대로 H3 `### [YYYY-MM-DD HH:mm]` 단위로 누적 기록.

### [2026-04-29 14:00]

**Q:** 지금 내 코드 전체 분석해봐

**A:** Backend(~7,300 LOC) + Frontend(~11,200 LOC) 코드베이스 전체를 영역별로 분석. 인증·보안(JWT CAS rotation, MFA, CSRF/Rate Limit, HMAC 미디어 티켓, AES-256-GCM, 감사 로그 HMAC 체인), 슬라이드/타일 시스템(3-stage 피라미드, 69-tile/1-read 최적화, CPU 파티셔닝, generation counter, NDP 색보정), AI 파이프라인(HE-Fit/PD-Score/Precise-IHC/VS-IHC + VSTileStreamer 메모리 상한), 백그라운드 워커 3종(tile_worker/auto_ai/tile_janitor의 상호 양보), DB 설계(7 컬렉션), 프론트엔드(refresh 싱글톤, fade-in, SpatialGrid)를 종합 평가. 강점·개선 제안 정리.

**변경사항**: 없음 (분석 전용)

---

### [2026-04-29 14:30]

**Q:** 지금 docs 업데이트좀 해줘

**A:** 코드 기준으로 docs 4개 파일을 일괄 갱신.

- `docs/DATABASE.md`
  - `user_ai_edits` 컬렉션 신규 섹션 추가 (인덱스/필드/API)
  - `users` 에 MFA 필드 (`bool_mfa_enabled`, `str_totp_secret_enc`) 추가
  - `slides.str_sha256` 필드 추가, verify-integrity API 명시
  - audit_logs action 표 확장 (login_locked/pending/rejected, logout, password_changed, mfa_*, security.*)
  - audit_logs `str_hmac` 인덱스 명시
  - 부록 B 인덱스 일람 갱신
  - markdownlint disable 헤더 추가

- `docs/SECURITY.md`
  - "8. TOTP 2차 인증 (MFA)" 섹션 신규
  - "11. 파일 무결성 (SHA-256 체크섬)" 섹션 신규 (스트리밍 계산, verify API, 경로 방어 헬퍼)
  - Rate Limiting "슬라이딩 윈도우" → "고정 윈도우" 정정
  - TRUSTED_PROXIES 화이트리스트 정책 명시 (X-Forwarded-For 위조 방어)
  - 감사 로그 actions 표 확장
  - 부록 모듈 구조에 totp.py 추가

- `docs/FEATURES.md`
  - 렌더링 파이프라인 "4단계" → "3단계 stage 피라미드" 정정 + 69 타일/1 read 최적화 명시
  - Hamamatsu NDP.view2 색 매칭 (자동 LUT + 사용자 토글) 신규 설명
  - CPU 코어 파티셔닝 (cpu_layout) 섹션 추가
  - HE-Fit class 5: "Connective tissue" → "Stromal cell" 정정
  - Sticky Class HUD (Shift), 모델 결과 리셋 기능 신규
  - "12. 회원가입·로그인 & 2차 인증 (MFA)" 섹션 신규
  - "13. 파일 무결성 (SHA-256)" 섹션 신규
  - 키보드 단축키 표에 Shift/Shift+A/Delete 추가
  - 부록 A 엔드포인트 일람 갱신 (mfa/*, verify-integrity, user-edits/*, ndp 타일 등)
  - 부록 B 캐시 디렉토리 구조 갱신 (3-stage, ndpmatch, user_edits)

- `docs/COMPLIANCE_STATUS.md`
  - 최종 업데이트 날짜 2026-04-29 갱신
  - 네트워크 보안에 미디어 URL 서명/디렉토리 탈출 방어 항목 추가
  - Rate Limiting 비고를 고정 윈도우 + TRUSTED_PROXIES 로 정정
  - 합계 표 (충족 20→22)
  - markdownlint disable 헤더 추가

**변경사항**: docs/DATABASE.md, docs/SECURITY.md, docs/FEATURES.md, docs/COMPLIANCE_STATUS.md, claudy_log.md (신규)

---

### [2026-04-29 15:00]

**Q:** Readme.md 도 다시 정리해줘

**A:** README.md 를 코드와 docs 기준으로 통째로 재작성.

- 제목 정정: "MeDICus Studio SaaS" → "MeDIAuto Studio SaaS" (main.py FastAPI title 과 일치)
- 주요 기능 표 확장: Annotation, 사용자 편집본, 2차 인증 (MFA), 미디어 URL 서명, 감사 로그, 파일 무결성 항목 추가
- 기술 스택에 TOTP RFC 6238, HMAC-SHA256, NDP.view2 색 매칭, PyTorch CUDA AMP 명시
- 프로젝트 구조 — 누락된 모든 모듈 반영 (totp/csrf/rate_limit/url_signer/cpu_layout/thread_slide_pool/tile_worker/tile_janitor/ndp_color_match/svs_to_hamamatsu/priority + ai_pipelines/ 7개 + ai_user_edits 라우터). frontend 의 home.html/upload.html/home.js/color-correction.js, docs 5개, model/ + .secrets.json 추가
- 데이터베이스 컬렉션 6→7 (user_ai_edits 추가)
- 환경 변수 표 신설 (12개 — MONGO/JWT/시크릿/토큰 수명/업로드/CORS/TRUSTED_PROXIES/TILE_QUOTA/디렉토리)
- API 엔드포인트 표 갱신: MFA 4개, media-ticket, verify-chain, verify-integrity, refresh CAS rotation 명시
- "이미지 URL: query parameter token 인증" → "?mt=<10분 HMAC 티켓>" 으로 정정 (보안 후퇴 표현 제거)
- 운영 가이드 신설 — 배포 전 보안 체크리스트 8개, 알려진 한계 4개
- 추가 문서 링크 (FEATURES/DATABASE/SECURITY/COMPLIANCE_STATUS/color_match_analysis)
- 코드 규칙 섹션 보강 — 모든 type-prefix 일람 + 금지 규칙

**변경사항**: README.md, claudy_log.md

---

### [2026-04-29 15:30]

**Q:** SECURITY.md 이거 부분 인허가 SaMD 2등급을 목표로 하고 있으니까 이에대해서도 추가해줘

**A:** SECURITY.md 에 SaMD 2등급 인허가 컨텍스트 섹션을 추가.

- 인트로 한 문장 강화 — "SaMD Class 2 인허가 목표" + IEC 62304 / ISO 14971 / 21 CFR Part 11 / 식약처 가이드라인 명시
- TOC 에 "SaMD 2등급 인허가 컨텍스트" 와 "부록 C" 추가
- 신규 섹션 "SaMD 2등급 인허가 컨텍스트" (§1 앞):
  - IMDRF 등급 분류 표 (1~4등급) + 본 시스템이 2등급인 근거 (보조 진단 도구)
  - 적용 규격 8개 표 (IEC 62304/ISO 14971/ISO 13485/IEC 62366-1/IEC 81001-5-1/21 CFR Part 11/식약처/IMDRF SaMD N41)
  - 핵심 기술 통제 표 (8개 영역 → 본 문서 §장 매핑)
  - 본 문서가 다루지 않는 인허가 산출물 9개 체크리스트 (위험 분석 / SW 안전 등급 / 사용 적합성 / 임상 평가 / V&V / 변경 관리 / 사이버보안 위험 관리 / IFU / PMS)
- 신규 부록 C "SaMD 2등급 보안 통제 매트릭스":
  - 32개 통제 항목 (C-01 ~ C-32) ↔ 규격 ↔ 본 문서 §장 ↔ 코드 위치 ↔ 충족 상태 매핑
  - 충족 상태: ✅ 25개 / ⚠ 4개 (TLS, SBOM, 사이버보안 사고 대응 절차, 운영 보완) / ❌ 3개 (보안 이벤트 알림, HTTP 보안 헤더, 시판 후 모니터링)
  - 인허가 심사 대응 팁 4개 (추적성 매트릭스 / V&V 증적 / 운영 통제 / 미충족 항목 보강)

**변경사항**: docs/SECURITY.md, claudy_log.md

---

### [2026-04-29 16:00]

**Q:** url_signer.py 이런 내부소스 코드 위치는 안보였으면 좋겠어

**A:** SECURITY.md 에서 모든 내부 소스 파일·함수·상수 참조를 제거하고 추상 표현으로 교체.

- 본문 함수명 추상화:
  - `get_current_user`/`get_media_user`/`require_role`/`require_not_viewer` → "사용자 인증 의존성", "미디어 인증 의존성", "역할 제한 의존성", "viewer 차단 의존성"
  - `_safe_subpath`/`_safe_filename` → "경로 검증", "파일명 검증"
  - `verify_totp(secret, code, window=1)` → 일반 서술
  - `[`app/totp.py`](../backend/app/totp.py)` → "외부 라이브러리 의존 없이 자체 구현"
  - `app.audit.get_client_ip()` 와 `app.rate_limit._get_client_ip()` → "감사 모듈과 Rate Limit 미들웨어"
  - `db.users.find_one()` → "DB 조회"
- 라이브러리 API / 내부 상수 추상화:
  - `BCRYPT_COST = 12` → "work factor 12"
  - `MAX_LOGIN_ATTEMPTS=5` → "5회 초과"
  - `REFRESH_ROTATION_GRACE_SECONDS=300` → "5분 grace window"
  - `UserRole` enum → "사용자 역할"
  - `find_one_and_update` → "DB 의 원자적 CAS 연산"
  - `hmac.compare_digest` → "상수 시간(timing-safe) 비교"
  - `os.urandom(12)` → "OS 난수원에서 12 바이트(96 비트)"
  - `BaseHTTPMiddleware` 비교 표현 제거 → "ASGI 프로토콜 레벨에서 직접 구현"
  - `os.walk`/`run_in_executor`/`count_documents`/`$facet` → "동기 walk", "스레드 풀", "카운트 쿼리", "aggregation 파이프라인"
- 부록 A 파일 트리 → **6 레이어 보안 아키텍처 다이어그램** 으로 통째로 재작성 (네트워크 / ASGI 미들웨어 / 인증·인가 / 입력 검증 / 도메인 로직 / 영속화 + 직교 통제)
- 부록 C 매트릭스 "구현 위치" 컬럼 → 부록 A 의 추상 레이어명으로 32개 항목 모두 교체 (예: `auth.py::require_role` → "인증·인가 레이어 (역할 의존성)")
- DB 스키마 필드 (`bool_is_locked`, `dt_rotated_at`, `str_replaced_by`, `str_totp_secret_enc` 등) 와 audit action 명 (`user.login_locked` 등) 은 DATABASE.md 에서도 공식 문서화된 외부 인터페이스이므로 유지
- API 엔드포인트 경로 (`/api/auth/refresh` 등) 는 공개 인터페이스이므로 유지

**변경사항**: docs/SECURITY.md, claudy_log.md
