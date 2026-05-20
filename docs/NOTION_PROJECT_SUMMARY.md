# MeDIAuto Studio SaaS

> 병리 Whole Slide Image(WSI) 뷰어, Annotation, AI 분석, 프로젝트 관리를 하나로 묶은 병원 On-Premise형 웹 플랫폼

## 1. 프로젝트 개요

| 항목 | 내용 |
| --- | --- |
| 제품명 | MeDIAuto Studio SaaS |
| 현재 버전 | 1.1.20 |
| 릴리스 채널 | production |
| 최신 릴리스 | 2026-05-20 |
| 배포 형태 | 병원 내부망 On-Premise |
| 주요 사용자 | 병리과 의사, 연구자, 관리자, viewer 계정 |
| 핵심 목적 | WSI 조회, Annotation, AI 분석, 프로젝트 단위 운영, 감사 추적 |

## 2. 한 줄 설명

MeDIAuto Studio SaaS는 대용량 병리 WSI를 웹에서 빠르게 열람하고, Tissue/Cell Annotation과 Quanti AI 분석 모델을 프로젝트 단위로 관리할 수 있는 병리 AI 워크스페이스입니다.

## 3. 핵심 가치

- **WSI 웹 뷰어**: OpenSlide 기반 3-stage 타일 피라미드로 대용량 SVS/NDPI/TIFF 계열 슬라이드 열람
- **프로젝트 중심 워크플로**: 병원, 소유자, 슬라이드 수, 기본 AI 모델을 프로젝트별로 관리
- **Annotation 분리**: Tissue Annotation과 Cell Annotation을 별도 진입점으로 운영
- **AI 분석 제품군**: Quanti HE, Quanti PD-L1, Quanti IHC, VS IHC 지원
- **보안/감사 추적**: JWT, MFA, RBAC, HMAC 감사 로그, 미디어 URL 서명
- **운영 대시보드**: 프로젝트별/병원별 슬라이드 분포 차트와 최근 열람 슬라이드 추적

## 4. 주요 화면

| 화면 | URL | 설명 |
| --- | --- | --- |
| Home | `/home` | 운영 대시보드, 프로젝트/병원별 슬라이드 차트, 최근 슬라이드 |
| Project | `/project` | 프로젝트 목록, Default AI 모델 목록, 프로젝트 생성/수정/삭제 |
| AI | `/ai` | AI 분석 워크스페이스 |
| Tissue Annotation | `/tissue-annotation` | 조직 단위 Annotation 워크스페이스 |
| Cell Annotation | `/cell-annotation` | 세포 단위 Annotation 워크스페이스 |
| Admin | `/admin` | 사용자, 승인, 권한, 감사 로그 관리 |
| Profile | `/profile` | 사용자 프로필 및 계정 설정 |

## 5. 최근 변경 사항

### v1.1.20

- Annotation Class Management의 Hide/Show 버튼을 eye visibility icon으로 변경

### v1.1.19

- AI viewer module의 깨진 주석 정리 및 영어 파일 헤더 추가

### v1.1.18

- Tissue/Cell Annotation page module syntax 복구 및 project gate rendering 재활성화
- Annotation viewer script cache key 갱신

### v1.1.17

- AI page module syntax 복구 및 project gate rendering 재활성화
- AI viewer app script cache key 갱신

### v1.1.16

- AI page project gate startup IIFE 복구

### v1.1.15

- Scanner/vendor and native MPP badge 표시 복구

### v1.1.14

- AI viewer shortcut help를 annotation 페이지와 같은 Shortcuts modal UX로 정리
- AI Analysis help 내용을 영어로 통일

### v1.1.13

- Multi-cell edit popup 폭 제한 및 class-count summary 줄바꿈 처리

### v1.1.12

- `Alt + right-drag` 이후 지연 발생하는 browser context menu까지 차단하도록 보강

### v1.1.11

- AI viewer에서 `Alt + right-click/right-drag` 작업 중 브라우저 기본 context menu가 뜨지 않도록 차단

### v1.1.10

- 저장된 AI 편집본 cell count가 hidden Other cell을 제외한 visible result cell 기준으로 기록되도록 수정
- 기존 저장본 목록 조회 시 저장 JSON 기준으로 cell count 자동 보정

### v1.1.9

- Cell edit/add/sticky/multi popup header drag 이동 지원

### v1.1.8

- Hidden Other cell 승격 작업의 undo/redo 복구 처리 추가

### v1.1.7

- Alt 누름 상태의 viewer crosshair cursor 표시 안정화

### v1.1.6

- Sticky result-cell class picker 단축키를 `Alt + A`로 변경
- AI viewer `?` UX help 버튼을 ruler tool 옆으로 이동
- Hidden Other cell 라쏘 선택에 현재 모델 confidence threshold 적용

### v1.1.5

- AI viewer 상단 toolbar의 `?` UX help 버튼 표시 복구

### v1.1.4

