<!-- markdownlint-disable MD024 MD031 MD032 MD036 MD040 -->
# MeDIAuto Studio — 제품 소개서

> 의사 결정자(병원장·진단검사의학과장·IT 부서·구매팀) 대상 마케팅·영업 자료.
> 각 `## ` 헤더가 PPT 슬라이드 1장 분량.
>
> 버전: 1.0.0 / 2026-05-04 / 영문 자료 별도 제공 가능

---

## 1. 표지

- **MeDIAuto Studio**
- *AI-Augmented Digital Pathology, On Your Premises.*
- 디지털 병리 WSI 뷰어 + AI 분석 플랫폼
- SaMD Class 2 (식약처 의료기기 2등급) 인허가 목표
- 발행: MeDIAuto / 문의: (담당자 연락처)

---

## 2. 한눈에 보는 MeDIAuto

- **One Platform** — WSI 뷰어 + 4가지 AI 모델 + 자동 워크플로
- **On-Premise** — 환자 데이터가 병원 밖으로 나가지 않음
- **AI 보조 진단** — Quanti HE / Quanti PD-L1 / Quanti IHC / VS IHC
- **인허가 준비** — IEC 62304 / ISO 14971 / 21 CFR Part 11 / 식약처 가이드라인
- **즉시 도입** — 단일 서버, 1일 안에 셋업

---

## 3. 디지털 병리, 왜 지금인가

- **표본 디지털화 표준화** — DICOM-DP·OpenSlide 호환 스캐너 보급
- **병리의 부족** — 한국 병리의 1인당 슬라이드 부담 증가
- **AI 보조의 효용** — 셀 카운팅·점수 계산 자동화로 진단 시간 단축
- **인허가 가속** — 식약처 SaMD 가이드라인 정비, FDA AI/ML 가이드 발표
- **시장 규모** — 2030년 글로벌 디지털 병리 AI 시장 30억 달러+ (CAGR 13%↑)

---

## 4. 우리가 풀고 있는 문제

| 진단실 현실 | MeDIAuto 가 풀어내는 방식 |
|---|---|
| 슬라이드 카운팅에 1장당 30분+ | Quanti HE 자동 검출 → 분 단위로 단축 |
| PD-L1 CPS / TPS 계산이 주관적 | 정량 알고리즘 + 셀 단위 검증 가능 |
| HER2 / ER / Ki-67 점수 산정 일관성 부족 | 표준 score (Allred / LI) 자동 산출 |
| 클라우드 SaaS = 환자 데이터 외부 전송 우려 | **On-Premise 단일 서버** 로 차단 |
| 모델 업데이트 후 결과 추적 어려움 | 사용자별 편집본 분리 + 감사 로그 HMAC 체인 |

---

## 5. 핵심 가치 (4가지)

- **정확성 (Accuracy)** — Point Detection + WSI Segmentation + Pixel-level 분류
- **추적성 (Traceability)** — HMAC 체인 감사 로그, SHA-256 무결성, 21 CFR Part 11
- **안전성 (Security)** — JWT + TOTP MFA + AES-GCM + RBAC 3단계
- **속도 (Performance)** — 3-stage 타일 피라미드, CPU 코어 파티셔닝, 뷰어 우선순위 게이팅

---

## 6. 핵심 기능 — Quanti HE (H&E 세포 검출)

- **Point Detection** 기반 8 클래스 세포 검출
- 조직별 학습된 weights — Stomach / Breast / Other
- **자동 Tumor / Benign 재분류** (Stomach·Breast)
- WSI 1장당 약 5–15분 (GPU 1장 기준)
- 결과: 셀 좌표 + 클래스 + confidence + spatial heatmap

---

## 7. 핵심 기능 — Quanti PD-L1 (PD-L1 IHC)

- **CPS (Stomach)** — Combined Positive Score 0–100 자동 산출
- **TPS (Lung)** — Tumor Proportion Score 0–100% 자동 산출
- 양성/음성 × 종양/면역세포 7 클래스 분류 (Stomach 기준)
- Confidence ≥ 0.1 셀만 점수 반영 (재현성 보장)
- 셀 단위 검증·수정 가능 → 점수 실시간 재계산

---

## 8. 핵심 기능 — Quanti IHC

