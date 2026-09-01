# MeDIAuto Studio SaaS 데이터베이스

현재 애플리케이션의 유일한 데이터베이스는 PostgreSQL 18이다. SQLAlchemy async와
`asyncpg`를 사용하며 스키마는 Alembic으로 관리한다.

## 테이블 개요

| 테이블 | 용도 | 주요 제약·인덱스 |
| --- | --- | --- |
| `users` | 계정, 역할, 승인, 잠금, MFA | login ID unique, 승인 상태 index |
| `sessions` | Refresh Token 회전과 폐기 | token unique, user/expiry index, user FK cascade |
| `audit_logs` | 사용자·관리자 행위와 HMAC 체인 | 시각/user/action/HMAC index |
| `audit_integrity_seals` | 감사 데이터 스냅샷 봉인 | scope unique |
| `ip_geo_cache` | IP 위치와 만료 시각 | IP unique, expiry index |
| `case_clinical_info` | 케이스별 임상정보 JSONB | case name unique |
| `application_documents` | 프로젝트·슬라이드·AI·annotation JSONB | collection+natural key unique, GIN index |
| `application_data_migrations` | 검증된 과거 전환 마커 | marker ID PK |
| `alembic_version` | 적용된 스키마 revision | Alembic 관리 |

## 인증과 세션

`users.id`와 `sessions.id`는 문자열 기본키다. 비밀번호는 bcrypt와 pepper로
해시되며 MFA seed는 AES-256-GCM으로 암호화한다. Refresh Token은 회전 시 원자적
비교·갱신으로 한 요청만 성공하며, `sessions.dt_expires_at`을 기준으로 만료 세션을
정리한다.

## 감사와 임상정보

감사 로그는 이전 HMAC, 현재 HMAC, 변경 전·후 JSON, IP 위치 및 사용자 정보를
저장한다. `audit_integrity_seals`는 스냅샷 건수와 SHA-256/HMAC을 보관한다.
임상정보는 `case_clinical_info.dict_clinical_info` JSONB에 저장하고 case name으로
일관되게 조회한다.

## 애플리케이션 문서

`application_documents`는 다음 논리 collection을 구분해 저장한다.

- `slides`
- `folder_ai_configs`
- `project_infos`
- `annotation_required_regions`
- `patch_annotation_status`
- `patch_cell_annotations`
- `user_ai_edits`
- `app_settings`

복합 기본키는 `(str_collection, str_id)`이고, 빈번한 조회는 collection,
natural key 및 secondary key 인덱스를 사용한다. 문서 본문은 JSONB GIN 인덱스를
지원한다. Python datetime은 명시적 type tag로 직렬화해 시간대 정보를 보존한다.

## 연결과 스키마

핵심 환경변수는 다음과 같다.

| 변수 | 기본 또는 설정 |
| --- | --- |
| `POSTGRES_URI` | `postgresql+asyncpg://...` 연결 URI |
| `POSTGRES_POOL_SIZE` | 기본 pool 크기, 기본값 10 |
| `POSTGRES_MAX_OVERFLOW` | 추가 연결 상한, 기본값 20 |

스키마 적용:

```bash
set -a
source .env.postgres
set +a
cd backend
alembic upgrade head
```

테이블을 코드에서 임의 생성하거나 변경하지 않는다. 모든 변경에는 새로운 Alembic
revision과 Repository 회귀 테스트가 필요하다.

## 저장 범위

WSI 원본, 타일 캐시, AI 이미지와 PDF는 파일 시스템에 저장한다. PostgreSQL에는
파일 경로, 상태, 체크섬, 정량 결과와 편집 메타데이터만 저장한다. 따라서 복구 시
PostgreSQL dump와 `UPLOAD_DIR`, `AI_RESULTS_DIR`, 영구 암호화 키를 함께 복원해야 한다.
