# MeDICus Studio SaaS — MongoDB 스키마

FastAPI + MongoDB (motor async) 기반. 모든 필드는 `str_/int_/bool_/dict_/list_/dt_/float_` 접두어 규칙(Claude.md)을 따른다.
인덱스는 [backend/app/database.py](../backend/app/database.py)의 `connect_db()`에서 멱등 생성된다.

## 컬렉션 개요

| # | 컬렉션 | 목적 | 수명 |
| - | ----- | ---- | ---- |
| 1 | [`users`](#1-users) | 인증 계정·권한·승인 상태 | 영구 |
| 2 | [`sessions`](#2-sessions) | Refresh Token 세션(로테이션/재사용 탐지) | TTL `dt_expires_at` |
| 3 | [`audit_logs`](#3-audit_logs) | 로그인·슬라이드 뷰·AI 분석 감사 로그 | 영구 |
| 4 | [`ip_geo_cache`](#4-ip_geo_cache) | IP → 지리정보 캐시 (ip-api.com) | TTL 30일 |
| 5 | [`slides`](#5-slides) | 업로드된 WSI 메타·AI 결과 플래그 | 영구 |
| 6 | [`folder_ai_configs`](#6-folder_ai_configs) | 폴더별 AI 자동 추론 설정 | 영구 |

### 관계 개요

```
users ──┬── sessions          (str_user_id)
        ├── audit_logs         (str_user_id)
        └── slides             (str_uploaded_by, 느슨한 FK)

audit_logs ── ip_geo_cache     (str_ip_address, 비정규화 캐시)

slides      ← folder_ai_configs (str_rel_path 기준 1:N)
```

---

## 1. `users`

사용자 계정. [backend/app/models.py](../backend/app/models.py)의 `create_user_document()`가 도큐먼트 생성 규격.

| 필드 | 타입 | 설명 |
| ---- | ---- | ---- |
| `_id` | ObjectId | PK |
| `str_login_id` | string | 로그인 아이디(소문자 정규화). **unique** |
| `str_hashed_password` | string | bcrypt + pepper 해시 |
| `str_name` | string | 표시 이름 |
| `str_role` | string | `admin` \| `doctor` \| `viewer` (technician은 migration으로 viewer로 downgrade) |
| `str_department` | string | 부서(선택) |
| `str_approval_status` | string | `pending` \| `approved` \| `rejected` |
| `str_approved_by` | string | 승인자 login_id / `"system"` |
| `dt_approved_at` | datetime? | 승인 시각 |
| `bool_is_active` | bool | 비활성화 플래그(승인 전엔 false) |
| `bool_is_locked` | bool | 연속 실패 시 계정 잠금 |
| `int_failed_login_attempts` | int | 실패 카운터 |
| `dt_locked_until` | datetime? | 잠금 해제 시각 |
| `dt_created_at` | datetime | 생성 시각 |
| `dt_updated_at` | datetime | 최종 수정 |
| `dt_last_login` | datetime? | 최종 로그인 시각 |

**인덱스**
- `str_login_id` unique
- `str_approval_status`

**마이그레이션 (startup)**
- `str_approval_status` 누락 + `admin` → `approved` + `bool_is_active=true`
- `str_approval_status` 누락 + 非admin → `pending` + `bool_is_active=false`
- `str_role == "technician"` → `viewer` (역할 축소, 2026-04 정책 변경)

**권한 요약**
- `admin`: 전체 기능 + 관리자 페이지
- `doctor`: 관리자 페이지를 제외한 모든 기능
- `viewer`: 슬라이드 조회만. AI 분석 / annotation 저장 / folder-config 수정 모두 `require_not_viewer`로 차단

---

## 2. `sessions`

Refresh Token 세션. Access Token은 저장하지 않고 JWT 자체 검증. [backend/app/routers/auth.py:287](../backend/app/routers/auth.py#L287)에서 생성.

| 필드 | 타입 | 설명 |
| ---- | ---- | ---- |
| `_id` | ObjectId | PK |
| `str_user_id` | string | `users._id` 문자열 |
| `str_refresh_token` | string | 현재 refresh token(회전 시마다 새 문서). **unique** |
| `str_ip_address` | string | 발급 시점 IP |
| `str_user_agent` | string | 발급 시점 UA |
| `dt_created_at` | datetime | 발급 시각 |
| `dt_expires_at` | datetime | 만료(TTL — 만료되면 자동 삭제) |
| `bool_is_revoked` | bool | 회전/로그아웃 시 true |
| `dt_rotated_at` | datetime? | 회전 시각(rotation 승리 시) |
| `str_replaced_by` | string? | 회전 후 새 refresh token(재사용 탐지용 포인터) |

**인덱스**
- `str_refresh_token` unique
- `dt_expires_at` TTL (`expireAfterSeconds=0`)

**회전 / 재사용 탐지**
- `/auth/refresh`는 `find_one_and_update(... bool_is_revoked: false, $set: revoked + replaced_by)` 원자 CAS로 한 요청만 rotation 획득.
- 이미 revoked된 토큰이 재요청되면: (a) grace window 내면 `str_replaced_by` 포인터를 따라가 동일 응답 반환, (b) 밖이면 해당 사용자의 모든 세션을 `update_many(... bool_is_revoked: true)`로 일괄 revoke (전역 로그아웃 효과).

---

## 3. `audit_logs`

감사 로그. [backend/app/audit.py](../backend/app/audit.py)의 `log_audit_event()`로 기록. 관리자 페이지 "활동 로그" 탭의 백엔드.

| 필드 | 타입 | 설명 |
| ---- | ---- | ---- |
| `_id` | ObjectId | PK |
| `str_action` | string | 아래 action 표 참고 |
| `str_user_id` | string? | 대상 사용자 id(로그인 실패 시 null 가능) |
| `str_user_email` | string? | 비정규화된 login_id (join 없이 표시 목적) |
| `str_resource_type` | string? | 예: `slide`, `user` |
| `str_resource_id` | string? | 리소스 식별자 |
| `str_detail` | string? | 자유 텍스트 메시지 |
| `str_ip_address` | string? | 클라이언트 IP (X-Forwarded-For → X-Real-IP → client) |
| `str_user_agent` | string? | UA 전체 문자열 |
| `dt_created_at` | datetime | 기록 시각 |
| `str_country` | string? | ISO2 국가코드 (geo enrich 결과) |
| `str_country_name` | string? | 국가명 |
| `str_region` | string? | 시·도 |
| `str_city` | string? | 도시명 |
| *(기타)* | any | `dict_extra`에 담긴 임의 필드(예: `str_rel_path`, `str_filename`, `str_model`) |

**action 값**
| action | 기록 시점 | 추가 필드 |
| ------ | -------- | -------- |
| `user.login_success` | 로그인 성공 | geo 필드 (async enrich) |
| `user.login_failure` | 로그인 실패 | — |
| `slide.view` | 슬라이드 열기(`/open`, `/open-local`) | `str_rel_path`, `str_filename`, `str_slide_id` |
| `ai.analyze` | AI 4종 엔드포인트 호출 | `str_model`, `str_variant` 등 |
| `user.create`, `user.update`, `user.approve`, `user.reject`, `user.delete` | 관리자 행위 | — |

**인덱스**
- `dt_created_at`
- `str_user_id`
- `str_action`
- compound `(str_user_id ASC, str_action ASC, dt_created_at DESC)` — 사용자 드릴다운 카테고리 필터 + 최신순

**Geo enrichment**
- `user.login_success` 기록 직후 `asyncio.create_task(enrich_audit_with_geo(...))`로 fire-and-forget.
- 응답 경로를 블로킹하지 않음. 실패해도 로그는 남음(geo 필드만 비어있게).

---

## 4. `ip_geo_cache`

IP → 국가/도시 캐시. [backend/app/geo.py](../backend/app/geo.py). 외부 `ip-api.com`(free tier, rate-limited 45/min, no key) 호출 결과를 30일간 캐싱한다.

| 필드 | 타입 | 설명 |
| ---- | ---- | ---- |
| `_id` | ObjectId | PK |
| `str_ip` | string | 조회 IP. **unique** |
| `str_country` | string | ISO2 국가코드 |
| `str_country_name` | string | 국가명 |
| `str_region` | string | 시·도 |
| `str_city` | string | 도시명 |
| `dt_updated_at` | datetime | 마지막 upsert |
| `dt_expires_at` | datetime | 만료(TTL). upsert 시 `now + 30일` |

**인덱스**
- `str_ip` unique
- `dt_expires_at` TTL

**사설 IP 스킵**: `127.`, `10.`, `192.168.`, `172.16-31.`, `169.254.`, `::1`, `fe80:`, `fc00:`, `fd00:` → 외부 API 호출 없이 즉시 skip.

---

## 5. `slides`

업로드된 WSI 파일의 메타데이터 + AI 결과 플래그. [backend/app/slide_store.py](../backend/app/slide_store.py)가 유일한 쓰기 경로. DB 미연결 시 helper들은 모두 no-op — 파일시스템 기반 동작은 유지된다.

| 필드 | 타입 | 설명 |
| ---- | ---- | ---- |
| `_id` | ObjectId | PK |
| `str_slide_id` | string | 애플리케이션 레벨 식별자(업로드 시 발급) |
| `str_filename` | string | 원본 파일명 |
| `str_rel_path` | string | `UPLOAD_DIR` 기준 상대 폴더(슬래시 정규화, `.`/빈값은 `""`) |
| `str_full_path` | string | 절대 경로(OpenSlide 열기용). 파일 이동 시 갱신 |
| `int_size_bytes` | int | 파일 크기 |
| `int_width` | int | WSI 최고 레벨 픽셀 폭 |
| `int_height` | int | WSI 최고 레벨 픽셀 높이 |
| `float_mpp` | float | microns-per-pixel (0이면 미상) |
| `str_vendor` | string | OpenSlide vendor 문자열 |
| `float_objective_power` | float | 배율 (40/20 등) |
| `str_uploaded_by` | string | 업로더 `str_login_id` (느슨한 FK) |
| `dt_uploaded_at` | datetime | 최초 업로드 |
| `dt_created_at` | datetime | 최초 도큐먼트 생성(업로드와 동일) |
| `dt_updated_at` | datetime | 최종 수정 |
| `dt_last_opened_at` | datetime | 최근 뷰어 오픈 시각 |
| `dict_ai_results` | dict | 모델별 결과 플래그. 아래 참조 |
| `bool_tiles_ready` | bool | 뷰어 사전 타일 생성 완료 여부 |
| `dt_tiles_ready_at` | datetime? | 타일 생성 완료 시각 |
| `str_status` | string? | 리뷰 상태: `""` / `pending` / `in_progress` / `done` / `flagged` |
| `dt_status_updated_at` | datetime? | 상태 변경 시각 |

**`dict_ai_results` 구조** — 키는 `LIST_AI_MODEL_KEYS = ["HE-Fit", "PD-Score", "Precise-IHC", "VS-IHC"]`:
```
{
  "HE-Fit":      {"bool_has_result": bool, "list_variants": [str, ...], "dt_updated_at": datetime?},
  "PD-Score":    {...},
  "Precise-IHC": {...},
  "VS-IHC":      {...}
}
```
- `list_variants`: tissue_type / marker / stain_type 등 variant 문자열들. `$addToSet`으로 중복 방지 추가.
- VS-IHC는 `target_mpp`를 DB에 별도 기록하지 않음 — base model 필터링만 DB 질의로, per-mpp 캐시 존재 확인은 파일시스템에서 수행.

**인덱스**
- `(str_rel_path, str_filename)` compound **unique** — 동일 폴더 내 파일명 중복 금지
- `str_slide_id`
- `dt_last_opened_at`

**주요 helper** (`slide_store.py`)
- `upsert_slide()` — 업로드/재열기 시 업서트. `$setOnInsert`로 `dict_ai_results`/`bool_tiles_ready`는 신규 시에만 초기화 → 재열기해도 AI 결과 유지.
- `touch_last_opened()`, `mark_ai_result()`, `mark_tiles_ready()`, `set_slide_status()`, `move_slide()`, `rename_folder_in_db()`, `delete_slide()`
- `*_threadsafe()` 변형: AI/타일 워커 스레드에서 `run_coroutine_threadsafe`로 메인 루프에 스케줄.

---

## 6. `folder_ai_configs`

폴더별 AI 자동 추론 설정. [backend/app/auto_ai.py](../backend/app/auto_ai.py)가 주기적으로(`SCAN_INTERVAL_SECONDS=60`) 스캔해 활성 폴더의 미완 variant들을 일괄 처리한다.

| 필드 | 타입 | 설명 |
| ---- | ---- | ---- |
| `_id` | ObjectId | PK |
| `str_rel_path` | string | `UPLOAD_DIR` 기준 상대 폴더 경로(정규화). **unique** |
| `bool_enabled` | bool | 자동 추론 on/off |
| `list_tasks` | list | 실행할 AI 작업 목록 |
| `dt_created_at` | datetime | 생성 시각 |
| `dt_updated_at` | datetime | 수정 시각 |

**`list_tasks` 항목 구조**
```
{
  "model":   "HE-Fit" | "PD-Score" | "Precise-IHC" | "VS-IHC",
  "variant": "<tissue_type | marker | stain_type>",
  "target_mpp": float    // VS-IHC 전용 (기본 2.0)
}
```

**인덱스**
- `str_rel_path` unique
- `bool_enabled`

**쓰기 권한**
- `POST/DELETE /folder-config` 모두 `require_not_viewer` 의존성 — viewer는 수정 불가, 조회만 허용.

**워커 동작 (`auto_ai.py`)**
1. `folder_ai_configs.find({bool_enabled: true})` 스캔
2. 각 task마다 `slide_store.list_slides_missing_variant(rel_path, model, variant)`로 미완 슬라이드만 조회
3. AI 파이프라인 호출 → 성공 시 `mark_ai_result()`로 `list_variants`에 variant 추가
4. 다음 인터벌까지 대기

---

## 부록 A — 전역 공통 규칙

- **타임스탬프**: 모든 `dt_*` 필드는 UTC (`datetime.now(timezone.utc)`).
- **ObjectId 직렬화**: API 응답에서는 `_id` → `str()`. `slide_store.serialize_slide_doc()`가 표준 헬퍼.
- **rel_path 정규화**: 역슬래시 → 슬래시, 앞뒤 슬래시 제거, 빈 경로는 `""`. `slide_store._norm_rel_path()` / `slides.py._norm_folder_path()`.
- **DB 미연결 내성**: `is_db_connected()`가 false면 `slide_store.*` helper는 조용히 no-op. 인증이 필요한 경로는 503을 반환한다.

## 부록 B — 인덱스 한눈에 보기

```
users.str_login_id                                        unique
users.str_approval_status

sessions.str_refresh_token                                unique
sessions.dt_expires_at                                    TTL(0)

audit_logs.dt_created_at
audit_logs.str_user_id
audit_logs.str_action
audit_logs.(str_user_id, str_action, dt_created_at DESC)  compound

ip_geo_cache.str_ip                                       unique
ip_geo_cache.dt_expires_at                                TTL(0)

slides.(str_rel_path, str_filename)                       unique compound
slides.str_slide_id
slides.dt_last_opened_at

folder_ai_configs.str_rel_path                            unique
folder_ai_configs.bool_enabled
```