| Marker | Score | 임상 활용 |
|--------|-------|-----------|
| **HER2** | 0–3.0 가중평균 | 유방암 표적치료 결정 |
| **ER / PR** | Allred 0–8 (PS+IS) | 호르몬 수용체 양성/음성 |
| **Ki-67** | LI (%) — High/Low | 증식 지표 (St Gallen 2013 14% cutoff) |

- 염색 강도 0+/1+/2+/3+ 픽셀 단위 정밀 분류
- 사용자 셀 수정 → 점수 즉시 재계산

---

## 9. 핵심 기능 — VS IHC (Virtual Staining)

- **H&E → IHC 가상 염색** (membrane / nucleus 모델)
- pix2pix 계열 GAN — 학습 후 H&E 만으로 IHC 패턴 시뮬레이션
- 뷰어에서 원본·가상 IHC 토글 또는 Split view 비교
- 연구·교육 우선 — 실제 IHC 염색 대체 아님
- 큰 SVS 도 메모리 ~100 MB 로 처리 (스트리밍 누적기)

---

## 10. 워크플로 자동화

- **폴더 자동 AI 추론** — 폴더에 작업 등록만 하면 신규 슬라이드 자동 분석
- 60초 주기 백그라운드 워커, 사용자 활동 시 자동 양보
- 4가지 모델 조합 자유 — Quanti HE + Quanti PD-L1 + Quanti IHC + VS IHC
- 진단실 운영자가 "한 번 설정하면 끝" — 매일 업로드 분량을 야간에 자동 처리

---

## 11. 보안 & 인허가 (SaMD 2등급)

- **인증·인가**: JWT + RFC 6238 TOTP MFA + RBAC 3단계 + 5회 실패 30분 잠금
- **감사 추적**: HMAC 체인 감사 로그 + 변경 전/후 값 (21 CFR Part 11)
- **데이터 무결성**: 업로드 SHA-256 체크섬 + 검증 API
- **민감 데이터 암호화**: bcrypt + pepper, AES-256-GCM
- **네트워크 보호**: CSRF + Rate Limit + 디렉토리 탈출 방어
- 32개 SaMD 통제 매트릭스 매핑 — [SECURITY.md 부록 C](SECURITY.md)

---

## 12. On-Premise 배포 — 차별점

| 비교 항목 | 클라우드 SaaS | **MeDIAuto On-Premise** |
|---|---|---|
| 환자 데이터 위치 | 외부 클라우드 | **병원 내부망** |
| 외부 네트워크 의존성 | 필수 | **선택** (geo enrich 등 일부) |
| 인허가 적합성 | 데이터 국외 이전 이슈 | **국내 의료법 부합** |
| 응답 속도 | WAN 의존 | **LAN 속도** (타일 즉시 서빙) |
| 비용 모델 | 월 구독 (트래픽 비례) | **단일 서버 도입** |
| 모델 업데이트 | 자동 (예고 없이) | **병원 통제** (변경 관리 절차) |

---

## 13. 시나리오 — 위암 PD-L1 검사실

> 일일 PD-L1 케이스 30장 처리하는 진단실

- **Before**: 병리의 1인이 1장당 평균 25분, 일일 12.5시간 소요
- **After**: AI 자동 추론 → 병리의는 결과 검증·수정만, 1장 평균 8분
- **효과**: 일일 4시간+ 절감, CPS 일관성 확보, 정량 리포트 자동화

---

## 14. 시나리오 — 유방암 통합 진단

> HER2 + ER + PR + Ki-67 한 환자에 4종 검사

- **Before**: 마커별 별도 시각 평가, 점수 산정 표준화 부재
- **After**: 폴더 자동 AI → 환자 슬라이드 4종 자동 분석
- 한 화면에서 HER2 score / Allred TS / Ki-67 LI 모두 확인
- **효과**: 보고서 작성 시간 단축, 다중 마커 일관성 확보

---

## 15. 시나리오 — 다기관 연구

> 위암 PD-L1 다기관 임상시험 데이터 수집

- 각 기관 On-Premise 인스턴스 → 슬라이드 외부 반출 없음
- 표준 모델 + 동일 cutoff (CPS conf 0.1) 로 재현성 확보
- 사용자별 편집본 분리 — 검토자 간 의견 차이 추적 가능
- 감사 로그 HMAC 체인 — 결과 변조 즉시 감지