- AI viewer cell editing shortcut 변경
- `Alt + 우클릭`: 새 result cell 추가
- `Alt + 우클릭 드래그`: hidden Other cell 선택 후 실제 클래스로 승격
- Alt 누름 상태에서 viewer cursor를 crosshair로 표시

### v1.1.3

- Quanti IHC / PD-L1의 숨김 Other cell을 결과 JSON의 `excluded_cells`로 보존
- AI/Annotation viewer에서 `Ctrl + Alt + 드래그`로 Other cell 임시 선택 및 실제 클래스로 승격 편집 지원
- Other cell은 클래스 지정 전까지 score, visualize, 결과 카운트에서 제외 유지

### v1.1.2

- Tissue Annotation과 Cell Annotation 오른쪽 패널 상단에 `VS IHC` 접근 추가
- Annotation 워크스페이스에서는 AI 패널 전체가 아니라 `VS IHC` 탭만 노출
- Annotation 워크스페이스의 기본 AI 탭 상태를 `VS IHC`로 설정

### v1.1.1

- 상단 메뉴에 `Project` 탭 추가
- `Annotation` 메뉴를 `Tissue` / `Cell` 하위 항목으로 분리
- 기존 annotation 페이지를 `Tissue Annotation`으로 정리
- `Cell Annotation` 페이지 추가
- 프로젝트 Open 모달에서 `AI`, `Tissue Annotation`, `Cell Annotation` 선택 가능
- Project 테이블의 `Due` 컬럼 제거
- `Default AI` 컬럼을 task 개수 대신 실제 모델명 목록으로 변경
- AI 모델 계열별 칩 색상 분리
- Home 상단 통계 카드 제거
- Home에 프로젝트별/병원별 슬라이드 차트 추가
- 차트 조각 hover tooltip 추가 및 조각 색상과 tooltip 색상 연동
- Recent Slides 카드가 마지막으로 열린 페이지 컨텍스트를 기억하도록 수정
- Recent Slides 카드에는 AI 결과 배지 대신 워크스페이스 배지 표시
- 프론트 정적 리소스 cache-busting 버전 `20260519-03` 적용

## 6. AI 모델 구성

| 모델 | 용도 | 주요 variant |
| --- | --- | --- |
| Quanti HE | H&E 세포 검출 및 epithelial 분류 | Stomach, Breast, Other |
| Quanti PD-L1 | PD-L1 IHC scoring | Stomach CPS, Lung TPS |
| Quanti IHC | IHC marker 정량 분석 | HER2, ER/PR Allred, Ki-67 |
| VS IHC | Virtual Staining | 4.0, 2.0, 1.0, 0.5 um/px |

## 7. 프로젝트 관리 기능

| 기능 | 설명 |
| --- | --- |
| 프로젝트 생성 | 제목, 병원, 부서, 소유자, 상태, 설명, 기본 AI 구성 |
| 프로젝트 목록 | Project, Hospital, Owner, Status, Slides, Default AI, Actions |
| Default AI 표시 | 실제 선택된 모델명을 색상 칩으로 표시 |
| 프로젝트 열기 | AI / Tissue Annotation / Cell Annotation 중 선택 |
| 프로젝트 대시보드 | 프로젝트별 슬라이드 수, 병원별 슬라이드 수 도넛 차트 |
| 권한 제어 | admin/doctor는 편집 가능, viewer는 제한 |

## 8. Annotation 기능

| 항목 | 설명 |
| --- | --- |
| Tissue Annotation | 조직 단위 annotation 작업 |
| Cell Annotation | 세포 단위 annotation 작업 |
| 도구 | Polygon lasso, Rectangle, Point |
| 저장 | 슬라이드별 JSON 저장 |
| 권한 | viewer는 저장 제한 |
| 프로젝트 연계 | 프로젝트 선택 후 annotation 워크스페이스 진입 |

## 9. Home Dashboard

| 구성 | 설명 |
| --- | --- |
| Slides By Project | 프로젝트별 슬라이드 수 분포 |
| Slides By Hospital | 병원별 슬라이드 수 분포 |
| Hover tooltip | 조각 이름, 슬라이드 수, 비율 표시 |
| Recent Slides | 최근 열람한 슬라이드 카드 |
| Workspace badge | AI / Tissue Annotation / Cell Annotation 표시 |
| Reopen context | 최근 열람한 워크스페이스로 다시 열기 |

## 10. 기술 스택

| 영역 | 기술 |
| --- | --- |
| Backend | Python 3.12, FastAPI, Uvicorn |
| Frontend | Vanilla JavaScript, HTML, CSS |
| Database | MongoDB 7.x, motor async driver |
| WSI | OpenSlide, Pillow, ICC profile, Hamamatsu NDP fit |
| AI | PyTorch, YOLOv11-M, pix2pix U-Net |
| Auth | JWT HS256, bcrypt, pepper, Refresh Token |
| MFA | RFC 6238 TOTP, AES-256-GCM encrypted seed |
| Audit | HMAC chain audit log |
| Media Security | 10-minute HMAC media ticket |

## 11. Backend 주요 구조

