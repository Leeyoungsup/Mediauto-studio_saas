### [2026-04-16 15:45]
**Q:** PD-Score(Stomach/Lung) 고정 임계값을 0.5 → 0.1 로 되돌림. Precise-IHC 만 0.5 유지
**A:** 백엔드: `_run_pd_score` wrapper 에서 `float_score_conf_threshold=0.1` 명시 전달, `_run_precise_ihc` 는 `0.5` 명시 전달. `_run_marker_detection_pipeline` docstring 을 "PD=0.1 / Precise-IHC=0.5" 로 갱신 (default 0.5 는 안전장치로 유지). 프론트: `onPdScoreComplete` 의 `viewer.defaultConfidence` 0.5 → 0.1 복귀. PD-Score help 텍스트도 "0.1 이상" 으로 복구.
**변경사항**: backend/app/routers/ai.py, frontend/js/app.js

### [2026-04-16 15:30]
**Q:** Cell detection confidence 사용자 조절 기능 제거 — SaMD 인허가 재현성을 위해 고정값 강제. HE-Fit=0.1, PD-Score/Precise-IHC=0.5
**A:** **백엔드**: `_run_marker_detection_pipeline` 의 `float_score_conf_threshold` default 0.1 → 0.5 (PD-Score/Precise-IHC 공용). score 계산 comment 도 "고정 0.5, 사용자 조절 불가" 로 갱신. 레거시 캐시에 score_conf_threshold 가 다르면 자동 재계산하는 기존 로직이 그대로 동작. **프론트**: HE-Fit `onDetectionComplete` → `viewer.defaultConfidence = 0.1`, PD-Score `onPdScoreComplete` / Precise-IHC `onPreciseIhcComplete` → `0.5`. `buildResultList` 의 클래스별 confidence 슬라이더 UI 생성 코드 전체 삭제. `_debouncedRender` / `_confDebounceTimer` 도 미사용 → 제거. `saveDetectionResult` 에서 `class_confidence` / `default_confidence` 필드 저장 중단 (`delete` 로 레거시 필드 스트립). `onDetectionResultLoaded` (캐시 로드 경로) 에서 저장본의 `class_confidence` 복원 로직 제거 — 레거시 저장본이어도 현재 모델의 고정 임계값으로 재표시. PD-Score help 텍스트를 "검증된 고정 0.5 (SaMD 재현성)" 로 갱신. **CSS**: `.class-conf-slider` / `.conf-label` 규칙 삭제. `setDetectionResults` 는 기존대로 매 클래스 임계값을 `defaultConfidence` 로 재설정 → 고정값이 항상 보장됨.
**변경사항**: backend/app/routers/ai.py, frontend/js/app.js, frontend/css/style.css

### [2026-04-16 15:00]
**Q:** VS-IHC 결과 파일명에서 `_ihc_membrane_` 제거 (옵션 A — lazy 마이그레이션), nucleus 결과 파일 삭제
**A:** `_get_vs_cache_paths(slide_path, target_mpp)` 에서 `stain_type` 인자 제거, 새 컨벤션 `{stem}_VS-IHC_mpp{p}`. 함수 내부에 2단계 마이그레이션 (1) stain-suffix 마이그레이션: 기존 `_ihc_membrane_` 파일/타일디렉터리 → 새 이름 자동 rename, (2) 레거시 ai_results 루트 → VS-IHC/ 마이그레이션 기존 로직 유지 + 구 이름도 동시 체크. `_get_vs_tile_dir` 도 stain_type 제거. 모든 caller (ai.py 5곳 + auto_ai.py 1곳) 에서 stain_type 인자 제거. 프론트 URL/요청 스키마는 건드리지 않음 (stain_type 필드는 서버에서 무시). `backend/ai_results/VS-IHC/*_ihc_nucleus_*` 파일/디렉터리 전체 삭제 (rm -rf, 0개 남음 확인).
**변경사항**: backend/app/routers/ai.py, backend/app/auto_ai.py, backend/ai_results/VS-IHC/(nucleus 파일 삭제)

### [2026-04-16 14:30]
**Q:** VS-IHC membrane/nucleus 분리 제거 — membrane 모델 하나로 통합, "membrane 특화" 표시도 제거
**A:** 프론트: `app.html`에서 `btn-vs-nucleus` 버튼 삭제, `btn-vs-membrane` 라벨을 "IHC → H&E (Membrane)" → "IHC → H&E" 로 변경. `app.js`에서 `$btnVsNucleus` 상수/권한 체크/뷰어 제한 리스트/`AI_TASKS` 엔트리/클릭 리스너 모두 제거, `startVirtualStain` 내 nucleus 분기 제거(항상 `$btnVsMembrane` 사용), VS-IHC 라벨에서 "Membrane" 삭제. 백엔드: `ai.py::VS_MODEL_FILES`에서 `ihc_nucleus` 항목 제거. 기존 `ai_results/VS-IHC/*_ihc_nucleus_*.json` 파일은 과거 결과 보존용으로 그대로 둠.
**변경사항**: frontend/app.html, frontend/js/app.js, backend/app/routers/ai.py

### [2026-04-16 14:00]
**Q:** UI 전역에서 텍스트 선택/caret 깜빡임 막아달라 — slide-name 말고 다른 것들도 전부
**A:** `style.css` 글로벌 규칙에 `body { user-select: none; cursor: default }` 추가 후 `input, textarea, select, [contenteditable]` 에만 `user-select: text; cursor: text` 로 복구. 버튼류 input 과 select 는 `cursor: pointer`. 읽기전용 복사 허용이 필요한 콘텐츠는 `.selectable` 클래스로 opt-in. `.slide-name` 전용 `user-select: none` 규칙도 유지(중복 무해).
**변경사항**: frontend/css/style.css

### [2026-04-16 13:30]
**Q:** 3-stage 타일 페이드인 시 검정→타일 블렌딩으로 깜빡여보이는 문제
**A:** `tile-viewer.js::_render()` 의 present children 루프에서 페이드 중인 타일(fade_start + duration 이내)을 만나면 `_findFallbackTiles` 로 parent 를 수집해 `map_fallback_parents` 에 추가 → Pass 2b 에서 parent 가 먼저 깔린 뒤 그 위로 alpha 램프. 이로써 블랙 캔버스 위에 블렌딩되던 깜빡임 제거. alpha 계산은 `_tileFadeStart` Map (onload 시 `performance.now()` 기록), LRU 제거·슬라이드 전환·`clearCacheAndRender` 에서 동기 cleanup. 페이드 중 프레임은 `requestRender()` 로 rAF 루프 지속.
**변경사항**: frontend/js/tile-viewer.js

### [2026-04-15 08:30]
**Q:** 보안 관련 내용 정리 MD 파일 작성
**A:** `docs/SECURITY.md` 신규 작성 — 10개 섹션(시크릿 관리/비밀번호/JWT/계정 생애주기/RBAC/미디어 HMAC 티켓/필드 암호화/감사 로그/네트워크/알려진 한계) 전체 커버. 각 섹션마다 구현 경로 파일 링크, 위협 모델, 관련 라인 번호까지 포함. 운영 배포 직전 체크리스트 부록 추가(CORS 제한, TLS, X-Forwarded-For 신뢰 범위, audit_logs append-only 유저 분리 등). DB 미연결 시 익명 admin fallback, AES-GCM 검색 불가 등 설계상 한계도 명시.
**변경사항**: docs/SECURITY.md(신규)

### [2026-04-15 08:10]
**Q:** 모바일/태블릿 (작은 화면) 에서 뷰어가 너무 작게 보이는 문제 — 좌/우 패널 합계 560px+ 고정폭 3컬럼 레이아웃
**A:** `@media (max-width: 900px)` 미디어쿼리 추가. 좌/우 패널을 `position: absolute` drawer 로 전환 + `transform: translateX` 슬라이드 애니메이션. `body.panel-left-open` / `body.panel-right-open` 클래스로 열림 상태 관리. 메뉴바 좌측에 햄버거 토글(≡), 우측에 AI 패널 토글(□|) 버튼 추가(데스크톱에선 `.mobile-toggle { display: none }`). 배경 backdrop 클릭 + ESC 로 닫힘. `matchMedia` change 리스너로 브레이크포인트 역방향 이동 시 drawer 상태 자동 정리. 모바일 헤더·툴바 폭 축소(status/user-name 숨김, toolbar horizontal scroll), ≤480px 추가 규칙. 뷰어는 절대 위치 drawer 가 그 위로 겹치므로 `viewer-container` 실제 크기는 안 바뀜 → `_resizeCanvas` 재계산 불필요.
**변경사항**: frontend/css/style.css, frontend/app.html, frontend/js/app.js

### [2026-04-15 07:55]
**Q:** 관리자 활동 로그 시각이 UTC 로 표시되는 문제 (9시간 차이)
**A:** Motor 가 MongoDB 의 UTC datetime 을 naive 로 리턴 → FastAPI 가 timezone suffix 없이 직렬화 → JS `new Date()` 가 local(KST) 로 오해해 결과적으로 UTC 값을 KST 로 표시. `frontend/js/admin.js::fmtDate` 에서 ISO 문자열에 timezone suffix 가 없으면 `'Z'` 를 붙여 UTC 로 강제 파싱 후 `toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })` 로 변환. DB 마이그레이션 불필요 (저장은 이미 올바른 UTC).
**변경사항**: frontend/js/admin.js

### [2026-04-15 07:45]
**Q:** 활동 로그 다이얼로그 닫기 버튼 눌러도 안 닫히는 문제 + 버튼이 안 보이는 문제
**A:** (1) `admin.css .admin-dialog-wide` 기본 규칙에 `display: flex` 가 무조건 걸려있어서 `<dialog>` 기본의 `dialog:not([open]) { display: none }` 을 덮어씀 → `.close()` 호출해도 보이는 상태 유지. 기본 규칙에서 `display: flex` 제거하고 `[open]` 셀렉터에만 남김. (2) 닫기 버튼 클래스 `admin-btn-ghost`(흰색, 다크 헤더용)가 밝은 다이얼로그 헤더 `#f9fafb` 에서 안 보여서 `admin-btn-secondary` 로 교체.
**변경사항**: frontend/admin.html, frontend/css/admin.css

### [2026-04-15 07:30]
**Q:** DB 스키마 MD 문서 작성 + README 업데이트
**A:** `docs/DATABASE.md` 신규 작성 — 6개 컬렉션(users/sessions/audit_logs/ip_geo_cache/slides/folder_ai_configs) 전부 필드·타입·설명·인덱스·관계·마이그레이션·TTL·helper 흐름 정리. README 는 기능표(PD-Score/Precise-IHC/폴더 자동 AI/활동 로그 추가), 프로젝트 구조(geo.py/slide_store.py/auto_ai.py/admin.html/docs), RBAC 역할 매트릭스(technician 제거), API 엔드포인트(승인/활동 로그) 반영.
**변경사항**: docs/DATABASE.md(신규), README.md

### [2026-04-14 23:30]
**Q:** 타일 1024 전환, 폴더별 AI 제한, Cloudflare 캐시 오염, refresh 무한 retry 루프 수정
**A:**

1) **타일 사이즈 512 → 1024**: `config.py TILE_SIZE`, `tile-viewer.js TILE_SIZE`
   상수 변경. DB 는 `bool_tiles_ready` 를 False 로 리셋(타일 메타는 유지)하여
   `tile_worker` 가 다음 스캔에서 자동 재생성하게 하고, 기존 `tiles/` 폴더는
   수동 삭제. 뷰포트 기준 타일 수가 1/4 로 줄어 HTTP 오버헤드 감소.

2) **폴더별 AI 자동분석 설정 → 해당 AI 만 활성**: 폴더 진입(`onSlideLoaded`)
   후 `api.getFolderAiConfig(path)` 로 tasks 목록을 조회, `model::variant`
   set 을 만들어 `tissue-type`/`pd-tissue-type` radio 와 `btnDetect`/
   `btnPdScore`/`btnIhcHer2`/`btnVsMembrane`/`btnVsNucleus` 를 disabled
   처리(숨기지 않음). 현재 선택이 허용 집합 밖이면 첫 허용 옵션으로 자동 전환.

3) **Cloudflare Browser Cache TTL 5-day 오염**: Cloudflare Tunnel 의 Browser
   Cache TTL 이 origin Cache-Control 을 덮어써 구 JS 가 시크릿 창에서도 계속
   서빙되던 문제. 사용자 측에서 Cloudflare Caching 설정을 "Respect Existing
   Headers" 로 변경해 해결. 보강으로 `NoCacheStaticFiles` 서브클래스를 추가,
   `.js/.mjs/.html/.css` 에 `Cache-Control: no-cache, must-revalidate` 를
   강제 — ETag/304 는 유지되므로 파일이 바뀐 경우에만 바이트 재전송.

