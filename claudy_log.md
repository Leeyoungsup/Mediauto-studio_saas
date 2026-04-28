# MeDIAuto Studio SaaS — Claude 작업 로그

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