| 경로 | 역할 |
| --- | --- |
| `backend/main.py` | FastAPI 진입점, 정적 페이지 라우팅, `/api/version` |
| `backend/app/database.py` | MongoDB 연결 및 인덱스 |
| `backend/app/auth.py` | JWT, RBAC, 사용자 인증 |
| `backend/app/audit.py` | HMAC chain audit log |
| `backend/app/slide_store.py` | slides collection helper |
| `backend/app/slide_manager.py` | OpenSlide handle cache |
| `backend/app/tile_generator.py` | WSI tile generation |
| `backend/app/auto_ai.py` | folder/project AI 자동 실행 |
| `backend/app/routers/slides.py` | 슬라이드, 프로젝트, dashboard API |
| `backend/app/routers/ai.py` | AI 분석 API |

## 12. Frontend 주요 구조

| 경로 | 역할 |
| --- | --- |
| `frontend/home.html` | Home dashboard |
| `frontend/project.html` | Project management |
| `frontend/app.html` | AI workspace |
| `frontend/annotation.html` | Tissue Annotation |
| `frontend/cell-annotation.html` | Cell Annotation |
| `frontend/js/home.js` | Project/Home 로직 |
| `frontend/js/annotation.js` | Annotation 워크스페이스 로직 |
| `frontend/js/shared-header.js` | 공통 상단 메뉴 |
| `frontend/css/home.css` | Home/Project 스타일 |
| `frontend/css/style.css` | AI/Annotation 스타일 |
| `frontend/css/shared-header.css` | 공통 헤더 스타일 |

## 13. 데이터베이스 컬렉션

| 컬렉션 | 설명 |
| --- | --- |
| `users` | 사용자 계정, 권한, 승인 상태, MFA 정보 |
| `sessions` | Refresh token 세션 |
| `audit_logs` | 보안/행위 이벤트 및 HMAC chain |
| `ip_geo_cache` | IP 위치 정보 캐시 |
| `slides` | WSI 메타데이터, AI 결과 플래그, 최근 열람 정보 |
| `folder_ai_configs` | 폴더/프로젝트 단위 AI 자동 실행 설정 |
| `user_ai_edits` | 사용자별 AI 결과 편집본 |

## 14. 보안/컴플라이언스 요약

| 항목 | 현재 상태 |
| --- | --- |
| 인증 | JWT access token + refresh token |
| MFA | TOTP 기반 2차 인증 |
| 권한 | admin / doctor / viewer |
| 계정 보호 | 5회 로그인 실패 시 30분 잠금 |
| 감사 로그 | HMAC chain으로 변조 감지 |
| 미디어 보호 | 이미지 URL에 JWT 노출 없이 HMAC media ticket 사용 |
| 파일 무결성 | SHA-256 기반 업로드 파일 검증 |
| 경로 보안 | safe subpath / filename 검증 |

## 15. 운영 명령

```bat
start.bat
```

기본 접속 주소:

```text
http://localhost:8092
```

주요 확인 API:

```text
GET /api/health
GET /api/version
```

## 16. 버전 관리 규칙

| 작업 | 규칙 |
| --- | --- |
| 앱 버전 | `version.json` 수정 |
| 변경 이력 | `CHANGELOG.md`에 버전 섹션 추가 |
| 문서 버전 | `README.md`, `docs/VERSIONING.md` 동기화 |
| 프론트 캐시 | 변경된 JS/CSS는 HTML query version 갱신 |
| 태그 | 릴리스 시 `git tag vX.Y.Z` |

## 17. 현재 작업 상태

| 영역 | 상태 |
| --- | --- |
| Home dashboard | 완료 |
| Project tab | 완료 |
| Tissue Annotation route | 완료 |
| Cell Annotation route | 완료 |
| Recent Slides context | 완료 |
| Chart tooltip | 완료 |
| Version 1.1.1 관리 | 완료 |

## 18. 다음 개선 후보

- Project별 권한/담당자 세분화
- Cell Annotation 전용 UI/데이터 모델 분리
- Home 차트 기간 필터 추가
- Project dashboard export 기능
- 자동 테스트 및 CI/CD 구성
- 운영 배포용 HTTP security headers 강화
- MongoDB audit_logs append-only 권한 분리

## 19. 노션 DB로 분리하면 좋은 항목

### Project Roadmap

| 필드 | 타입 |
| --- | --- |
| Feature | Title |
| Area | Select: Home, Project, AI, Annotation, Admin, Backend |
| Status | Select: Backlog, In Progress, Done, Blocked |
| Priority | Select: P0, P1, P2, P3 |
| Version | Text |
| Owner | Person |
| Notes | Text |

### Release Notes

| 필드 | 타입 |
| --- | --- |
| Version | Title |
| Date | Date |
| Channel | Select |
| Added | Text |
| Changed | Text |
| Fixed | Text |
| Verification | Text |

### Compliance Tasks

| 필드 | 타입 |
| --- | --- |
| Requirement | Title |
| Standard | Select |
| Status | Select |
| Evidence | Files & media / URL |
| Risk | Select |
| Owner | Person |
| Due | Date |