4) **Refresh 무한 retry 루프**: 이전 세션에서 `token_reuse_detected` 가 한
   사용자 세션 64 개를 전부 revoke 한 잔재로, 브라우저가 죽은 세션을 가리키는
   refresh token 을 들고 있음. 추가로 기존 패치 버그로 인해 background timer
   의 `_refreshTokenIfNeeded` 가 실패 시 redirect 를 안 해서 30 초마다 무한
   401. 수정: `_refreshTokenIfNeeded(bool_force, bool_silent)` 로 시그니처
   확장. silent=false (timer/직접 호출) 는 실패 시 tokens clear 후
   `/login.html` 로 redirect, silent=true (`_authFetch` 재시도 경로) 는 단순
   `false` 반환해 호출자가 제어. `_authFetch` 는 `_refreshTokenIfNeeded(true,
   true)` 로 호출 후 재시도, 그래도 401 이면 스스로 정리+리다이렉트. 또한
   `REFRESH_ROTATION_GRACE_SECONDS` 를 30 → 300 초로 늘리고, grace 밖
   known session 도 더이상 `update_many` 로 전 세션을 revoke 하지 않음 —
   해당 request 만 401 반환하고 `security.refresh_stale_rotation` 감사 로그.

**변경사항**:

- 수정: backend/app/config.py (TILE_SIZE 1024)
- 수정: backend/main.py (NoCacheStaticFiles)
- 수정: backend/app/routers/auth.py (grace 300s, 단일 요청 401 정책)
- 수정: frontend/js/tile-viewer.js (TILE_SIZE 1024)
- 수정: frontend/js/app.js (_applyFolderAiRestrictions)
- 수정: frontend/js/api.js (_refreshTokenIfNeeded silent flag, _authFetch 재시도)

### [2026-04-14 21:00]
**Q:** High 이슈 5건 해결 (#4 Refresh race, #5 타일 디스크 쿼터, #6 Auto-AI race, #7 Pepper 하드코딩, #8 타일 부분실패)
**A:** 각 이슈를 원자성/리소스/시크릿 관점에서 해결.

1) **#4 Refresh token CAS**: `find_one_and_update` 로 `{refresh_token, is_revoked:False}`
   필터 + `{is_revoked:True, replaced_by:<새 토큰>}` 세트를 원자화. CAS winner 만 새
   세션을 insert, loser 는 기존 30초 grace window 경로로 fall-through. 동시 요청
   2건이 같은 refresh 로 오면 한 쪽만 rotation 성공, 다른 쪽은 같은 신규 refresh 를
   grace 경로로 돌려받아 양쪽 모두 일관.

2) **#7 AUTH_PEPPER 이관**: `models.py` 하드코딩 제거 → `config.py` 가
   환경변수 `AUTH_PEPPER` 또는 `.secrets.json` 의 `pepper` 키에서 로드. 기존
   배포(`.secrets.json` 존재하지만 `pepper` 키 없음) 는 legacy 값을 파일로 이관해
   기존 해시 호환 유지, 신규 설치는 무작위 pepper 생성.

3) **#8 타일 부분실패 정리**: `_generate_tiles` 의 finally 에서 `.complete` 마커가
   쓰이기 전 예외로 빠져나간 경우 불완전 tile dir 를 즉시 `shutil.rmtree`. 다음
   스캔에서 `tiles_are_valid` → False → 재생성 경로로 들어가지만, 그 사이 뷰어가
   404/깨진 타일을 만나는 윈도우를 최소화.

4) **#5 타일 디스크 캐시 쿼터 + LRU janitor**: `TILE_CACHE_QUOTA_BYTES` 설정
   (기본 50GB) 추가. 신규 `tile_janitor.run_janitor_once()` 가 DB `bool_tiles_ready`
   True 슬라이드의 tile dir 총량을 집계, 쿼터 초과 시 `.complete` 마커 mtime (LRU
   signal) 오름차순으로 eviction — rmtree + DB 플래그 False. 현재 `slide_manager`
   에 열려 있는 (활성 뷰잉) 슬라이드는 stem 기준으로 보호. `tile_worker` 가
   20초 주기 스캔을 15회마다(=5분) 호출. tiles 라우터는 서빙 시 throttled (60s)
   로 `.complete` 를 `os.utime` 하여 LRU 접근 시각을 갱신.

5) **#6 Auto-AI race**: `is_system_idle()` 의 스냅샷 체크와 `_tasks` insert
   사이에 사용자 task 가 끼어들 수 있던 문제를 `check_idle_and_reserve()` 로 해결.
   `ai_router._tasks_lock` → `_activity_lock` 순서로 동시에 잡은 상태에서 모든
   idle 조건(업로드/활동/queued·running 존재) 을 검사하고 즉시 reservation 을
   삽입. 사용자 경로는 `_tasks_lock` 만 잡으므로 데드락 없음. `_run_auto_inference`
   는 `check_idle_and_reserve` 실패 시 그 슬라이드만 skip.

**변경사항**:

- 생성: backend/app/tile_janitor.py (LRU + 쿼터 eviction)
- 수정: backend/app/config.py (AUTH_PEPPER, TILE_CACHE_QUOTA_BYTES)
- 수정: backend/app/models.py (하드코딩 pepper 제거 → settings.AUTH_PEPPER)
- 수정: backend/app/tile_generator.py (부분실패 cleanup)
- 수정: backend/app/tile_worker.py (janitor 주기 호출)
- 수정: backend/app/routers/tiles.py (throttled access touch)
- 수정: backend/app/routers/auth.py (refresh CAS)
- 수정: backend/app/auto_ai.py (check_idle_and_reserve 원자화)

### [2026-04-14 19:30]
**Q:** 프로젝트 전체 분석 + Critical 보안/리소스 문제 해결 (저사양 서버 대상 외)
**A:** 전체 프로젝트(FastAPI WSI 뷰어 + AI SaaS) 구조·기술 스택·최근 개발 궤적 파악 후 Critical 이슈 2건을 해결.

1) **JWT 쿼리 노출 제거**: 브라우저 이미지 태그(img src) 타일/썸네일 URL 에
   JWT 가 `?token=` 으로 실리던 문제를 HMAC-SHA256 단기 미디어 티켓(10분 TTL,
   사용자 바인딩, 미디어 엔드포인트 전용 스코프)으로 교체. `?mt=<opaque>`
   쿼리만 노출되고 누출되어도 API 호출 권한은 없음. slides/ai 라우터에
   `media_router` 서브 라우터를 추가해 스코프 분리. `_extract_bearer_token`
   의 query 토큰 fallback 제거. 프론트는 `_ensureMediaTicket` 으로 _authFetch
   호출마다 사전 발급/갱신.

2) **OpenSlide thread-local 핸들 누수 제거**: SlideManager 에 generation
   counter 추가(close 시 bump). 공용 `thread_slide_pool` 모듈 신설 —
   generation 검증으로 스테일 핸들 자동 close, per-thread LRU(8개) 로 무제한
   누적 방지. tiles.py 와 routers/ai.py 의 `_patch_thread_local` 관용 코드를
   `get_thread_slide()` 호출로 교체.

**변경사항**:

- 생성: backend/app/url_signer.py (HMAC 미디어 티켓)
- 생성: backend/app/thread_slide_pool.py (generation + LRU 풀)
- 수정: backend/app/auth.py (query token fallback 제거, get_media_user 추가)
- 수정: backend/app/routers/auth.py (/media-ticket 엔드포인트)
- 수정: backend/app/routers/tiles.py (media_user dep + 공용 풀)
- 수정: backend/app/routers/slides.py (media_router 로 thumbnail/preview 이동)
- 수정: backend/app/routers/ai.py (media_router 로 virtual-stain tile 이동, 공용 풀)
- 수정: backend/app/slide_manager.py (generation counter)
- 수정: backend/main.py (media_router 등록)
- 수정: frontend/js/api.js (미디어 티켓 캐시, ?token= → ?mt=)

### [2026-03-23 13:10]
**Q:** 데이터 분석/AI 프로젝트를 위한 .clauderules.md 통합 및 로그 기록 규칙 설정
**A:** 데이터 타입 접두어(df_, np_, int_ 등) 체계 확립 및 작업 시마다 .claudy_log.md 업데이트 규칙 정의.
**변경사항**: clauderules.md 생성

### [2026-04-12 14:00]
**Q:** 프로젝트 구조 분석 및 정리
**A:** FastAPI 백엔드 + Vanilla JS 프론트엔드로 구성된 디지털 병리 WSI 뷰어 프로젝트 구조 파악. 슬라이드 업로드/타일 렌더링/AI 분석(HE-Fit, VS-IHC) 기능 확인.
**변경사항**: 없음 (읽기 전용)

### [2026-04-12 14:30]
**Q:** MongoDB 기반 계정 관리 시스템 구현 (병원 온프레미스 배포, 보안 필수)
**A:** MongoDB + JWT 기반 전체 인증/인가 시스템 구현 완료. RBAC(admin/doctor/technician/viewer), bcrypt+pepper 해싱, AES-256-GCM 필드 암호화, Refresh Token rotation + reuse detection, 감사 로그, 계정 잠금 등 보안 기능 포함.
**변경사항**:
- 생성: backend/app/database.py (MongoDB 연결)
- 생성: backend/app/models.py (User 모델, bcrypt, UserRole)
- 생성: backend/app/auth.py (JWT + RBAC 의존성)
- 생성: backend/app/audit.py (감사 로그)
- 생성: backend/app/encryption.py (AES-256-GCM)
- 생성: backend/app/routers/auth.py (인증 API)
- 생성: backend/app/routers/users.py (관리자 사용자 관리 API)
- 생성: frontend/login.html (로그인/회원가입 페이지)
- 생성: frontend/app.html (메인 뷰어 + 사용자 메뉴)
- 수정: backend/requirements.txt (motor, bcrypt, python-jose, cryptography 추가)
- 수정: backend/app/config.py (MONGO, JWT, 보안 설정 추가)
- 수정: backend/main.py (DB 연결/해제, auth/users 라우터 등록)
- 수정: backend/app/routers/slides.py (인증 미들웨어 적용)
- 수정: backend/app/routers/tiles.py (인증 미들웨어 적용)
- 수정: backend/app/routers/ai.py (인증 미들웨어 적용)
- 수정: frontend/index.html (토큰 기반 리다이렉트)
- 수정: frontend/js/api.js (JWT 토큰 관리, _authFetch, 이미지 URL 토큰 쿼리 파라미터)
- 수정: frontend/js/app.js (로그아웃 핸들러, 사용자 표시)
- 수정: README.md (전체 프로젝트 문서화)

### [2026-04-12 15:30]
**Q:** start.bat 실행 시 CMD 에러 ('버' is not recognized)
**A:** REM 주석의 한글 em-dash(`—`) 문자가 CMD 인코딩에서 깨져 파싱 오류 발생. 모든 주석을 ASCII 전용으로 교체하여 해결.
**변경사항**: 
- 수정: start.bat (한글 em-dash → ASCII 주석)

### [2026-04-12 15:45]
**Q:** MongoDB 미설치 시 서버 크래시 방지
**A:** `connect_db()`에 try/except + ping 테스트 추가. MongoDB 미연결 시에도 앱이 계속 구동되며 인증만 비활성화되도록 graceful 처리. `is_db_connected()` 함수 추가.
**변경사항**: 
- 수정: backend/app/database.py (graceful connection, is_db_connected 추가)
- 수정: backend/app/auth.py (DB 미연결 시 anonymous user 반환)

### [2026-04-12 16:00]
**Q:** 로그인 페이지 다수 버그 수정
**A:** (1) `[object Object]` 에러 표시 → FastAPI 422 응답의 detail이 배열인 경우 처리 추가. (2) 로그인 버튼 무반응 → 숨겨진 name 필드의 `required` 속성이 form submit을 차단 → 제거. (3) 회원가입 모드에서 이름 필드 미표시 → `querySelector('span, #mode-toggle')` JS 에러 → 해당 라인 제거.
**변경사항**: 
- 수정: frontend/login.html (에러 파싱, required 제거, toggleMode JS 수정)

### [2026-04-12 16:30]
**Q:** 이메일 → 아이디 기반 로그인으로 전환 ("이메일 말고 아이디 로그인으로 해줘")
**A:** 전체 인증 시스템을 이메일 기반에서 아이디(login_id) 기반으로 마이그레이션. `str_email`/`EmailStr` → `str_login_id`/`str` 전환. 아이디 형식: 4~30자 영문/숫자/언더스코어 (`LOGIN_ID_PATTERN = ^[a-zA-Z0-9_]{4,30}$`). DB 컬렉션 초기화 후 clean start.
**변경사항**: 
- 수정: backend/app/models.py (str_email → str_login_id, create_user_document 파라미터 변경)
- 수정: backend/app/routers/auth.py (RegisterRequest/LoginRequest 스키마, 아이디 검증 로직)
- 수정: backend/app/routers/users.py (감사 로그 내 str_email → str_login_id)
- 수정: frontend/login.html (이메일 필드 → 아이디 필드, 클라이언트 검증 규칙 변경)

