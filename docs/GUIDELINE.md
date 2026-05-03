<!-- markdownlint-disable MD024 MD031 MD032 MD036 MD040 -->
# MeDIAuto Studio — 사용자 가이드라인

> 본 문서는 **PPT 슬라이드 변환을 전제** 로 작성되었다. 각 `## ` 헤더가 한 슬라이드, 그 안의 bullet 들이 슬라이드 본문이다.
>
> 의도된 용도 — (1) 신규 사용자 온보딩 자료, (2) SaMD 2등급 인허가 시 IFU (Instructions for Use) 초안.
> 마지막 갱신 — 2026-05-04 / 대상 버전 — 1.0.0

---

## 1. 표지

- **MeDIAuto Studio**
- 디지털 병리 WSI 뷰어 + AI 분석 플랫폼
- SaMD Class 2 (식약처 의료기기 2등급 목표)
- On-Premise 병원 배포 / 단일 서버
- 발행: MeDIAuto / 대상: 병리의·연구원·관리자

---

## 2. 의도된 사용 (Intended Use)

- 병리의의 진단 **보조** 도구 — 최종 진단·치료 결정은 의사가 수행
- H&E 슬라이드 세포 검출·정량 (HE-Fit)
- IHC 슬라이드 PD-L1 / HER2 / ER·PR / Ki-67 정량 분석 (PD-Score, Precise-IHC)
- H&E → IHC virtual staining (VS-IHC, 연구·교육용 우선)
- 적용 조직: 위암(Stomach), 유방암(Breast), 폐암(Lung) — 모델별 학습 범위 내

---

## 3. 사용 한계 / 금기 (Limitations)

- 본 SW는 **단독 진단 도구가 아님** — 모든 결과는 병리의 검토를 거쳐야 함
- 학습 데이터 분포를 벗어난 조직·염색 변형(scanner 차이, fixation 불량)에선 성능 저하 가능
- 슬라이드 ICC 프로파일 부재 + non-Hamamatsu 스캐너 조합은 색감 차이 발생 가능 (NDP fit 토글로 보정 가능)
- AI 결과는 **사용자가 수정 가능** — 수정본은 사용자별로 분리 저장되며 원본은 보존됨
- VS-IHC 결과는 실제 IHC 염색을 대체하지 않음 (research-use only)

---

## 4. 시스템 요구사항

| 항목 | 사양 |
|------|------|
| 서버 OS | Linux (권장) / Windows 11 |
| Python | 3.12+ |
| MongoDB | 7.0+ |
| GPU | NVIDIA CUDA 11.8+ (AI 가속) |
| RAM | 32 GB+ (대용량 WSI 권장 64 GB) |
| 디스크 | 슬라이드 + 타일 캐시 (50 GB+) |
| 클라이언트 | Chrome / Edge / Safari 최신 |
| 네트워크 | 병원 내부망 (On-Premise) |

---

## 5. 지원 슬라이드 포맷

- **OpenSlide 호환 WSI**: SVS, NDPI, TIFF, VMS, VMU, SCN, MRXS
- 일반 이미지: PNG, JPG, JPEG (테스트 용도)
- 단일 파일 상한: 20 GB
- 청크 업로드 지원 — 대용량 파일 재개 가능

---

## 6. 사용자 역할 (RBAC)

| 역할 | 관리자 페이지 | AI 분석 | 주석 저장 | 폴더 설정 | 슬라이드 조회 |
|------|:---:|:---:|:---:|:---:|:---:|
| **admin** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **doctor** | ❌ | ✅ | ✅ | ✅ | ✅ |
| **viewer** | ❌ | ❌ | ❌ | ❌ | ✅ |

- 첫 가입자는 자동으로 **admin** + 즉시 승인
- 이후 가입자는 **viewer + pending** 상태 → admin 승인 필요

---

## 7. 시작하기 — 회원가입

- 로그인 페이지에서 "회원가입" 클릭
- 입력 항목: 아이디 / 비밀번호 / 이름 / 부서
- 아이디: 4~30자, 영문/숫자/언더스코어
- 비밀번호: 8자 이상 + 대문자 + 소문자 + 숫자 + 특수문자
- 가입 후 관리자 승인 대기 → 승인되면 로그인 가능