---

## 16. 도입 효과 (정량)

| 지표 | 개선 |
|------|------|
| 1 슬라이드 진단 시간 | **30–60% 단축** (시나리오에 따름) |
| PD-L1 CPS 산정 일관성 | 검증된 cutoff 0.1, 사용자 편집 가능 → 재현성 확보 |
| 보고서 작성 시간 | PDF 자동 생성으로 단축 |
| AI 결과 검증 시간 | 셀 단위 편집 + sticky HUD 로 효율화 |
| 인허가 적합성 입증 | 32개 SaMD 통제 매트릭스 즉시 제공 |

> 실제 효과는 진단실 워크로드·스캐너·인력 구성에 따라 다름.

---

## 17. 기술 스택 — Backend

- **언어/런타임**: Python 3.12, FastAPI (ASGI)
- **DB**: PostgreSQL 18, SQLAlchemy async/asyncpg, Alembic 스키마 관리
- **AI**: PyTorch + CUDA AMP, Point Detection, pix2pix
- **WSI**: OpenSlide, Pillow, ICC profile, Hamamatsu NDP fit
- **보안**: bcrypt, AES-256-GCM, HMAC-SHA256, RFC 6238 TOTP

---

## 18. 기술 스택 — Frontend

- **순수 JS (Vanilla ES Modules)** — 빌드 도구 없음, 빠른 디버깅
- HTML5 Canvas — 60 FPS 타일 렌더링
- 3-stage 피라미드 (downsample 1/4/8) — fade-in 250ms
- 반응형 (≤900 px) — 모바일·태블릿 drawer UI
- 미디어 HMAC 티켓으로 `<img src>` 인증

---

## 19. 시스템 요구사항 — 권장

| 항목 | 권장 사양 |
|------|-----------|
| OS | Linux (Ubuntu 22.04+) / Windows 11 |
| CPU | 24 코어+ (CPU 파티셔닝: viewer/bg/ai 자동 분배) |
| RAM | 64 GB+ |
| GPU | NVIDIA RTX A6000 / L40S / A100 (CUDA 11.8+) |
| 디스크 | NVMe SSD 1 TB+ (슬라이드 + 타일 캐시) |
| 네트워크 | 1 Gbps+ 내부망 |

---

## 20. 배포 모델

- **단일 서버** — 4명 동시 사용까지 충분
- **GPU 멀티 인스턴스** — 추론 부하 분산
- **백업 전용 서버** — `users` + `audit_logs` + 시크릿 파일 자동 백업
- 도커 / 시스템 서비스 / 프로세스 매니저 자유 선택
- 1일 안에 초기 설치 + 첫 슬라이드 업로드 가능

---

## 21. PACS / LIS 연동 (Roadmap)

- 현재: 파일 시스템 업로드 (drag-and-drop)
- v1.x: DICOM-DP 게이트웨이 연동 (PACS 서버에서 자동 import)
- v1.x: HL7 / FHIR 보고서 출력 (LIS 연동)
- v2.x: 외부 SIEM 연동 — 보안 이벤트 실시간 알림
- 인터페이스 설계 단계부터 협의 가능 — IT 부서와 직접 협의

---

## 22. 지원 / SLA

- **소프트웨어 라이선스** — 도입 시 영구 사용 + 1년 유지보수 포함
- **유지보수** — 보안 패치 / 모델 업데이트 / 버그 수정
- **기술 지원** — 영업일 8시간 응답, 긴급 4시간
- **온사이트 트레이닝** — 도입 시 병원 진단실 1회 (옵션)
- **추가 모델 학습** — 병원 자체 데이터로 fine-tuning 별도 협의

---

## 23. 인허가 / 규제 정합성

- **목표**: 식약처 의료기기 2등급 (SaMD Class 2)
- **적용 규격**:
  - IEC 62304 (의료기기 SW 수명주기)
  - ISO 14971 (위험관리)
  - ISO 13485 (QMS)
  - 21 CFR Part 11 (전자기록·서명)
  - IEC 81001-5-1 (Health software 보안)
  - 식약처 의료기기 사이버보안 가이드라인
- **현재 충족**: 32개 통제 중 25개 ✅ / 4개 ⚠ (운영) / 3개 ❌ (별도 산출물 필요)