### [2026-04-12 17:00]

**Q:** 로그인 후 페이지(app.html) 색상 테마를 MeDIAuto 대시보드 스크린샷의 보라색 톤에 맞춰달라
**A:** style.css의 :root CSS 변수만 교체해 전역 테마를 Google Blue(#1a73e8) → Purple(#6c5ce7)로 전환. var(--accent) 기반 컴포넌트(버튼/탭/슬라이더/토글/포커스링 등) 자동 전파. 배경/호버/보더도 쿨톤으로 미세 조정. 추후 사이드바 구현용 --sidebar-dark(#2d2d5f) 변수 예약. login.html 인라인 색상도 동일 팔레트로 갱신.

**변경사항**:

- 수정: frontend/css/style.css (:root 변수 — accent purple, bg-light 쿨톤, sidebar-dark 추가)
- 수정: frontend/login.html (인라인 #1a73e8 → #6c5ce7, 호버/포커스 색상 일치)

### [2026-04-12 17:30]

**Q:** 색상만 바꾸지 말고 전체 테마를 대시보드 스크린샷 수준으로 바꿔달라
**A:** app.html 전역 비주얼을 "다크 퍼플 사이드바 + 카드형 패널" 스타일로 리디자인. 좌측 Slides 패널 sidebar-dark 그라데이션 + 흰 텍스트, 슬라이드 hover/active 퍼플 글로우. 메뉴바/툴바 52/42px 확장·얕은 그림자, zoom-info 퍼플 pill, toolbar-btn hover 퍼플 틴트. 뷰어 컨테이너 마진+12px 라운드+카드 섀도. 우측 AI 패널 투명 컨테이너+개별 카드 레이아웃. 탭바 pill 스위처(active 퍼플+섀도). 버튼 퍼플 틴트/글로우, 프로그레스 바 999px 퍼플 그라데이션, 다이얼로그 헤더 그라데이션+16px 라운드+backdrop blur, 스크롤바 얇은 퍼플 pill.

**변경사항**:

- 수정: frontend/css/style.css (전역 테마 리디자인)

### [2026-04-12 17:45]

**Q:** 위쪽 바도 스크린샷처럼 수정해달라
**A:** menubar 높이 56px, 좌측 240px 영역을 sidebar-dark 그라데이션으로 채워 로고를 흰색으로 반전(filter brightness-invert). 툴바도 좌측 240px 다크 strip(::before)을 덧대 좌측 사이드바가 최상단부터 연속으로 보이게 함. slide-name은 중앙 pill 스타일, status-text는 녹색 dot + pill로 "online" 표시. user-name은 그라데이션 아바타 도트 + ▼ 드롭다운 화살표 pill로 변경. 중복 status-text 규칙 제거.

**변경사항**:

- 수정: frontend/css/style.css (menubar/toolbar 레이아웃 + 사용자 영역 리디자인)

### [2026-04-13 09:00]

**Q:** Virtual staining 실패 — ModuleNotFoundError: No module named 'ai'. 사용자가 ai/ 와 model/ 폴더를 backend/ 에 붙여넣음.

**A:** 레거시 ai/ 패키지가 PyQt5(QObject/QThread/pyqtSignal)에 모듈 최상단에서 의존해 헤드리스 SaaS 백엔드에서 import 실패. PyQt5 설치 없이 우회하기 위해 backend/ai/`__init__.py` 를 재작성: import 시점에 PyQt5/PyQt5.QtCore/QtGui/QtWidgets 를 no-op 스텁으로 sys.modules 에 주입(QObject, QThread.start→run() 동기 호출, pyqtSignal→.emit/.connect no-op, QImage/QPixmap 더미 클래스). `__init__.py` 의 깨진 eager-import (TissueSegmentation/Classification/LesionDetection — 일부 클래스 부재) 도 제거. conda env yslee 에서 ai.virtual_stain / ai.detection / ai.nets import 통과 확인.

**변경사항**:

- 신규: backend/ai/ (전체 패키지 — virtual_stain, detection, nets, epithelial_classifier, segmentation, classification, pdl1_detection, utils)
- 신규: backend/model/ (HnE_*.pt, IHC_HnE_virtual_stain_membrane.pth, PDL1_TPS_detection.pt 등 가중치)
- 수정: backend/ai/`__init__.py` (PyQt5 stub 주입 + eager import 제거)

### [2026-04-13 09:15]

**Q:** Virtual stain model not found: C:\\...\\project\\model\\IHC_HnE_virtual_stain_membrane.pth

**A:** `backend/app/config.py` 의 MODEL_DIR 경로가 `Path(__file__).parent` 를 4단계 올라가 프로젝트 루트의 바깥(Desktop/project/model)을 가리키고 있었음. backend/ 기준 2단계(backend/model) 로 축소. 실제 가중치 6종(HnE_detection / HnE_BR_segmentation / HnE_ST_segmentation / IHC_HnE_virtual_stain_membrane / PDL1_TPS_detection / backup) 모두 정상 해석 확인.

**변경사항**:

- 수정: backend/app/config.py (MODEL_DIR 경로 수정)

### [2026-04-13 09:30]

**Q:** Virtual staining 실패 — No module named 'core' (virtual_stain.py 에서 core.wsi_tile_manager 참조)

**A:** 레거시 데스크톱 ai/ 모듈이 Qt 뷰어 스레드와의 I/O 우선순위 조율을 위해 `core.wsi_tile_manager.viewer_io_priority.ai_yield_if_needed()` 를 호출하는데, SaaS 백엔드엔 경쟁할 Qt 스레드가 없고 core 패키지도 존재하지 않음. 4개 파일(virtual_stain, detection, pdl1_detection, epithelial_classifier)의 해당 호출을 no-op(주석)로 치환.

**변경사항**:

- 수정: backend/ai/virtual_stain.py, detection.py, pdl1_detection.py, epithelial_classifier.py (core.wsi_tile_manager 참조 제거)

### [2026-04-13 09:45]

**Q:** model/IHC_HnE_virtual_stain_nucleus.pth 추가했으니 VS-IHC Nucleus 버튼 활성화 (membrane 과 동일 구조/파이프라인)

**A:** 라우터 VS_MODEL_FILES 에 `ihc_nucleus` 엔트리 추가, 프론트엔드 Nucleus 버튼 disabled/placeholder 제거 및 primary 스타일 적용, 클릭 핸들러 연결, 슬라이드 로드/실행중/완료 시 disable 토글에 nucleus 버튼 동기화.

**변경사항**:

- 수정: backend/app/routers/ai.py (VS_MODEL_FILES 에 ihc_nucleus 등록)
- 수정: frontend/app.html (btn-vs-nucleus 활성 스타일)
- 수정: frontend/js/app.js (nucleus 클릭 핸들러 + 버튼 상태 토글 3곳)

### [2026-04-13 10:00]

**Q:** PDL1_ST_CPS_detection.pt / PDL1_TPS_detection.pt 를 PD-Score 탭에 구현. Stomach→CPS(7클래스), Lung→TPS(3클래스). HnE Detection 과 모델 구조 동일.

**A:** 백엔드에 `PD_SCORE_CONFIG` dict (tissue별 model_file/num_classes/class_names/class_colors/score_type) 와 `_compute_pd_score` helper 추가. `_run_pd_score` 함수로 `_run_detection` 과 동일한 YOLOv11m 파이프라인(조직 마스크 → 병렬 I/O 프리페치 → 배치 GPU 추론 → NMS)을 재사용하되 epithelial 재분류는 생략. Stomach CPS = min(100, (cls3 + cls4 + cls5) / (cls0+cls3) × 100), Lung TPS = cls1 / (cls0+cls1) × 100. 결과 캐시는 `ai_results/PD-Score/{stem}_PD-Score_{tissue}.json`. 신규 엔드포인트 `POST /ai/pd-score` 추가. 프론트 PD-Score 탭에 Stomach/Lung 라디오 + Run 버튼 + 그라데이션 스코어 카드(CPS/TPS 대형 숫자 + 세부 카운트) 구성. `api.startPdScore()` 추가, `app.js` 에 `startPdScore`/`onPdScoreComplete` 추가 및 슬라이드 로드 시 버튼 활성화.

**변경사항**:

- 수정: backend/app/routers/ai.py (`PD_SCORE_CONFIG`, `_get_pd_score_cache_path`, `_compute_pd_score`, `_run_pd_score`, `POST /pd-score` 엔드포인트)
- 수정: frontend/app.html (PD-Score 탭 활성화, tissue 라디오 + 실행 버튼 + 스코어 카드)
- 수정: frontend/css/style.css (.pd-score-result 그라데이션 카드 스타일)
- 수정: frontend/js/api.js (startPdScore 메서드)
- 수정: frontend/js/app.js ($btnPdScore 요소 참조, startPdScore/onPdScoreComplete 핸들러, 슬라이드 로드 시 활성화)

### [2026-04-13 10:15]

**Q:** PD-Score 실행 시 state_dict size mismatch — head.dfl.conv.weight [1,4,1,1] vs [1,16,1,1], head.box.*.2 [16 vs 64]

**A:** PDL1 체크포인트는 DFL 채널수가 4로 학습됨 (HnE detection 은 기본값 16). `_run_pd_score` 에서 load 전에 state_dict 의 `head.dfl.conv.weight` 채널수를 검사하여 기본값과 다르면 `head.ch` 를 체크포인트 값으로 교체하고 `head.dfl = DFL(ch)`, `head.box[i][-1]` 의 마지막 Conv2d 를 `out_channels=4*ch` 로 재구성한 뒤 로드. 이렇게 동일 `yolo_v11_m` 팩토리를 재사용하면서 PDL1 전용 head shape 만 맞춤.

**변경사항**:

- 수정: backend/app/routers/ai.py (`_run_pd_score` 내부에서 PDL1 체크포인트 감지 후 head DFL/box 재구성)

### [2026-04-13 14:30]

**Q:** `Precise_IHC_HER2_detection.pt` 모델 추가 — AI Analysis 에 Precise-IHC 탭 만들고 HER2/ER-PR/KI-67 버튼 배치(HER2 만 활성화). 모델 구조는 PD-L1 과 동일(DFL ch=4). 클래스 0~3 은 HER2 intensity (0+~3+), 4 는 other(표시 제외). 색상은 class0 green → class3 deep red 그라데이션. HER2 스코어.

**A:** 백엔드에서 `_run_pd_score` 파이프라인을 공용 `_run_marker_detection_pipeline(task_id, slide_id, roi_polygons, dict_config, cache_path, score_fn, score_key, extra_fields, log_label)` 로 리팩터 — YOLOv11m 파이프라인(조직 마스크 → 병렬 I/O 프리페치 → 배치 GPU 추론 → NMS → exclude_classes 필터) 을 score 계산 함수만 주입받아 재사용하게 함. `_run_pd_score` 는 `_compute_pd_score` wrapper 로 축소. 신규 `PRECISE_IHC_CONFIG` (HER2: num_classes=5, class_colors 0:#27ae60, 1:#f1c40f, 2:#e67e22, 3:#c0392b, 4:hidden, exclude_classes=[4]) 추가. `_compute_her2_score` 는 클래스 0~3 을 intensity 0/1/2/3 으로 보고 가중 평균 + dominant_class + class_counts 리턴. `_run_precise_ihc` wrapper + `POST /ai/precise-ihc` 엔드포인트(marker Form param). 프론트는 AI Analysis 탭 바에 Precise-IHC 추가, 내부에 HER2/ER-PR/KI-67 버튼 행(HER2 만 enable), HER2 score 디스플레이 카드 추가. `api.startPreciseIhc(slideId, roi, marker)`, `app.js` 에 `$btnIhcHer2` 핸들러, `startPreciseIhc` / `onPreciseIhcComplete`, `_updateHer2ScoreDisplay` (confidence 슬라이더 변경 시 재계산), 비주얼라이제이션 modelType 을 `'Precise-IHC'` 로 분기. `visualization.js` 는 Precise-IHC 모드에서 Spatial Heatmap 숨기고 Tumor Analysis 탭을 HER2 Analysis 로 교체 — `_renderHer2Analysis` 는 가중 평균 반원 게이지(0~3 → 0~100 매핑, dominant 색상) + intensity 분포 막대 차트 렌더. CSS 에 `.ihc-marker-row` flex 버튼 행 추가.

**변경사항**:

- 수정: backend/app/routers/ai.py (`_run_marker_detection_pipeline` 리팩터, `_run_pd_score` wrapper, `PRECISE_IHC_CONFIG`, `_get_precise_ihc_cache_path`, `_compute_her2_score`, `_run_precise_ihc`, `POST /ai/precise-ihc` 엔드포인트)
- 수정: frontend/app.html (Precise-IHC 탭 버튼 + HER2/ER-PR/KI-67 버튼 행 + HER2 score 카드)
- 수정: frontend/css/style.css (`.ihc-marker-row` 플렉스 버튼 행)
- 수정: frontend/js/api.js (`startPreciseIhc` 메서드)
- 수정: frontend/js/app.js (`$btnIhcHer2` 외 HER2 UI 요소, `startPreciseIhc`/`onPreciseIhcComplete`, `_updateHer2ScoreDisplay`, 슬라이드 로드 시 활성화, 비주얼 modelType 분기)
- 수정: frontend/js/visualization.js (`_configureTabs` Precise-IHC 분기, `_renderHer2Analysis`/`_drawHer2Gauge`/`_drawHer2Bars`)

### [2026-04-13 15:30]

**Q:** PD-L1 모델과 HER2 모델은 기본 초기 confidence 값을 0.1로 설정해달라 (HE-Fit 는 0.01 유지).

**A:** `tile-viewer.js` 의 `TileViewer` 에 `this.defaultConfidence = 0.01` 필드 추가 — `setDetectionResults` 와 `_refreshAfterCellEdit` 가 `const defConf = this.defaultConfidence ?? 0.01` 로 dynamic 하게 초기 슬라이더 값을 설정. `app.js` 에서는 `onDetectionComplete` (HE-Fit) 가 `viewer.defaultConfidence = 0.01`, `onPdScoreComplete` 및 `onPreciseIhcComplete` 가 `viewer.defaultConfidence = 0.1` 로 설정한 뒤 `setDetectionResults` 호출. `buildResultList` 슬라이더 초기값도 `viewer.classConfidence[id] ?? viewer.defaultConfidence ?? 0.01` 로 수정.

**변경사항**:

- 수정: frontend/js/tile-viewer.js (`defaultConfidence` 필드, `setDetectionResults` / `_refreshAfterCellEdit` 에서 사용)
- 수정: frontend/js/app.js (`onDetectionComplete`/`onPdScoreComplete`/`onPreciseIhcComplete` 에서 `viewer.defaultConfidence` 설정, `buildResultList` 슬라이더 초기값)

### [2026-04-13 16:45]

**Q:** 관리자 권한을 가진 계정만 접근 가능한 관리자 페이지를 만들고, 회원가입 즉시 로그인 불가 — 관리자가 승인해야만 로그인 가능하도록. 추가로 관리자가 직접 계정 생성 및 사용자 관리도 할 수 있게. (기존 사용자는 재승인 대상, 관리자 생성 계정은 admin 이 비밀번호 직접 지정)

**A:** **백엔드** — `models.py` 에 `ApprovalStatus` enum(`pending`/`approved`/`rejected`) 추가, `create_user_document` 에 `str_approval_status`/`bool_is_active`/`str_approved_by` 파라미터 추가(기본 pending+inactive). `database.py` 에 startup migration — 관리자 계정은 approved+active, 비관리자는 pending+inactive 로 초기화하고 `str_approval_status` 인덱스 생성. `routers/auth.py` 의 register 는 첫 사용자만 admin+approved+active, 나머지는 viewer+pending+inactive 로 생성하고 `bool_requires_approval` 리턴; login 은 비밀번호 검증 후(enumeration 방지) approval 상태 체크 — pending 은 "관리자 승인 대기중", rejected 는 "가입 거부됨" 메시지로 403. `routers/users.py` 에 신규 엔드포인트: `GET /users/pending`, `POST /users/approve` (승인 시 role 설정), `POST /users/reject`, `POST /users/create` (admin 이 비밀번호 직접 지정해 즉시 승인된 계정 생성), `POST /users/update` (이름/부서/비밀번호 변경), `DELETE /users/delete/{id}`. `GET /users/list` 는 `str_approval_status`/`str_search` 필터 + `int_pending_total` 카운트 지원. last-admin 가드를 `/users/role` demote 와 `/users/delete/{id}` 에 추가. **프론트엔드** — 신규 `admin.html` 3탭(Pending Approvals / User Management / Create User) + 수정 다이얼로그, `admin.css` 전용 스타일, `admin.js` (module 아님) — `authFetch` wrapper + `userCache` Map 기반 편집, 필터/디바운스 검색/20개 페이지네이션, role 변경 dropdown + 확인 dialog. `login.html` 회원가입 성공 메시지가 `data.str_message` 또는 `bool_requires_approval` 기반으로 안내. `app.html` 메뉴바에 `#link-admin` (hidden) 추가, `app.js` 가 `dict_me.str_role === 'admin'` 일 때 unhide. `style.css` 에 `.btn-admin` accent purple pill 스타일 추가.

**변경사항**:

- 수정: backend/app/models.py (`ApprovalStatus` enum, `create_user_document` 확장)
- 수정: backend/app/database.py (approval_status startup migration + 인덱스)
- 수정: backend/app/routers/auth.py (register pending 기본값, login approval 체크)
- 수정: backend/app/routers/users.py (pending/approve/reject/create/update/delete, list 필터, last-admin 가드)
- 생성: frontend/admin.html
- 생성: frontend/css/admin.css
- 생성: frontend/js/admin.js
- 수정: frontend/login.html (승인 대기 안내 메시지)
- 수정: frontend/app.html (`#link-admin` 메뉴바 링크)
- 수정: frontend/js/app.js (role 기반 admin 링크 표시)
- 수정: frontend/css/style.css (`.btn-admin` 스타일)

### [2026-04-13 15:50]

**Q:** 슬라이드 파일 여러개를 한번에 올릴 수 있게 하고, 좌측 폴더에 직접 드롭해서 업로드도 가능하게 해줘.

**A:** `app.html` 의 `#file-input` 에 `multiple` 속성 추가. `app.js` 의 업로드 로직을 `uploadOneFile(file, targetPath, prefix)` + `uploadFiles(fileList, targetPath)` 로 리팩터 — 확장자 화이트리스트(`SLIDE_EXT_PATTERN`) 필터링, 순차 업로드, 진행률에 `[n/total]` 프리픽스 표기, 첫 파일이 현재 폴더에 업로드되면 자동으로 뷰어에서 열기. 파일 입력 change / 뷰어 drop 이 `uploadFiles` 호출. 폴더 아이템 drop 핸들러는 `e.dataTransfer.files.length > 0` 이면 `uploadFiles(files, folderPath)` 로 해당 폴더에 직접 업로드, 아니면 기존 `_dropMoveFiles` (내부 이동) 로 fallback. breadcrumb drop 핸들러도 동일하게 OS 파일 업로드 지원. `$slideList` 빈 영역에도 drag 오버레이 + drop 핸들러 추가(현재 폴더로 업로드) — `Files` 타입만 감지해 내부 드래그와 충돌 없음. `style.css` 에 `.slide-list.drag-over-panel` 대시 아웃라인 스타일 추가.

**변경사항**:

- 수정: frontend/app.html (`#file-input` `multiple` 속성)
- 수정: frontend/js/app.js (`uploadFiles`/`uploadOneFile` 리팩터, 파일 입력 change, 뷰어 drop, 폴더/breadcrumb drop OS 파일 지원, `$slideList` 빈 영역 OS 파일 drop)
- 수정: frontend/css/style.css (`.slide-list.drag-over-panel`)

### [2026-04-13 16:40]

**Q:** DB 에서 슬라이드 관리 — AI Result 결과 유무 기록, slide_id, 메타데이터 등 관리.

**A:** **백엔드** — 신규 `backend/app/slide_store.py` 에 `slides` MongoDB 컬렉션 helper 추가: 스키마는 `str_slide_id`/`str_filename`/`str_rel_path`/`str_full_path`/`int_size_bytes`/`int_width`/`int_height`/`float_mpp`/`str_vendor`/`float_objective_power`/`str_uploaded_by`/`dt_uploaded_at`/`dt_last_opened_at`/`dict_ai_results`. `dict_ai_results` 는 `HE-Fit`/`PD-Score`/`Precise-IHC`/`VS-IHC` 각 모델별로 `{bool_has_result, list_variants, dt_updated_at}` 를 저장. Helper 함수: `upsert_slide`, `touch_last_opened`, `mark_ai_result`, `mark_ai_result_threadsafe` (백그라운드 스레드 → 메인 이벤트 루프 스케줄), `delete_slide`, `move_slide`, `rename_folder_in_db`, `list_slides_in_folder`, `serialize_slide_doc`. DB 미연결 시 모든 helper 는 no-op. `database.py` 에 `asyncio` import + `_main_loop` 캡처 + `get_main_loop()` + `slides` 컬렉션 인덱스 `(str_rel_path, str_filename)` unique + `str_slide_id` / `dt_last_opened_at` 추가. **슬라이드 라우터 훅** — `slides.py` 의 `_open_and_generate` 가 async 로 변환되고 `dict_user` 를 받아 `_upsert_and_attach` 통해 업서트, 응답에 `ai_results`/`uploaded_at` 부착. `/slides/open`, `/slides/upload/complete`, `/slides/open-local` 엔드포인트가 `Depends(get_current_user)` 로 사용자 주입. `/slides/browse` 는 `slide_store.list_slides_in_folder` 로 현재 폴더 DB 문서를 한 번에 가져와 각 슬라이드에 `ai_results` / `uploaded_by` / `last_opened_at` 부착. `/slides/file/move` → `slide_store.move_slide`, `/slides/folder/rename` → `slide_store.rename_folder_in_db` (하위 경로 모두 재작성). **AI 훅** — `ai.py` 의 HE-Fit (`_run_detection`), 공용 marker 파이프라인(`_run_marker_detection_pipeline` — `str_variant` 파라미터 추가, log_label 에서 `/` 앞부분을 모델 key 로 사용), VS-IHC (`_run_virtual_stain`) 의 캐시 저장 블록에서 `slide_store.mark_ai_result_threadsafe(info.file_path, model_key, variant)` 호출. `/save-result` 엔드포인트(async)는 `await slide_store.mark_ai_result(...)` 직접 호출. `_run_pd_score`/`_run_precise_ihc` 는 각각 `str_variant=tissue_type` / `str_variant=marker` 를 파이프라인에 전달. **프론트엔드** — `app.js` 의 `loadSlideList` 가 `s.ai_results` 를 읽어 완료된 모델별 컬러 닷(`.slide-ai-dot`) 을 슬라이드 아이템에 렌더 (H=보라, P=주황, I=빨강, V=초록). tooltip 에 variants 표시. `style.css` 에 `.slide-ai-badges` / `.slide-ai-dot` 스타일 (그리드 뷰에서는 absolute).

**변경사항**:

- 생성: backend/app/slide_store.py (`slides` 컬렉션 helper, threadsafe wrapper)
- 수정: backend/app/database.py (asyncio import, `_main_loop` 캡처, `get_main_loop`, slides 인덱스)
- 수정: backend/app/routers/slides.py (`_open_and_generate` async 변환, `_upsert_and_attach`, open/upload/open-local 에 `dict_user` 주입, `browse` ai_results 부착, move/rename 훅)
- 수정: backend/app/routers/ai.py (HE-Fit / 공용 marker pipeline / VS-IHC / save-result 캐시 저장 직후 `mark_ai_result` 호출, `_run_marker_detection_pipeline` 에 `str_variant` 파라미터, `_run_pd_score`/`_run_precise_ihc` 전달)
- 수정: frontend/js/app.js (`loadSlideList` AI 결과 배지 렌더링)
- 수정: frontend/css/style.css (`.slide-ai-badges`, `.slide-ai-dot` 그리드 뷰 오버레이)

### [2026-04-13 17:20]

**Q:** 폴더별 AI 자동 분석 — HnE 폴더에 HE-FIT Stomach / Other 를 설정하면, 그 폴더의 슬라이드 중 AI 결과가 없는 것을 백그라운드에서 자동 추론. 단 사용자 AI 작업이 10분간 없을 때만, 1분마다 스캔, 업로드 중엔 일시정지.

**A:** **백엔드** — 신규 `backend/app/auto_ai.py` 에 활동 추적 + 워커 루프 구현. 전역 `_last_ai_activity_ts` / `_upload_in_progress` / `_worker_task` 와 `ping_ai_activity()` / `upload_enter()` / `upload_exit()` / `is_system_idle()` helper. `is_system_idle` 은 (업로드 카운터 == 0) + (마지막 사용자 AI 활동 이후 `IDLE_THRESHOLD_SECONDS=600` 경과) + (ai 라우터 `_tasks` 중 queued/running 없음) 세 조건 모두 만족해야 True. `_worker_loop` 은 `SCAN_INTERVAL_SECONDS=60` 초마다 `_scan_and_infer_once` 호출 — DB 의 `folder_ai_configs` 중 enabled 인 config 를 순회하며 해당 폴더 슬라이드의 `dict_ai_results` 를 확인, 누락된 (model, variant) 에 대해서만 `_run_auto_inference` 실행. `_run_auto_inference` 는 `slide_manager.open` 후 `ai_router._run_detection/_run_pd_score/_run_precise_ihc` 를 `run_in_executor` 로 비동기 실행하고, task_id 는 `auto_` 접두어. 매 슬라이드 처리 전 `is_system_idle()` 재확인 — 사용자 활동 끼어들면 사이클 중단. **활동 훅** — `ai.py` 의 `_update_task` 가 호출될 때마다 `auto_ai.ping_ai_activity()` (단 `task_id.startswith("auto_")` 면 스킵 — 워커 자신의 활동으로 타이머가 리셋되지 않도록). `slides.py` 의 `/upload/chunk` 와 `/upload/complete` 를 `auto_ai.upload_enter/exit()` try/finally 로 감쌈. **folder_ai_configs 컬렉션** — `database.py` 에 `str_rel_path` unique + `bool_enabled` 인덱스. `slides.py` 에 신규 엔드포인트: `GET /slides/folder-config?path=...`, `POST /slides/folder-config` (path/enabled/tasks_json form), `DELETE /slides/folder-config` — 모델은 HE-Fit/PD-Score/Precise-IHC 만 허용, (model, variant) tuple 저장. **생명주기** — `main.py` lifespan 에 `await auto_ai.start_auto_worker()` / `await auto_ai.stop_auto_worker()` 추가. **프론트엔드** — `api.js` 에 `getFolderAiConfig`/`saveFolderAiConfig`/`deleteFolderAiConfig` 래퍼. `app.js` 폴더 우클릭 컨텍스트 메뉴에 "AI 자동 분석 설정..." 항목 추가, `openFolderAiConfigDialog` 이 6개 task 옵션(HE-Fit Stomach/Breast/Other, PD-Score Stomach/Lung, Precise-IHC HER2) 체크박스 + 활성화 토글 + 안내 hint 포함 모달. `style.css` 에 `.ai-cfg-*` 스타일 (backdrop + card + body + footer + primary 버튼).

**변경사항**:

- 생성: backend/app/auto_ai.py (활동 추적, idle 체크, 워커 루프, `_run_auto_inference`)
- 수정: backend/app/database.py (`folder_ai_configs` 인덱스)
- 수정: backend/app/routers/ai.py (`_update_task` 에서 `ping_ai_activity` — auto_ task 제외)
- 수정: backend/app/routers/slides.py (`auto_ai` import, upload 카운터 try/finally, `folder-config` GET/POST/DELETE, `json` import 상단 이동)
- 수정: backend/main.py (lifespan 에 worker start/stop)
- 수정: frontend/js/api.js (folder config 3 개 래퍼)
- 수정: frontend/js/app.js (컨텍스트 메뉴 항목, `openFolderAiConfigDialog`, `AUTO_AI_TASK_OPTIONS`)
- 수정: frontend/css/style.css (`.ai-cfg-*` 다이얼로그 스타일)


### [2026-04-13 17:45]
**Q:** Alt+드래그 라쏘로 셀 여러 개 선택해서 일괄 클래스 변경/삭제 가능하게 해줘
**A:** tile-viewer에 Alt+드래그 라쏘 인터랙션 추가 — mousedown 시 `_altPending` 으로 유보, 4px 이상 이동 시 `_lassoActive`=true 로 전환해 씬 좌표 라쏘 폴리곤 축적. mouseup 시 `_findCellsInPolygon`(ray-casting + SpatialGrid bbox prune, visibility/confidence 필터)으로 내부 셀 인덱스 수집 → `onCellsMultiEditRequested` 콜백 호출. 드래그 아닐 때(단순 Alt+Click)는 기존 `_findNearestCell` 경로. Esc 로 라쏘 취소. `_renderLasso`(점선 시안 폴리곤 + 반투명 채움), `_renderMultiCellHighlight`(선택 셀 클래스 색 원형) 추가. `deleteCells`/`changeCellsClass`/`clearMultiCellHighlight` 일괄 메서드 추가. app.js 에 `_showMultiCellEditPopup` (클래스별 집계 + 전체 클래스 버튼 + Delete N Cells) 팝업 신규. `_cellEditCtx.multi` 플래그로 기존 `_doDeleteCell`/`_doChangeClass` 가 단일/다중 분기.
**변경사항**:
- 수정: frontend/js/tile-viewer.js (`_altPending`, `_lassoActive`, `_lassoPoints`, `_highlightedCellIdxSet`, mousedown/mousemove/mouseup Alt 경로, `_pointInPolygon`, `_findCellsInPolygon`, `deleteCells`, `changeCellsClass`, `clearMultiCellHighlight`, `_renderMultiCellHighlight`, `_renderLasso`, Esc 취소)
- 수정: frontend/js/app.js (`_closeCellEditPopup` multi clear, `_doDeleteCell`/`_doChangeClass` multi 분기, `_showMultiCellEditPopup`, `viewer.onCellsMultiEditRequested`)

### [2026-04-13 18:05]
**Q:** AI 결과(셀 편집)에 대한 undo/redo 기능 추가
**A:** tile-viewer에 operation-based history 스택 추가 — `_undoStack`/`_redoStack` (max 200). `deleteCell`/`deleteCells`는 `{type:'delete', items:[{index, cell}]}` 기록, `changeCellClass`/`changeCellsClass`는 `{type:'changeClass', items:[{index, oldClassId, oldClassName, newClassId, newClassName}]}` 기록 후 적용. 새 편집마다 `_redoStack` 초기화, LIFO 순서로 인덱스 유효성 유지. `undoCellEdit()` — delete는 ascending index 로 splice-insert 복구, changeClass는 oldClass로 되돌림. `redoCellEdit()` — 반대. 두 경우 모두 highlight clear + `_refreshAfterCellEdit` (SpatialGrid/heatmap 재빌드) 호출. `setDetectionResults` 에서 스택 초기화. app.js에 키보드 훅: Ctrl+Z 는 undo, Ctrl+Shift+Z / Ctrl+Y 는 redo. 입력 위젯 포커스 중이면 무시, 실행 전 셀편집 팝업 close.
**변경사항**:
- 수정: frontend/js/tile-viewer.js (`_undoStack`/`_redoStack`/`_maxUndo`, `_pushUndoOp`, `deleteCell`/`deleteCells`/`changeCellClass`/`changeCellsClass` 기록 로직, `undoCellEdit`/`redoCellEdit`/`canUndoCellEdit`/`canRedoCellEdit`, `setDetectionResults` 스택 초기화, 기존 `changeCellClass` 중복 제거)
- 수정: frontend/js/app.js (Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y keydown 핸들러)

### [2026-04-13 18:30]
**Q:** 좌측 슬라이드 리스트에서 드래그로 여러개 선택 + 우클릭 컨텍스트 메뉴 (상태 설정 / 삭제). Delete 는 AI 결과도 같이 삭제되는 경고 팝업 (영문).
**A:** 백엔드: `slide_store` 에 `SET_SLIDE_STATUSES`(pending/in_progress/done/flagged/"")와 `set_slide_status` 추가. `browse` 응답에 `status` 필드 포함. `slides.py` 에 `_cleanup_ai_caches_for_stem`(ai_results/{HE-Fit,PD-Score,Precise-IHC,VS-IHC} + 레거시 루트에서 `{stem}_*` glob 으로 파일/폴더 삭제) + `_delete_slide_file`(파일 + 타일 피라미드 + AI 캐시 + DB 문서 일괄 제거, 열린 슬라이드는 사전 close). `POST /api/slides/file/delete` (filenames_json) 와 `POST /api/slides/file/status` 엔드포인트 신규. 프론트: `api.deleteFiles`/`api.setFileStatus` 래퍼. 슬라이드 아이템 렌더에 `status-{value}` 클래스 + 컬러 `slide-status-dot` 배지. 각 아이템 `contextmenu` 핸들러 → `showSlideContextMenu` (헤더에 파일명/개수, Set Status 5 옵션 + Delete). 전역 마키 선택: `$slideList` 빈영역 mousedown 에서 러버밴드 div 생성, mousemove 마다 교차 판정으로 selected 토글, Ctrl/Shift 는 baseline 유지. Delete 확인 팝업은 영문 ("All AI analysis results ... will also be permanently deleted. This action cannot be undone.").
**변경사항**:
- 수정: backend/app/slide_store.py (`SET_SLIDE_STATUSES`, `set_slide_status`)
- 수정: backend/app/routers/slides.py (browse 에 status, `_cleanup_ai_caches_for_stem`, `_delete_slide_file`, `/file/delete`, `/file/status`)
- 수정: frontend/js/api.js (`deleteFiles`, `setFileStatus`)
- 수정: frontend/js/app.js (status badge, contextmenu 훅, `showSlideContextMenu`, `_applyStatusToSelected`, `_deleteSelectedSlides`, marquee selection IIFE, 빈영역 contextmenu)
- 수정: frontend/css/style.css (`ctx-menu-header/label/sep/status`, `slide-status-dot`, `slide-marquee-rect`)

### [2026-04-13 18:50]
**Q:** PD-Score/Precise-IHC 는 confidence 0.1 로 표시되는데 초기 CPS/TPS/HER2 점수는 conf≥0.01 전체 셀로 계산되어 불일치. 점수도 0.1 필터로 계산해야 함.
**A:** `_run_marker_detection_pipeline` 에 `float_score_conf_threshold: float = 0.1` 파라미터 추가. `score_fn(all_cls)` 호출 전 `all_conf >= 0.1` 마스크로 필터링한 `cls_for_score` 를 넘김 — cells 리스트 전체는 그대로 저장하므로 사용자가 임계값을 낮추면 셀은 여전히 볼 수 있음. 결과 dict 에 `score_conf_threshold` 필드 추가. 캐시 로드 시 cached 의 `score_conf_threshold` 가 현재 임계값과 다르면 (= 레거시 캐시) cells 로부터 점수 재계산해서 덮어쓰기 → 기존 캐시도 자동 업데이트. HE-Fit 은 `_run_detection` 이 별도 경로라 영향 없음.
**변경사항**:
- 수정: backend/app/routers/ai.py (`_run_marker_detection_pipeline` signature + score 필터 + 캐시 재계산 로직, empty_result 에 threshold 필드)

### [2026-04-13 19:05]
**Q:** 시각화 PDF 저장 시 파일명 베이스가 "HE-Fit_Stomach" 으로 하드코딩되어 있음. 모델/variant 별로 유동적이어야 함.
**A:** `frontend/js/visualization.js` 의 PDF export filename 생성부를 수정. `state.modelType` (HE-Fit / PD-Score / Precise-IHC) 와 `state.tissue` (Stomach / Lung / HER2 등) 를 각각 sanitize 후 조합. variant 가 빈 문자열이면 모델명만 사용. `_vizState` 에 이미 두 필드가 저장되어 있고 caller (app.js showVisualization) 가 meta 로 넘기고 있어 백엔드/API 수정 불필요.
**변경사항**:
- 수정: frontend/js/visualization.js (PDF export filename dynamic base — `${safeName}_${modelType}_${tissue}_report.pdf`)

### [2026-04-13 19:30]
**Q:** report PDF 내용 자체도 모델별로 다르게 해야 함 (HE-Fit 전용 Tumor Analysis 페이지가 PD-Score/Precise-IHC 에도 그대로 나오는 문제).
**A:** `_exportPDF` 페이지 리스트를 `state.modelType` 기준으로 분기. HE-Fit: Cover/Class Dist/Tumor Analysis/Spatial Heatmap/Confidence (5p). PD-Score: Cover/Class Dist/CPS·TPS Analysis/Confidence (4p, Stomach=CPS+TPS 카드, Lung=TPS 단일 카드). Precise-IHC: Cover/Class Dist/HER2 Analysis/Confidence (4p, 게이지+intensity 분포). `_pdfDrawCover` 헤드라인 지표도 모델별 분기 — HE-Fit 은 Tumor Proportion, PD-Score(Stomach) 는 CPS, PD-Score(Lung) 는 TPS, Precise-IHC 는 dominant+/weighted. 제목도 모델+variant 반영. Class Dist/Confidence 페이지는 이미 `CLASS_NAMES`/`CLASS_COLORS` Proxy 로 `_activeNames`/`_activeColors` 를 읽고 있어서 수정 불필요.
**변경사항**:
- 수정: frontend/js/visualization.js (`_exportPDF` 페이지 라우팅, `_pdfDrawCover` 모델별 헤드라인, `_pdfDrawPdScoreAnalysis`/`_pdfDrawHer2Analysis` 신규 함수)

### [2026-04-13 19:45]
**Q:** CODIPAI-STBX-SS-04335-I-PD-22 슬라이드에 HE-Fit 배지 ('H' dot) 가 잘못 붙어있음. HE-Fit 마크 자체를 제거해달라.
**A:** 슬라이드 리스트 렌더링의 `modelMeta` 에서 `'HE-Fit'` 엔트리만 제거. 이제 리스트 배지는 PD-Score('P')/Precise-IHC('I')/VS-IHC('V') 만 표시됨. 기존 AI 결과 캐시 자체는 건드리지 않음 — 잘못 누적된 HE-Fit 결과 파일이 있어도 UI 에서는 더 이상 표시되지 않는다.
**변경사항**:
- 수정: frontend/js/app.js (slide list `modelMeta` 에서 HE-Fit 제거)

### [2026-04-13 19:55]
**Q:** 슬라이드 리스트 AI 결과 배지 (P/I/V 닷) 전부 제거해달라.
**A:** `renderSlideList` 에서 `s.ai_results` 기반 `slide-ai-badges` 생성 블록을 통째로 제거. 리뷰 상태 배지 (`slide-status-dot`) 는 유지.
**변경사항**:
- 수정: frontend/js/app.js (AI 결과 배지 렌더 블록 삭제)

### [2026-04-13 20:10]
**Q:** 리스트 배지는 auto AI 또는 수동 AI 진행중(queued/running)일 때만 표시하고 끝나면 사라져야 함.
**A:** 백엔드 task dict 에 `slide_filename/model/variant` 추가 (start_detection, start_pd_score, start_precise_ihc, start_virtual_stain, auto_ai._run_auto_inference). 신규 `GET /api/ai/active-tasks` 엔드포인트로 queued/running 상태만 `{filename: [{model,variant,status}]}` 형태로 반환. 프론트는 `loadSlideList` 후 `_refreshAiActiveBadges()` 호출 + 4초 interval polling. 각 슬라이드 아이템에 해당 filename 의 활성 task 가 있으면 `.slide-ai-active` 스피너 배지 부착, 없으면 제거 → 완료 시 자동으로 사라짐. CSS 에 회전 애니메이션 추가.
**변경사항**:
- 수정: backend/app/routers/ai.py (4개 start_* 엔드포인트 task dict 필드 확장, `/active-tasks` 엔드포인트 추가)
- 수정: backend/app/auto_ai.py (`_run_auto_inference` task dict 에 filename/model/variant 추가)
- 수정: frontend/js/api.js (`getActiveAiTasks()` 래퍼)
- 수정: frontend/js/app.js (`_refreshAiActiveBadges` + 4s polling interval)
- 수정: frontend/css/style.css (`.slide-ai-active` 스피너 + keyframes)

### [2026-04-13 20:25]
**Q:** 폴더 AI 자동분석 설정 옵션에 VS-IHC 가 누락되어 있음.
**A:** `AUTO_AI_TASK_OPTIONS` 에 `VS-IHC · Membrane` 항목 추가 (variant = `ihc_membrane`). 백엔드 `_run_auto_inference._dispatch` 에도 VS-IHC 분기 추가 — `_run_virtual_stain(task_id, slide_id, None, stain_type, 2.0)` 호출. 현재 VS_MODEL_FILES 에는 `ihc_membrane` 1종만 있어 단일 옵션.
**변경사항**:
- 수정: frontend/js/app.js (`AUTO_AI_TASK_OPTIONS` 에 VS-IHC 항목 추가)
- 수정: backend/app/auto_ai.py (`_dispatch` VS-IHC 분기)

### [2026-04-13 20:40]
**Q:** VS-IHC 체크하면 어떤 배율 (target_mpp) 로 돌릴지도 하위 체크로 선택 가능해야 함. 또 ihc_nucleus 도 있음.
**A:** `AUTO_AI_TASK_OPTIONS` 에 `ihc_nucleus` 추가 + VS-IHC 옵션에 `mpp: true` 플래그. 다이얼로그 VS-IHC 행은 상위 체크 시 하위 배율 체크박스 4개 (4.0/2.0/1.0/0.5 µm/px) 가 나타나도록 렌더. 기본 체크는 저장된 mpp 또는 2.0. 저장 시 체크된 mpp 당 task 하나씩 생성 (`{model:'VS-IHC', variant, target_mpp}`). 백엔드 `save_folder_config` 의 allowed models 에 `VS-IHC` 추가, `target_mpp` 필드 저장/반환. auto_ai 는 VS-IHC 의 경우 `_get_vs_cache_paths(path, variant, mpp)` 의 PNG 존재 여부로 per-mpp 스킵 판단 후 `_run_virtual_stain(..., float_target_mpp)` 호출.
**변경사항**:
- 수정: frontend/js/app.js (VS-IHC mpp 하위 체크박스 + 다중 task 저장)
- 수정: frontend/css/style.css (`.ai-cfg-sub` 하위 섹션 스타일)
- 수정: backend/app/routers/slides.py (folder-config VS-IHC + target_mpp 허용)
- 수정: backend/app/auto_ai.py (`_run_auto_inference` target_mpp 인자, VS-IHC per-mpp 캐시 스킵)

### [2026-04-13 20:55]
**Q:** AI Analysis 패널 헤더 옆에 `?` 아이콘 추가, hover 시 현재 활성 탭의 모델 설명 툴팁 표시.
**A:** `panel-header` 에 `#ai-help-icon` `.help-icon` span 추가 (flex 정렬). `AI_MODEL_HELP` dict 에 4개 탭 (hne/vs/pd/ihc) 별 title + body 설명 정의. mouseenter/focus 시 `.tab-btn.active` 의 dataset.tab 으로 해당 설명을 fixed-position 툴팁에 렌더. leave/blur 시 숨김. CSS 로 dark theme 툴팁 + `.help-icon` 원형 버튼 스타일 추가.
**변경사항**:
- 수정: frontend/app.html (panel-header 에 `#ai-help-icon` 추가)
- 수정: frontend/js/app.js (`AI_MODEL_HELP`, `_showAiHelpTooltip`/`_hideAiHelpTooltip`)
- 수정: frontend/css/style.css (`.help-icon`, `.ai-help-tooltip` + `.panel-header` flex)

### [2026-04-13 21:10]
**Q:** 슬라이드 열면 상단 이름 옆에 스캐너 정보 + 스캐너 로고 표시해달라.
**A:** 상단 menubar `.menu-center` 에 `#slide-scanner` 배지 span 추가. `onSlideLoaded` 에서 `slideInfo.vendor` (openslide vendor 문자열) 로 `SCANNER_META` 매핑을 조회해 인라인 SVG 로고 + magnification + MPP 를 pill 형태로 표시. 지원 vendor: Hamamatsu/Aperio/Leica/3DHistech(MIRAX)/Philips/Ventana/Sakura/Olympus. 매칭 실패 시 vendor 원문을 텍스트로 fallback. 별도 이미지 asset 없이 SVG 를 JS 에 인라인해서 에셋 추가 없이 동작. `backend/app/routers/slides.py` 의 slide info 응답에는 이미 `vendor/objective_power/mpp_x` 가 포함되어 있어 백엔드 수정 불필요.
**변경사항**:
- 수정: frontend/app.html (`#slide-scanner` span 추가)
- 수정: frontend/js/app.js (`SCANNER_META`, `_updateScannerBadge`, `onSlideLoaded` 호출)
- 수정: frontend/css/style.css (`.slide-scanner`, `.scanner-logo`, `.scanner-info` 스타일)

### [2026-04-13 저장 진단]
**Q:** AI 자동분석 설정 VS-IHC 설정이 저장안돼
**A:** 프론트 `openFolderAiConfigDialog` 저장/로드 경로에 `console.log('[ai-cfg] load'/'save'/'save resp', ...)` 디버그 로그 추가. 코드 경로 자체(dataset.model/variant, .ai-cfg-parent/.ai-cfg-mpp 선택, parseFloat, tasks_json FormData 전송, 백엔드 VS-IHC 허용 + target_mpp 파싱)는 정상으로 보이며, 실제 실패 원인을 브라우저 콘솔에서 추적할 수 있도록 지원.
**변경사항**:
- 수정: frontend/js/app.js (openFolderAiConfigDialog 디버그 로그 3곳 추가)

### [2026-04-13 저장 진단 — 해결]
**Q:** 재시작하니 되네
**A:** 원인은 백엔드 uvicorn 프로세스가 VS-IHC 허용 코드 반영 이전 상태였음. 재시작 후 정상 저장 확인. 디버그용 `console.log('[ai-cfg] ...')` 3개 제거.
**변경사항**:
- 수정: frontend/js/app.js (디버그 로그 제거)

### [2026-04-13 로그인 전 401 정리]
**Q:** /api/ai/active-tasks, /api/slides/browse 가 401 로 뜨는 원인 설명 및 수정
**A:** 기존 `loadSlideList()` 와 `api.me()` 호출이 스크립트 최상단에서 독립적으로 즉시 실행돼 로그인 확인 이전에 401 을 발생시켰음. 둘을 하나의 async IIFE 로 합쳐서 `api.me()` 성공 후에만 `loadSlideList()` → `_startAiActivePolling()` 흐름이 시작되도록 변경. 로그아웃 버튼에서 `_stopAiActivePolling()` 을 먼저 호출해 4초 폴링 타이머를 즉시 중지. `.well-known/appspecific/com.chrome.devtools.json` 404 는 Chrome DevTools 자동 탐색으로 무해.
**변경사항**:
- 수정: frontend/js/app.js (`_stopAiActivePolling` 추가, 로그아웃 핸들러 폴링 중지, init IIFE 로 인증 게이팅)

### [2026-04-13 스캐너 배지 위치 이동]
**Q:** 스캐너 정보는 줌상태바로왼쪽으로 이동해줘
**A:** `#slide-scanner` span 을 `.menu-center` 에서 툴바 우측의 zoom-info 바로 왼쪽(`toolbar-group` 내부, `#zoom-info` 앞)으로 이동. 툴바 컨텍스트에 맞게 padding 을 5px/12px → 4px/10px 로 소폭 축소하고 `margin-right: 10px` 로 줌 표시와 간격 확보.
**변경사항**:
- 수정: frontend/app.html (slide-scanner span 이동)
- 수정: frontend/css/style.css (.slide-scanner 여백/패딩 조정)

### [2026-04-13 폴더 단일 클릭 진입]
**Q:** 폴더 들어갈때 더블클릭말고 클릭으로 들어갈수 있게 해줘
**A:** slide-list 의 folder-item 에 걸려있던 `dblclick` 리스너를 `click` 으로 변경.
**변경사항**:
- 수정: frontend/js/app.js (folder-item dblclick → click)

### [2026-04-13 툴바 정리]
**Q:** 상단 툴바 정리 — Save Results 버튼 제거
**A:** 툴바의 `#btn-save` 버튼은 실제로 annotation 다운로드 핸들러(`_downloadAnnotations`)에 연결돼 있어 우측 Annotations 패널의 Save 버튼과 기능 중복이었음. 버튼 DOM + `$btnSave` 참조 + click 리스너 + disabled 토글 제거.
**변경사항**:
- 수정: frontend/app.html (#btn-save 버튼 제거)
- 수정: frontend/js/app.js ($btnSave 관련 3곳 제거)

### [2026-04-13 좌측 패널/로고 폭 동기화]
**Q:** 좌측 슬라이드 패널을 리사이즈할 때 위 로고 영역(menu-left)도 같이 크기 조정되게 해줘
**A:** `--left-panel-w` CSS 변수(:root, 기본 240px)를 도입해 `.menu-left`, `#menubar::after`, `#left-panel` 가 공통으로 참조하도록 변경. 리사이저 드래그 핸들러는 `$leftPanel.style.width` 직접 설정 대신 `document.documentElement.style.setProperty('--left-panel-w', ...)` 로 변수를 갱신 → 로고 영역과 좌측 패널이 같은 폭으로 함께 리사이즈됨. 최소 폭도 140 → 160 으로 통일.
**변경사항**:
- 수정: frontend/css/style.css (--left-panel-w 변수 + 3곳 참조)
- 수정: frontend/js/app.js (리사이저 핸들러가 CSS 변수 갱신)

### [2026-04-13 툴바 좌측 오프셋 동기화]
**Q:** 툴바도 같이 가야지 (좌측 패널 리사이즈 시 툴바의 좌측 다크 컬럼/패딩도 따라오도록)
**A:** `#toolbar` padding-left, `::before` width, `::after` left 의 하드코딩 240px 를 `var(--left-panel-w)` / `calc(var(--left-panel-w) + 14px)` 로 교체. 좌측 패널 리사이즈 시 툴바의 다크 사이드바 컬럼과 버튼 시작 위치가 함께 조정됨.
**변경사항**:
- 수정: frontend/css/style.css (#toolbar 3곳 변수화)

### [2026-04-13 썸네일 크기 Ctrl+휠 조정]
**Q:** 좌측 슬라이드 리스트에서 마우스 휠에 따라 썸네일 이미지 크기 변경
**A:** 일반 휠은 리스트 스크롤과 충돌하므로 **Ctrl+Wheel**(Windows Explorer 방식)로 구현. 리스트/그리드 모드 각각 별도 범위: 리스트 28~96px (6px step), 그리드 60~200px (10px step). CSS 변수 `--slide-thumb-list`/`--slide-thumb-grid` 를 도입해 `.slide-thumb` 와 `.slide-list.grid-view` grid-template-columns(=썸네일+10px 최소) 에서 참조. 값은 localStorage (`thumbSizeList`/`thumbSizeGrid`) 에 저장해 재로드 시 복원.
**변경사항**:
- 수정: frontend/css/style.css (CSS 변수 2개 + .slide-thumb 하드코딩 교체)
- 수정: frontend/js/app.js (Ctrl+wheel 핸들러 + restoreThumbSizes)

### [2026-04-14 On-Prem 보안 강화 3종]
**Q:** 일단 한동안은 on-premise 로 진행할거니까 외부 접근 관련된건 빼고 보안 수정
**A:** 외부 공개와 관련된 CORS/HTTPS/rate-limit/CSP 는 건너뛰고, on-prem 에서도 반드시 필요한 3가지만 처리.
 1) **시크릿 영속화** — `backend/.secrets.json` 자동 생성/로드. 환경변수 `JWT_SECRET_KEY`/`FIELD_ENCRYPTION_KEY` 가 있으면 그대로 사용, 없으면 파일의 값 사용. 서버 재시작 시에도 키가 유지되어 기존 토큰/암호화 필드가 깨지지 않음. 파일 권한 0600.
 2) **업로드 크기 상한** — `Settings.MAX_UPLOAD_BYTES` (기본 20 GB, 환경변수 오버라이드 가능). `upload_complete` 에서 청크 조립 전 선집계해 초과 시 413.
 3) **업로드 실패 파일 정리** — `upload_complete` 에서 확장자 재검증 추가 + OpenSlide 오픈 실패(손상/위조) 시 이번 업로드로 디스크에 기록한 파일만 삭제 (기존 파일은 보존).
 .gitignore 에 `/backend/.secrets.json` 과 `.env` 추가.
**변경사항**:
- 수정: backend/app/config.py (_load_or_create_secrets + MAX_UPLOAD_BYTES)
- 수정: backend/app/routers/slides.py (upload_complete 검증/정리 강화)
- 수정: .gitignore (.secrets.json, .env)

### [2026-04-13 14:00]
**Q:** auto_ai 가 폴더 안의 모든 슬라이드를 메모리에서 필터링하는데, DB 에서 AI 결과 없는 애들만 골라 질의할 수 있지 않나?
**A:** slide_store 에 `list_slides_missing_variant(rel_path, model, variant)` 추가 — `dict_ai_results.{model}.list_variants` 에 `$ne` 질의로 누락 슬라이드만 가져옴. auto_ai `_scan_and_infer_once` 를 "task 단위로 후보 조회 → 순회" 구조로 리팩토링. VS-IHC 는 target_mpp 가 DB 에 없어 기존 per-mpp 파일 체크 유지.
**변경사항**:
- 수정: backend/app/slide_store.py (list_slides_missing_variant 추가)
- 수정: backend/app/auto_ai.py (_scan_and_infer_once task-first 루프)

### [2026-04-14 10:30]
**Q:** Aperio 라고 표시하지 말고 Leica 로 표시하고, ICC profile 있으면 적용해서 보여줘
**A:** 프론트 SCANNER_META 의 'aperio' 키 라벨/SVG 를 Leica 로 교체. 백엔드는 openslide ≥1.3 의 `slide.color_profile` 에서 ICC bytes 를 추출해 SlideInfo 에 캐싱하고, 모든 JPEG 저장 경로(tile_generator, tiles 라우터, slides 의 썸네일/프리뷰 핸들러)에서 `Image.save(..., icc_profile=bytes)` 로 임베드 → 브라우저가 색 보정.
**변경사항**:
- 수정: frontend/js/app.js (SCANNER_META.aperio → Leica)
- 수정: backend/app/slide_manager.py (icc_profile_bytes 캐싱)
- 수정: backend/app/tile_generator.py (썸네일/타일 ICC 임베드)
- 수정: backend/app/routers/tiles.py (즉석 타일 ICC 임베드)
- 수정: backend/app/routers/slides.py (썸네일/프리뷰 핸들러 ICC 임베드)

### [2026-04-14 10:50]
**Q:** 타일 요청이 401 Unauthorized 로 줄줄이 실패. 왜?
**A:** 타일/썸네일 URL 은 `<img src>` 로 직접 로드되어 `_authFetch` 의 사전 refresh 가 안 돈다. 사용자가 15분(access TTL) 이상 idle 후 새 타일 요청 시 만료된 토큰이 query string 에 박혀 401. api.js 에 30초 주기 백그라운드 refresh 타이머(`_startBackgroundTokenRefresh`) 추가 — 만료 임박이면 사전 갱신. logout 에서 타이머 정리.
**변경사항**:
- 수정: frontend/js/api.js (백그라운드 token refresh 타이머)

### [2026-04-14 11:10]
**Q:** ICC 임베드 방식이 너무 느리고 렉이 심함 → 타일 생성 시 sRGB 변환 방식으로 바꿔달라
**A:** SlideInfo 에 `icc_profile_bytes` 대신 `icc_transform`(ImageCms.buildTransform 캐싱)을 보관하고 `apply_icc()` 헬퍼 추가. tile_generator/tiles 라우터/slides 라우터 썸네일 모두 픽셀을 한 번 sRGB 로 변환 후 plain JPEG 로 저장 → ICC blob (수 MB) 이 모든 타일에 박히던 IO 폭증 해소. 기존 캐시는 사용자가 tiles/ 비우면 새 방식으로 재생성됨.
**변경사항**:
- 수정: backend/app/slide_manager.py (icc_transform + apply_icc)
- 수정: backend/app/tile_generator.py (sRGB 픽셀 변환)
- 수정: backend/app/routers/tiles.py (apply_icc 사용)
- 수정: backend/app/routers/slides.py (썸네일/프리뷰 ICC 픽셀 변환)
### [2026-04-14 15:54]
**Q:** `./start.sh` 실행 시 `jose.py` SyntaxError 및 이후 Python 3.9 타입힌트 오류로 서버 기동 실패
**A:** conda 환경에서 잘못 설치된 `jose`(1.0.0)를 제거하고 `python-jose[cryptography]`/`motor`를 설치해 인증/DB import 오류를 해결. 이어서 `backend/app/tile_generator.py`의 `dict | None` 반환 타입을 `Optional[dict]`로 변경해 Python 3.9 런타임 타입 평가 오류를 제거. 최종적으로 `./start.sh` 재실행 시 Uvicorn/FastAPI가 정상 기동됨(타임아웃으로 테스트 종료).
**변경사항**: backend/app/tile_generator.py, claudy_log.md

### [2026-04-14 15:47]
**Q:** `./start.sh` 실행 시 `conda activate` 관련 `CommandNotFoundError` 발생
**A:** `start.sh`에서 `conda activate "$ENV_NAME"` 줄을 제거하고 `conda run -n "$ENV_NAME" ...`만 사용하도록 수정. 비초기화 셸(`conda init` 미적용)에서도 동일하게 서버 실행 가능.
**변경사항**: start.sh, claudy_log.md

### [2026-04-14 15:44]
**Q:** `start.bat` 기반으로 실행용 sh 파일 생성
**A:** Windows 배치 스크립트와 동일 동작의 `start.sh`를 루트에 추가. 스크립트 경로 기준으로 `backend` 이동, conda 설치 여부/환경(`medicus-saas`) 존재 여부 검사 후 `conda run`으로 `uvicorn main:app --host 0.0.0.0 --port 8092` 실행하도록 구성.
**변경사항**: start.sh, claudy_log.md

### [2026-04-14 02:10]
**Q:** ER/PR 버튼 임시 비활성화 + 자동 AI 설정 다이얼로그에서도 숨김
**A:** `app.html`의 `#btn-ihc-erpr`에 `hidden` 속성 추가 + `disabled` 유지. `app.js`의 슬라이드 로드 시 버튼 enable 라인(`$btnIhcErPr.disabled = false`)과 `AUTO_AI_TASK_OPTIONS` 의 ER_PR 항목을 주석 처리(삭제가 아니라 복구 쉽게). 코드/config 자체는 남겨둠.
**변경사항**: frontend/app.html, frontend/js/app.js

### [2026-04-14 02:05]
**Q:** 3-way union 으로도 내부 패치가 잘림 — 컨투어로 묶어서 내부 홀은 통째로 tissue 처리
**A:** 픽셀 단위 임계값 튜닝을 포기하고 영역 기반 접근으로 전환. union mask → **25x25 CLOSE 로 인접 조각 병합** → `cv2.findContours(RETR_EXTERNAL)` 로 외곽 컨투어 추출 → 면적이 썸네일의 0.05% 미만(min 50px)인 노이즈 컨투어 드랍 → `drawContours(FILLED)` 로 솔리드 채움. 결과적으로 컨투어 내부의 모든 구멍(염색 옅은 세포간 공간, DAB-sparse 영역)이 전부 tissue 로 포함되어 AI 패치 수집 단계에서 잘리지 않음.
**변경사항**: backend/app/routers/ai.py

### [2026-04-14 02:00]
**Q:** H 채널 Otsu 로 좀 나아졌지만 아직도 빠트리는 영역이 있음
**A:** 단일 Hem Otsu 만으로는 (1) DAB 가 강하게 덮여 H 가 억제된 영역, (2) 염색이 옅지만 구조가 있는 조직이 빠질 수 있음. `_create_tissue_mask` 를 `virtual_stain.py::_build_tissue_grid` 의 3-way 방식으로 확장: **Hem Otsu ∪ DAB Otsu ∪ 국소std Otsu** 후 확실한 유리 배경(그레이 히스토그램 최고 피크의 95% 이상) 강제 제외. 국소 표준편차(15x15 blur 기반)는 무염색이지만 세포 구조가 있는 영역을 잡아주고, DAB Otsu 는 H 가 suppressed 된 고염색 영역을 보완함.
**변경사항**: backend/app/routers/ai.py

### [2026-04-14 01:55]
**Q:** DAB 갈색 부분 제외하고 Otsu 돌리는 방식으로 조직 마스크 개선
**A:** `_create_tissue_mask` 를 H-DAB Color Deconvolution (Ruifrok & Johnston 2001) 방식으로 교체. RGB → OD → `inv(stain_matrix)^T` 곱셈으로 Hematoxylin / DAB / Residual 3채널 분리, **Hematoxylin OD 채널만** Otsu 임계처리. 99.5 percentile 로 클리핑해 outlier 영향 제거. 이렇게 하면 DAB 갈색 강도 편차가 임계값 결정에 개입하지 않아 옅은 hematoxylin counterstain 영역(DAB 없는 조직)도 안정적으로 잡힘. HE 슬라이드는 원래 hematoxylin 이 주염색이라 동일 방식 그대로 잘 작동. Stain matrix 는 `virtual_stain.py::_build_tissue_grid` 와 동일 값 사용.
**변경사항**: backend/app/routers/ai.py

### [2026-04-14 01:50]
**Q:** `_create_tissue_mask` 의 Otsu 변경 롤백 — 고정 임계값(원래 방식) 으로 복원
**A:** Saturation + Gray Otsu union 방식 제거하고 기존 `cv2.threshold(255-gray, 30, 255, THRESH_BINARY)` 고정 임계값으로 되돌림. ICC profile 파라미터(`icc_transform=None`) 는 유지 — 이 부분은 다른 AI 경로와 일관성 있게 필요한 수정이라 그대로 둠. 호출부(`_run_detection`, `_run_marker_detection_pipeline`) 의 `info.icc_transform` 전달도 유지.
**변경사항**: backend/app/routers/ai.py

### [2026-04-14 01:45]
**Q:** `_create_tissue_mask` 에도 ICC profile 적용되는지 확인
**A:** 안 돼 있었음. 다른 AI 경로(`_read_patch_tensor`, `_build_seg_overlays`)는 최근 ICC 연결 완료했는데 이 함수만 누락. ICC 없으면 Aperio SVS 같이 embedded profile 있는 슬라이드에서 색상(특히 HSV 채도)이 뷰어 표시와 달라져 Saturation Otsu 임계값이 흔들릴 수 있음. 수정: `_create_tissue_mask(slide, icc_transform=None)` 로 선택 인자 추가, 썸네일을 PIL 로 받아 `ImageCms.applyTransform` inPlace 적용 후 np.array 변환. `_run_detection`(HE-Fit), `_run_marker_detection_pipeline`(PD-Score/Precise-IHC) 양쪽 호출부에서 `info.icc_transform` 전달.
**변경사항**: backend/app/routers/ai.py

### [2026-04-14 01:40]
**Q:** IHC 모델(PD-Score/Precise-IHC/VS-IHC)만 추론 영역 중 특정 부분이 빠짐 — HE-Fit 은 정상
**A:** 원인은 `_create_tissue_mask` 의 고정 임계값 `cv2.threshold(255-gray, 30, ...)` — gray<225 만 조직으로 인정. IHC 는 hematoxylin counterstain 이 옅어서 이 임계값을 넘는 영역이 통째로 배경 취급됨. HE 는 염색이 진해서 문제없음. 수정: **HSV Saturation Otsu ∪ Gray Otsu** 방식으로 교체. IHC 염료(DAB 갈색/Fast Red/AEC)는 채도가 높아 S-Otsu 로 검출되고, 진염색 영역은 Gray-Otsu 로 보완. 순수 유리 배경(S<15 AND V>220)만 강제 제외. `_run_detection`(HE-Fit), `_run_marker_detection_pipeline`(PD-Score/Precise-IHC) 가 공유하는 함수라 HE 에도 영향이지만 Otsu 는 HE 슬라이드에서도 더 정확하므로 안전. VS-IHC 는 별도의 `_build_tissue_grid`(color deconv + texture) 를 사용하므로 이 수정 범위 밖 — 테스트 후 동일 증상이면 추가 조치 필요.
**변경사항**: backend/app/routers/ai.py

### [2026-04-14 01:35]
**Q:** Precise-IHC ER/PR 버튼 통합 — 실제로 동일 모델이라 분리 의미 없음
**A:** `PRECISE_IHC_CONFIG` 에서 "ER"/"PR" 두 엔트리를 하나의 "ER_PR" 로 병합 (동일한 `Precise_IHC_ER_PR_detection.pt` 사용). 프론트 `btn-ihc-er`/`btn-ihc-pr` 두 개 → 단일 `btn-ihc-erpr` ("ER/PR") 로 교체. `app.js` 의 `$btnIhcEr`/`$btnIhcPr` 참조 전부 `$btnIhcErPr` 로 통일, `startPreciseIhc('ER_PR')` 호출, 표시 라벨은 `markerLabel = 'ER_PR' → 'ER/PR'` 로 포맷. `AUTO_AI_TASK_OPTIONS` 에서도 두 항목 합침. 백엔드 `_run_precise_ihc` 의 score_fn 분기 `marker in ("ER","PR")` → `marker == "ER_PR"`. 캐시 파일명은 `{slide}_Precise-IHC_ER_PR.json` 로 생성됨. visualization.js 는 `_activeScoreType === 'Allred'` 로 분기하므로 수정 불필요.
**변경사항**: backend/app/routers/ai.py, frontend/app.html, frontend/js/app.js

### [2026-04-14 01:30]
**Q:** `/api/ai/task/null/cancel` 및 `/api/ai/task/{id}/cancel` 에서 405 Method Not Allowed
**A:** 두 가지 원인. (1) 백엔드 서버 재시작 필요 — cancel 엔드포인트 추가 이전 코드로 실행 중이라 라우트가 없고, `main.py`의 `StaticFiles("/")` 마운트가 매칭 실패한 POST 를 받아 405 반환. (2) `task/null/cancel` 은 프론트 버그 — 사용자가 AI 시작 직후 `task_id` 가 서버에서 돌아오기 전에 재클릭하면 `_runningAiTasks[key].task_id` 가 아직 `null` 인데 그대로 URL 에 박아 전송. 수정: `_maybeCancelRunning`에 `task_id` null 체크 추가 → `pending_cancel` 플래그만 세팅, 4개 start 핸들러 모두 `task_id` 수신 직후 `pending_cancel` 검사해서 즉시 `cancelTask` 호출. 사용자는 백엔드 수동 재시작 필요.
**변경사항**: frontend/js/app.js

### [2026-04-14 01:25]
**Q:** VS-IHC 취소 cleanup 에 타일 폴더는 왜 삭제하지?
**A:** 버그 지적. (1) VS 타일 피라미드는 PNG 저장 **완료 후** `_generate_vs_tiles`가 만들며 그 단계엔 `_check_cancel`가 없어서 "부분 생성" 상태가 존재할 수 없음 → 정리할 필요 없음. (2) 더 큰 문제는 `list_cleanup_on_cancel.extend([png, meta, tile_dir])`을 함수 초반에 무조건 등록해서, **캐시 hit 로딩 중 취소**하면 기존 완전한 캐시(PNG + 타일 피라미드)까지 날려버림. 수정: 함수 초반 등록 제거, 새 추론이 실제로 `png_path`/`meta_path`에 쓰기 **직전**에만 `[png_path, meta_path]` 등록, 타일 디렉터리는 목록에서 제외.
**변경사항**: backend/app/routers/ai.py

### [2026-04-14 01:20]
**Q:** 모든 AI 모델 버튼 — 실행 중 다시 클릭하면 중지되게, 중지 시 지금까지 저장된 ai_results도 삭제해서 나중 충돌 방지 (옵션 B: 백엔드 협조적 취소)
**A:** 백엔드 `ai.py`에 `TaskCancelled` 예외 + `_is_cancel_requested`/`_check_cancel` + `_cleanup_cache_paths` 추가, `POST /api/ai/task/{id}/cancel` 엔드포인트로 `cancel_requested` 플래그 세팅. 4개 워커(`_run_detection`, `_run_marker_detection_pipeline` (PD-Score+Precise-IHC), `_run_virtual_stain`) 의 I/O 프로듀서 루프·GPU 배치 루프·저장 직전에 `_check_cancel` 체크포인트, `except TaskCancelled` 핸들러가 `list_cleanup_on_cancel` 에 등록된 캐시 파일/JSON/타일 피라미드 폴더를 모두 삭제 후 status='cancelled'. 프론트 `api.js`에 `cancelTask(taskId)`, `app.js` 에 `_runningAiTasks` 맵 + `_setButtonRunning` + `_maybeCancelRunning` 헬퍼, 4개 핸들러(`startDetection`/`startVirtualStain`/`startPdScore`/`startPreciseIhc`) 모두 동일 패턴으로 리팩토 — 실행 중 재클릭하면 취소 요청, 폴링에서 `status==='cancelled'` 처리, finally 에서 `_runningAiTasks` 엔트리 삭제 및 버튼 상태 복원. `style.css` 에 `.ai-btn-running` 빨간 펄스 애니메이션.
**변경사항**: backend/app/routers/ai.py, frontend/js/api.js, frontend/js/app.js, frontend/css/style.css

### [2026-04-14 01:10]
**Q:** 폴백 적용되긴 하는데 최초 로딩 순간(최대 축소) 격자가 잠깐 보임
**A:** 첫 렌더(fitToWindow 직후)에 썸네일 네트워크 응답이 아직 도착 전이라 생기는 flash. `_loadThumbnailFallback` 에 0단계 추가 — `document.querySelector('.slide-list-item[data-slide-id="..."] .slide-thumb')` 로 사이드바가 이미 로드해둔 96px `<img>` DOM 엘리먼트를 즉시 훔쳐 `_thumbnailBitmap` 에 대입. 네트워크 0ms, 첫 렌더에 바로 가용. 그 뒤 300/2048 로 순차 업그레이드.
**변경사항**: frontend/js/tile-viewer.js

### [2026-04-14 01:05]
**Q:** 썸네일 폴백 적용했는데도 여전히 격자 보임
**A:** 원인 — `previewUrl(2048)` 은 on-demand 생성이라 SVS 에서 수 초 걸려 초기 확대 순간엔 `_thumbnailBitmap` 이 여전히 null. 2단 로딩으로 수정: (1) `thumbnailUrl(300)` — 디스크 캐시라 즉시 응답, 즉시 블러 폴백 가용. (2) 같은 자리에서 `previewUrl(2048)` 도 병렬 요청 → 도착하면 자동 업그레이드. slideId 변경 체크로 슬라이드 전환 중 레이스 방지.
**변경사항**: frontend/js/tile-viewer.js

### [2026-04-14 01:00]
**Q:** Hamamatsu는 zoom 레벨 불러올 때 빈 격자무늬가 없는데 Leica는 생김 — 썸네일 전역 폴백
**A:** Leica SVS는 level_count=3이라 `_preloadCoarsestLevel()`이 큰 최상위 레벨(수백 타일)을 큐에 넣는데 완료 전에 사용자가 확대하면 `_findFallbackTile`이 miss → 빈 격자 노출. `loadSlide()`에서 `api.previewUrl(slideId, 2048)` 한 장을 `this._thumbnailBitmap`으로 1회 로드하고, `_render()` 폴백 경로에서 pyramid fallback 도 없을 때 scene 좌표→썸네일 좌표 매핑으로 해당 영역을 스케일해 그림. 타일이 실제로 도착하면 자동으로 덮여짐.
**변경사항**: frontend/js/tile-viewer.js

### [2026-04-14 00:50]
**Q:** 뷰어 타일링이 level 0만 하던 문제 — 줌 stage level 전부 프리생성으로 변경
**A:** `tile_generator._generate_tiles`를 SlideInfo._setup_level_stages와 동일한 4단계(중복 제거) 레벨을 모두 생성하도록 수정. 거친 레벨(높은 인덱스)부터 역순으로 → 뷰어 첫 화면이 가장 빠르게 채워짐. `progress.total_tiles`도 모든 stage level 합으로 계산.
**변경사항**: backend/app/tile_generator.py

### [2026-04-14 00:40]
**Q:** 슬라이드 DB에 뷰어 타일링 완료 여부 추가, 미완이면 auto_ai보다 우선, 타일링은 사용자 활동 무관 백그라운드 지속 실행
**A:** slides 컬렉션에 `bool_tiles_ready`/`dt_tiles_ready_at` 필드 추가. `slide_store`에 `mark_tiles_ready` (async+threadsafe), `list_slides_missing_tiles`, `has_any_pending_tiles` helper 추가. `tile_generator._generate_tiles` 완료 hook에서 `mark_tiles_ready_threadsafe` 호출. 신규 `app/tile_worker.py` 워커를 20초 주기로 스캔해 미완료 슬라이드의 타일을 `run_in_executor`로 순차 생성 — idle/activity 체크 없음. `main.py` lifespan에서 tile_worker → auto_ai 순으로 시작. `auto_ai._scan_and_infer_once`의 사이클 시작과 슬라이드 간 분기점 모두에 `has_any_pending_tiles()` 체크 추가 → 타일 미완료 시 AI 추론 보류.
**변경사항**: backend/app/slide_store.py, backend/app/tile_generator.py, backend/app/tile_worker.py(신규), backend/app/auto_ai.py, backend/main.py

### [2026-04-14 00:30]
**Q:** 타일링 완료 전 확대 시 빈 셀로 보이는 문제 — 최상위 레벨 전체 프리로드(A안)
**A:** `tile-viewer.js::loadSlide()`에서 `fitToWindow()` 직후 `_preloadCoarsestLevel()` 호출. `level_count - 1`의 모든 타일(보통 1~16장)을 `_loadTile`로 즉시 큐잉해 캐시에 넣음 → `_findFallbackTile()`이 어디로 확대하든 항상 블러 업스케일 fallback을 얻을 수 있게 됨.
**변경사항**: frontend/js/tile-viewer.js

### [2026-04-14 00:20]
**Q:** AI 추론 때문에 뷰어 타일링이 뒷전이 된다 — 타일링 우선순위를 높여달라
**A:** `app/priority.py` 신설: `notify_viewer_activity()` / `wait_if_viewer_busy()` 로 1.2초 grace 타임스탬프 기반 게이팅. 타일 엔드포인트는 진입 시 viewer activity 신호 송출 + 블로킹 디코딩/ICC/인코딩을 `asyncio.to_thread`로 오프로드(이벤트 루프 차단 제거). `_run_detection`과 공유 PD/Precise-IHC의 `_read_patch_tensor`, `_run_virtual_stain`의 submit 루프에 `wait_if_viewer_busy()` 삽입 → 뷰어 요청 수신 시 AI 워커가 최대 3초 양보.
**변경사항**: backend/app/priority.py(신규), backend/app/routers/tiles.py, backend/app/routers/ai.py

### [2026-04-14 00:10]
**Q:** AI 추론 타일 가져올 때도 ICC profile 적용되는지 확인
**A:** `ai.py`의 AI 패치 로딩 경로 4곳에서 ICC 미적용 → `info.icc_transform`을 각 경로에 연결. (1) `_run_detection._read_patch_tensor` 스레드에서 `ImageCms.applyTransform` inPlace 적용, (2) 공유 PD/Precise-IHC `_read_patch_tensor` 동일 적용, (3) `_build_seg_overlays`에 `icc_transform` 파라미터 추가 후 썸네일/ROI 영역 변환, (4) `_run_virtual_stain`의 `_read_patch` 호출 시 `None` 대신 `info.icc_transform` 전달, `predict_wsi(세그멘테이션)`에도 `icc_transform` 전달.
**변경사항**: backend/app/routers/ai.py

### [2026-04-14 00:00]
**Q:** Precise-IHC에 ER/PR 기능 추가 (HER2와 동일 구조, Allred 스코어링)
**A:** 백엔드 `ai.py`에 ER/PR config + `_compute_allred_score()` 추가, 프론트 버튼 분리(HER2/ER/PR/KI-67), 앱 핸들러 분기(her2_score vs allred_score), visualization.js에 Allred 차트 및 PDF 페이지(`_pdfDrawAllredAnalysis`), Cover 메트릭 라벨 Allred 분기 추가.
**변경사항**: backend/app/routers/ai.py, frontend/app.html, frontend/js/app.js, frontend/js/visualization.js