---

## 8. 시작하기 — 로그인

- 아이디 + 비밀번호 입력
- 5회 실패 시 30분 자동 잠금
- MFA 활성 사용자: 비밀번호 통과 후 6자리 TOTP 코드 입력
- 로그인 시간 / 위치 / IP 자동 기록 (관리자 활동 로그)

---

## 9. 2차 인증 (MFA) 설정

1. 로그인 후 사용자 메뉴 → "2차 인증 설정"
2. 화면의 QR 코드를 Google Authenticator / Microsoft Authenticator 로 스캔
3. 앱에 표시된 6자리 코드를 입력 → 활성화
4. 다음 로그인부터 비밀번호 + TOTP 코드 모두 필요
5. 비활성화도 같은 메뉴에서 가능

---

## 10. 메인 화면 구성

- **좌측 패널**: 폴더 트리 + 슬라이드 목록 (썸네일 그리드)
- **중앙**: WSI 뷰어 (Canvas 렌더링)
- **우측 패널**: AI 분석 결과 + Annotation
- **상단 툴바**: 줌·Fit·도구 선택 + 모델 트리거
- **하단**: 미니맵 + 줌 정보 + 마우스 좌표

---

## 11. WSI 뷰어 — 기본 조작

| 동작 | 데스크톱 | 모바일 |
|------|---------|-------|
| 팬 | 좌클릭 드래그 | 한 손가락 드래그 |
| 줌 | 마우스 휠 | 두 손가락 핀치 |
| Fit to window | Fit 버튼 / 단축키 | Fit 버튼 |
| 그리기 취소 | 우클릭 / ESC | — |
| Annotation 내부 팬 | Ctrl + 드래그 | — |

- 좌하단 미니맵에 현재 뷰포트 표시
- 우하단 마우스 좌표 (슬라이드 픽셀)

---

## 12. WSI 뷰어 — Annotation

- 도구: **Polygon (lasso)** / **Rectangle** / **Point**
- 1 mm² 정사각형 / 원형 ROI 자동 그리기 버튼 제공
- Ruler — 두 점 거리 측정 (μm)
- 우측 패널 Annotation Panel 에서 색상·이름 변경, 삭제
- "저장" 으로 슬라이드별 JSON 영구화 (viewer 역할은 저장 불가)

---

## 13. WSI 뷰어 — 색 보정

- **자동 ICC 적용** — 슬라이드 임베드 ICC 프로파일이 있으면 sRGB 변환
- **Hamamatsu NDP fit** — Hamamatsu NDPI 슬라이드용 별도 토글
  - 우측 패널 "NDP 색보정 ON" 으로 활성화
  - NDP.view2 와 동일한 톤으로 보정된 타일 서빙
  - 이미지 처리는 서버에서 수행 (클라이언트 부하 0)

---

## 14. 슬라이드 업로드

1. 좌측 패널 "업로드" 버튼 클릭
2. 파일 선택 (drag-and-drop 또는 파일 선택기)
3. 대상 폴더 선택 (없으면 새 폴더 생성)
4. 5 MB 청크 단위로 업로드 (네트워크 끊겨도 재개 가능)
5. 업로드 완료 → 자동 타일 프리젠 + 슬라이드 메타 등록
6. 업로드 직후 SHA-256 체크섬 자동 계산·저장

---

## 15. 슬라이드 관리

- **상태 플래그**: pending / in_progress / done / flagged — 리뷰 워크플로 추적
- **이동 / 이름 변경 / 삭제** — 우클릭 메뉴
- **체크섬 검증** — 슬라이드 우클릭 → "무결성 검증" → SHA-256 재계산 + DB 비교
- 삭제 시 원본·타일·AI 결과 캐시 모두 함께 제거
- viewer 역할은 모든 변경 작업 차단

---

## 16. AI 분석 — HE-Fit (H&E 세포 검출)

- **입력**: H&E 슬라이드, tissue type (Stomach / Breast / Other)
- **출력**: 8 클래스 세포 검출 좌표
  - Neutrophil / Epithelial / Lymphocyte / Plasma / Eosinophil / Stromal cell / Tumor Epithelial / Benign Epithelial