---

## 24. 로드맵

| 시기 | 마일스톤 |
|------|----------|
| 2026 Q2 | SaMD 2등급 인허가 신청서 제출 |
| 2026 Q3 | DICOM-DP 게이트웨이 alpha |
| 2026 Q4 | HL7 / FHIR 보고서 연동 |
| 2027 Q1 | 추가 marker 모델 (P53, EGFR 등) |
| 2027 Q2 | 외부 SIEM + 시판 후 모니터링 자동화 |
| 2027 Q3 | 다기관 연합 학습 (Federated Learning) PoC |

---

## 25. 가격 모델 (개요)

- **단일 서버 라이선스** — 도입 + 1년 유지보수 포함
- **사용자 수 무제한** — On-Premise 단일 서버 모델 특성상 라이선스가 사용자에 비례하지 않음
- **AI 모델 추가** — 추가 marker / 조직 타입 학습 별도 견적
- **연차 유지보수** — 라이선스 비용의 일정 % (보안 패치·업데이트 포함)
- **상세 견적 협의** — 병원 규모·연동 범위에 따라 맞춤 제안

> 정확한 견적은 영업팀 문의.

---

## 26. 도입 절차

```
1. NDA 체결          (1주)
2. 환경 사전 점검    (1주, 원격)
3. 견적 / 계약 체결  (2주)
4. 설치 / 초기 셋업  (1일)
5. 사용자 트레이닝   (반일)
6. 파일럿 운영       (4주)
7. 본격 운영 시작    
8. 정기 점검·갱신    (분기 / 연간)
```

---

## 27. 자주 묻는 질문 (FAQ)

- **Q. 인터넷 연결이 필요한가?** A. 아니오 — IP geo enrichment 외엔 모두 내부망에서 동작.
- **Q. 환자 데이터가 병원 밖으로 나가는가?** A. 절대 아님. 모든 처리는 병원 서버에서.
- **Q. AI 결과를 100% 신뢰해도 되는가?** A. 아니오 — **보조 도구**. 최종 진단은 의사가.
- **Q. 백업은 어떻게?** A. 매뉴얼 §29 참조. `users` + `audit_logs` + `.secrets.json`.
- **Q. 다른 스캐너와 호환되나?** A. OpenSlide 호환 포맷 모두 지원.
- **Q. 모델을 우리 병원 데이터로 학습 가능한가?** A. 별도 학습 협의 가능.

---

## 28. 보안 — 핵심 메시지

- **Zero data egress** — 환자 슬라이드는 병원 인프라를 떠나지 않음
- **Zero hardcoded secrets** — 시크릿은 환경변수 또는 0600 권한 파일에서만
- **Zero JWT in URL** — 미디어는 단기 HMAC 티켓으로 별도 인증
- **Zero unauthenticated AI** — viewer 역할도 AI 트리거 차단
- **Zero log tampering** — HMAC 체인 즉시 변조 감지

---

## 29. 회사 / 팀

- **MeDIAuto** — 디지털 병리 AI 전문 (PyQt5 데스크톱 → 웹 SaaS 진화)
- 병리·AI·SW 엔지니어링 통합 팀
- 인허가 컨설팅 파트너 보유
- 협력 기관: (병원·연구소 명시 — placeholder)
- 수상·인증: (해당 시 추가)

---

## 30. 컨택

- **영업 / 도입 문의**: sales@mediauto.example
- **기술 문의**: tech@mediauto.example
- **인허가 / 임상**: regulatory@mediauto.example
- **웹사이트**: <https://mediauto.example>
- **데모 신청**: 위 메일 또는 (담당자 직통)

> *MeDIAuto Studio — 병리의 곁에서, 데이터는 병원 안에서.*

---

## 부록 A — 더 알고 싶다면

- **문서 목차** — [README.md](README.md)
- **사용자 가이드 + IFU 초안** — [USER_GUIDE.md](USER_GUIDE.md)
- **기능 명세** — [FEATURES.md](FEATURES.md)
- **보안 설계 + SaMD 매트릭스** — [SECURITY.md](SECURITY.md)
- **인허가 충족 현황** — [COMPLIANCE_STATUS.md](COMPLIANCE_STATUS.md)
- **DB 스키마** — [DATABASE.md](DATABASE.md)