- **재분류** (Stomach / Breast 만): Epithelial → Tumor / Benign 자동 분류
- **소요**: WSI 1장당 약 5–15분 (GPU 기준)
- "Visualize" 버튼 → 4탭 (분포 / Tumor 분석 / Spatial heatmap / Confidence)

---

## 17. AI 분석 — PD-Score (PD-L1)

- **입력**: PD-L1 IHC 슬라이드, tissue type (Stomach / Lung)
- **출력**:
  - **Stomach → CPS** (Combined Positive Score, 0–100)
  - **Lung → TPS** (Tumor Proportion Score, 0–100%)
- 양성/음성 × 종양/면역세포 자동 분류 → 임상 점수 자동 산출
- Confidence ≥ 0.1 셀만 점수에 반영 (재현성 보장)

---

## 18. AI 분석 — Precise-IHC

| Marker | Score | 해석 |
|--------|-------|-----|
| **HER2** | 0–3.0 (가중평균) | dominant class + score |
| **ER / PR** | Allred 0–8 (PS+IS) | TS≥3 → Positive |
| **Ki-67** | Labeling Index (%) | ≥14% → High (St Gallen 2013) |

- 염색 강도 0+ / 1+ / 2+ / 3+ 세포 단위 분류
- 사용자가 셀을 수정하면 점수 실시간 재계산

---

## 19. AI 분석 — VS-IHC (Virtual Staining)

- **입력**: H&E 슬라이드 + stain type (membrane / nucleus)
- **출력**: 가상 IHC 이미지 (피라미드 타일)
- Target MPP 설정 (기본 2.0 μm/px ≈ ×5)
- 뷰어 오버레이 + Split view 로 원본 H&E 와 비교
- ROI 폴리곤은 표시 마스크로만 사용 (추론은 항상 전체)
- 연구·교육용 — 실제 IHC 염색 대체 아님

---

## 20. AI 결과 — 셀 편집

- 우측 결과 리스트에서 셀 클릭 → edit 모드
- 클래스 변경 / 추가 / 삭제 가능
- **Sticky 클래스**: 클릭한 클래스가 sticky 로 묶여 다음 셀 추가 시 기본값
- Shift 키 홀드 → 마우스 우상단에 sticky 클래스 HUD 표시
- 편집 후 "Save" → 사용자별 편집본으로 저장 (원본 캐시 보존)
- 다른 사용자 편집본은 별도 사용자 메뉴에서 로드 가능

---

## 21. AI 결과 — 시각화 / 리포트

- "Visualize" → 4탭 다이얼로그
  - **Class Distribution** (바 차트)
  - **Tumor Analysis** (Stomach / Breast 만)
  - **Spatial Heatmap** (썸네일 + 클래스별 오버레이)
  - **Confidence Distribution** (히스토그램)
- **PDF Export**: 각 score type 전용 페이지 (커버 + 메트릭)
- 클립보드 복사·이미지 저장 지원

---

## 22. 폴더 단위 자동 AI 추론

- 폴더별로 "이 AI 를 자동 실행" 설정
  - HE-Fit / PD-Score / Precise-IHC / VS-IHC 조합 가능
  - 조직 타입 / marker / target_mpp 지정
- 60초 주기 백그라운드 워커가 미완 슬라이드만 처리
- 사용자 활동 / 업로드 중 / 뷰어 조작 중에는 자동 양보
- viewer 역할은 설정 수정 불가, 조회만 가능

---

## 23. 관리자 페이지 (1) — 승인 대기

- 신규 가입자 목록
- 승인 시 역할 지정 (viewer / doctor / admin)
- 거부 시 사유 입력 (감사 로그 보존)
- 모든 작업은 변경 전/후 값까지 기록 (21 CFR Part 11)

---

## 24. 관리자 페이지 (2) — 사용자 관리

- 전체 사용자 페이지네이션 (필터: 상태·검색)
- 행 단위: 수정 / 역할 변경 / 활성 토글 / 잠금 해제 / 삭제
- 마지막 admin 보호 — 삭제·강등 차단
- 사용자 정보 변경은 30초 캐시 즉시 무효화

---

## 25. 관리자 페이지 (3) — 활동 로그

- 로그인 이력 역순 페이지네이션
- 컬럼: 시간(KST) / 아이디 / 이름·역할 / IP / 위치 / 디바이스
- 행 클릭 → 사용자 상세 활동 (전체 / 로그인 / 슬라이드 / AI 카테고리)
- HMAC 체인 무결성 검증 API 제공 — 로그 변조 시 즉시 감지

---

## 26. 보안 / 개인정보

- 모든 비밀번호: bcrypt + pepper 해싱
- 민감 필드 (TOTP 시드): AES-256-GCM 암호화
- 토큰: JWT 15분 / Refresh 7일, 자동 회전 + 재사용 탐지
- 미디어 URL: 단기 HMAC 티켓 (10분) — JWT 노출 차단
- 모든 보안 이벤트: HMAC 체인 감사 로그
- 자세한 내용: [docs/SECURITY.md](SECURITY.md)

---

## 27. 자주 발생하는 문제

| 증상 | 원인 / 해결 |
|------|-------|
| 로그인 후 빈 화면 | 토큰 만료 — 재로그인 |
| 타일이 흐리게 나오거나 안 뜸 | 슬라이드 첫 로드 — 백그라운드 타일 생성 대기 |
| Hamamatsu 슬라이드 색감 이상 | 우측 패널 NDP 색보정 ON |
| AI 결과가 같은 입력에 다르게 나옴 | 캐시 hit — `reset_ai_results.py --models <X>` 로 리셋 |
| 5회 실패 후 잠금 | 30분 대기 또는 admin 잠금 해제 요청 |
| MFA 코드가 안 맞음 | 디바이스 시계 동기화 (±30초 허용) |

---

## 28. 시판 후 모니터링 / 보고

- 이상사례 발견 시 즉시 IT 담당자 또는 제조사로 보고
- 보고 항목: 슬라이드 ID / AI 모델 / 입력 / 예상 결과 / 실제 결과 / 환자 영향 여부
- 정기 점검: HMAC 체인 무결성 검증 (월 1회 권장)
- 백업: `users` + `audit_logs` + `.secrets.json` (분리 보관)

---

## 29. 참고 문서

- [README.md](../README.md) — 설치·실행
- [docs/FEATURES.md](FEATURES.md) — 전체 기능 명세
- [docs/SECURITY.md](SECURITY.md) — 보안 설계 + SaMD 2등급 매트릭스
- [docs/DATABASE.md](DATABASE.md) — DB 스키마
- [docs/COMPLIANCE_STATUS.md](COMPLIANCE_STATUS.md) — 규제 충족 현황
- [docs/color_match_analysis.md](color_match_analysis.md) — 색 보정 분석

---

## 30. 문의 / 지원

- 시스템 관리자: (병원 IT 담당)
- 기술 문의: MeDIAuto 개발팀
- 인허가·임상 검증 자료: 별도 IFU·임상 평가 보고서 참조
- 라이선스 / 갱신: 계약서 명시
- 본 문서는 정기적으로 갱신됨 — 최신본은 사내 wiki 또는 GitHub 참조

---

## 부록 — PPT 변환 가이드

이 문서를 PPT 로 변환하는 가장 빠른 방법:

1. **Marp / Pandoc 사용** (자동):

   ```bash
   # Pandoc 으로 직접 변환
   pandoc docs/GUIDELINE.md -o GUIDELINE.pptx --reference-doc=template.pptx

   # 또는 Marp (CLI)
   npx @marp-team/marp-cli docs/GUIDELINE.md --pptx -o GUIDELINE.pptx
   ```

2. **수동 복사** (다듬기 필요할 때):
   - 각 `## ` 헤더 → 새 슬라이드 제목
   - bullet 들 → 슬라이드 본문
   - 표 → PPT 표 위젯으로 직접 입력

3. **`python-pptx` 변환 스크립트** — 필요 시 별도 작성 가능 (요청 시 제공).

각 섹션이 1 슬라이드로 떨어지도록 구성되어 있어 30 슬라이드 분량으로 자동 변환된다.
