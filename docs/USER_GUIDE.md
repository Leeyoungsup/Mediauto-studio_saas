<!-- markdownlint-disable MD024 MD031 MD032 MD036 MD040 -->
# MeDIAuto Studio — 사용자 가이드

> 병리의, 연구원, 관리자용 통합 문서.
> 기존 `USER_MANUAL.md`의 화면 조작 안내와 `GUIDELINE.md`의 의도된 사용·한계·IFU 초안을 합쳤다.
>
> 대상 버전: 1.0.0 / 마지막 갱신: 2026-05-06

---

## 1. 문서 목적

이 문서는 MeDIAuto Studio를 실제로 사용하는 사람이 빠르게 업무를 시작하고, AI 결과를 안전하게 해석하며, 관리자 작업과 운영 점검을 수행할 수 있도록 돕는다.

- 신규 사용자 온보딩
- 화면 단위 조작 안내
- AI 분석 결과 확인·수정·저장 절차
- 의료기기 사용 한계와 주의사항
- 관리자 승인, 감사 로그, 백업 점검 절차

상세 구현 명세는 [FEATURES.md](FEATURES.md), 보안 설계는 [SECURITY.md](SECURITY.md), 규제 충족 현황은 [COMPLIANCE_STATUS.md](COMPLIANCE_STATUS.md)를 참조한다.

---

## 2. 의도된 사용

MeDIAuto Studio는 병리의의 진단을 보조하기 위한 디지털 병리 WSI 뷰어 + AI 분석 플랫폼이다.

- H&E 슬라이드의 세포 검출 및 정량 분석: Quanti HE
- PD-L1 IHC 점수 산출: Quanti PD-L1, Stomach CPS / Lung TPS
- HER2, ER/PR, Ki-67 IHC 정량 분석: Quanti IHC
- H&E 기반 가상 IHC 생성: VS IHC
- 슬라이드 업로드, annotation, 사용자별 AI 결과 편집본 저장
- 감사 로그, 권한 관리, 파일 무결성 검증

최종 진단과 치료 결정은 반드시 의사가 수행해야 한다.

---

## 3. 사용 한계와 주의사항

- 본 소프트웨어는 단독 진단 도구가 아니다.
- AI 결과는 병리의 검토와 필요 시 수정을 거쳐야 한다.
- 학습 데이터 범위를 벗어난 조직, 염색, 스캐너, fixation 상태에서는 성능이 저하될 수 있다.
- VS IHC 결과는 연구·교육용 우선이며 실제 IHC 염색을 대체하지 않는다.
- 사용자 편집본은 사용자별로 분리 저장되고 원본 AI 캐시는 보존된다.
- 슬라이드 색감은 ICC 프로파일과 스캐너 특성에 영향을 받는다. Hamamatsu NDPI는 NDP 색보정 토글을 사용할 수 있다.
- AI 모델, cutoff, score 해석 기준은 병원 SOP와 검증 데이터에 맞춰 검토해야 한다.

---

## 4. 시스템 요구사항

| 항목 | 권장 사양 |
| --- | --- |
| 서버 OS | Linux 또는 Windows 11 |
| Python | 3.12+ |
| DB | MongoDB 7.0+ |
| GPU | NVIDIA CUDA 11.8+ 권장 |
| RAM | 64 GB+ 권장 |
| 디스크 | NVMe SSD, 슬라이드 원본 + 타일 캐시 50 GB+ |
| 브라우저 | Chrome, Edge, Safari 최신 |
| 네트워크 | 병원 내부망 또는 승인된 온프레미스 네트워크 |

지원 파일 형식: SVS, NDPI, VMS, VMU, SCN, MRXS, TIFF/TIF, PNG, JPG/JPEG.

---

## 5. 사용자 역할

| 역할 | 관리자 페이지 | AI 분석 | Annotation 저장 | 폴더 설정 | 슬라이드 조회 |
| --- | :---: | :---: | :---: | :---: | :---: |
| admin | O | O | O | O | O |
| doctor | X | O | O | O | O |
| viewer | X | X | X | X | O |

- 첫 가입자는 자동으로 admin이 되며 즉시 승인된다.
- 이후 가입자는 viewer + pending 상태로 생성되고 admin 승인이 필요하다.
- viewer는 슬라이드를 볼 수 있지만 AI 실행, annotation 저장, 폴더 설정 변경은 할 수 없다.

---

## 6. 빠른 시작

1. 브라우저에서 병원 서버 주소로 접속한다.
2. 로그인한다. 계정이 없으면 회원가입 후 관리자 승인을 기다린다.
3. 좌측 폴더 트리에서 슬라이드를 선택한다.
4. 뷰어에서 마우스 휠로 줌, 드래그로 팬한다.
5. 필요하면 annotation ROI를 그린다.
6. 우측 AI 패널에서 모델을 선택하고 분석을 실행한다.
7. 결과를 검토하고 필요한 셀을 수정한다.
8. 편집본을 저장하거나 Visualize/PDF Export로 보고서를 만든다.

---

## 7. 로그인과 회원가입

### 회원가입

1. 로그인 화면에서 회원가입을 선택한다.
2. 아이디, 비밀번호, 이름, 부서를 입력한다.
3. 아이디는 4~30자 영문, 숫자, 언더스코어만 허용된다.
4. 비밀번호는 8자 이상이며 대문자, 소문자, 숫자, 특수문자를 모두 포함해야 한다.
5. 가입 후 관리자 승인 전까지 로그인할 수 없다.

### 로그인

1. 아이디와 비밀번호를 입력한다.
2. MFA가 활성화된 사용자는 6자리 TOTP 코드를 추가 입력한다.
3. 로그인 실패가 5회 누적되면 30분 동안 계정이 잠긴다.
4. 잠금 해제는 시간이 지나면 자동으로 처리되며, 필요 시 admin이 해제할 수 있다.

---

## 8. 2차 인증과 비밀번호

### MFA 활성화

1. 사용자 메뉴에서 2차 인증 설정을 연다.
2. QR 코드를 Google Authenticator, Microsoft Authenticator 등으로 스캔한다.
3. 앱에 표시된 6자리 코드를 입력해 활성화한다.
4. 다음 로그인부터 비밀번호와 TOTP 코드가 모두 필요하다.

휴대폰을 분실하면 관리자에게 MFA 비활성화를 요청한다.

### 비밀번호 변경

1. 사용자 메뉴에서 비밀번호 변경을 선택한다.
2. 현재 비밀번호와 새 비밀번호를 입력한다.
3. 변경 완료 후 모든 세션이 폐기되며 다시 로그인해야 한다.

---

## 9. 화면 구성

```text
상단 툴바: 열기, 줌, Fit, 도구, 사용자 메뉴
좌측 패널: 폴더 트리, 슬라이드 목록, 썸네일
중앙 영역: WSI Canvas 뷰어, 미니맵, 좌표 표시
우측 패널: AI 모델, 결과 목록, annotation 패널
```

모바일과 태블릿에서는 좌우 패널이 drawer 형태로 접힌다.

---

## 10. 슬라이드 업로드와 관리

### 업로드

1. 좌측 패널에서 대상 폴더를 선택한다.
2. 업로드 버튼을 누른다.
3. 파일을 선택하거나 drag-and-drop 한다.
4. 5 MB 청크 단위로 업로드된다.
5. 완료 후 서버가 타일을 생성하고 SHA-256 체크섬을 계산한다.

### 관리

- 폴더 생성, 이름 변경, 삭제
- 슬라이드 이동, 삭제, 상태 플래그 변경
- 상태 플래그: pending, in_progress, done, flagged
- 무결성 검증: 저장된 SHA-256과 현재 파일 해시 비교

삭제 시 원본 파일, 타일 캐시, AI 결과 캐시, DB 문서가 함께 정리된다.

---

## 11. WSI 뷰어 조작

| 동작 | 데스크톱 | 모바일 |
| --- | --- | --- |
| 팬 | 좌클릭 드래그 | 한 손가락 드래그 |
| 줌 | 마우스 휠 | 두 손가락 핀치 |
| Fit | Fit 버튼 | Fit 버튼 |
| 미니맵 이동 | 미니맵 클릭 | 미니맵 터치 |
| 그리기 취소 | ESC 또는 우클릭 | ESC 지원 환경 |

- 처음 열 때 3-stage 타일 로딩 오버레이가 표시된다.
- 로딩 100%는 화면에 필요한 초기 타일 다운로드 완료를 의미한다.
- 우하단에는 슬라이드 픽셀 좌표가 표시된다.

---

## 12. Annotation

| 도구 | 용도 |
| --- | --- |
| Polygon | 자유형 ROI 그리기 |
| Rectangle | 사각형 ROI 그리기 |
| Point | 특정 지점 표시 |
| 1 mm² Rectangle/Circle | 정량 분석용 고정 면적 ROI |
| Ruler | 두 점 거리 측정 |

사용 방법:

1. 툴바에서 도구를 선택한다.
2. 슬라이드 위에 ROI나 점을 만든다.
3. 우측 Annotation 패널에서 이름, 색상, 표시 여부를 조정한다.
4. 저장 버튼을 눌러 슬라이드별 annotation JSON으로 보관한다.

viewer 역할은 annotation을 그릴 수 있어도 저장할 수 없다.

---

## 13. 색 보정

- ICC 프로파일이 있는 슬라이드는 서버에서 sRGB 변환을 적용한다.
- Hamamatsu NDPI는 NDP.view2와 색감 차이가 날 수 있다.
- Hamamatsu 슬라이드에서는 NDP 색보정 토글을 켜서 서버의 보정 타일을 사용할 수 있다.
- 첫 토글 시 보정 타일 캐시를 만들기 때문에 조금 느릴 수 있고, 이후에는 캐시가 사용된다.

---

## 14. Quanti HE

Quanti HE은 H&E 슬라이드에서 세포를 검출하고 클래스를 분류한다.

실행 절차:

1. H&E 슬라이드를 연다.
2. 우측 Quanti HE 탭에서 조직 타입을 고른다: Stomach, Breast, Other.
3. 필요하면 ROI polygon을 미리 그린다.
4. 분석 시작을 누른다.
5. 완료 후 세포 점 오버레이와 클래스별 카운트를 확인한다.

Stomach와 Breast는 Epithelial 세포를 Tumor Epithelial / Benign Epithelial로 재분류한다.

---

## 15. Quanti PD-L1

Quanti PD-L1는 PD-L1 IHC 슬라이드에서 CPS 또는 TPS를 계산한다.

| 조직 | 점수 |
| --- | --- |
| Stomach | CPS |
| Lung | TPS |

실행 절차:

1. PD-L1 IHC 슬라이드를 연다.
2. PD 탭에서 조직 타입을 선택한다.
3. 필요하면 ROI를 지정한다.
4. 분석을 실행한다.
5. 완료 후 점수 카드, 셀 분포, 오버레이를 검토한다.

Confidence cutoff는 재현성을 위해 고정 기준으로 관리된다.

---

## 16. Quanti IHC

Quanti IHC는 IHC marker별 세포 염색 강도와 score를 계산한다.

| Marker | 결과 |
| --- | --- |
| HER2 | 0~3.0 가중 평균, dominant class |
| ER/PR | Allred PS + IS = TS |
| Ki-67 | Labeling Index, High/Low |

실행 절차:

1. IHC 슬라이드를 연다.
2. IHC 탭에서 HER2, ER_PR, KI_67 중 하나를 선택한다.
3. 분석을 실행한다.
4. 결과 점수와 셀 오버레이를 검토한다.
5. 셀 편집 시 점수가 즉시 재계산되는지 확인한다.

---

## 17. VS IHC

VS IHC는 H&E 슬라이드에서 가상 IHC 이미지를 생성한다.

실행 절차:

1. H&E 슬라이드를 연다.
2. VS 탭에서 stain type을 선택한다.
3. target MPP를 선택한다. 낮을수록 고해상도지만 시간이 더 걸린다.
4. 분석을 실행한다.
5. 완료 후 overlay 또는 split view로 원본과 비교한다.

주의: VS IHC는 실제 IHC 염색을 대체하지 않는다.

---

## 18. AI 결과 편집

AI 분석 완료 후 사용자는 세포 단위 결과를 검토하고 수정할 수 있다.

- edit: 셀 클릭 후 클래스 변경
- multi: 여러 셀 선택 후 일괄 변경
- add: 빈 위치에 새 셀 추가
- delete: 선택 셀 삭제
- sticky class: Shift 키를 누르면 현재 추가 클래스가 HUD로 표시됨

Quanti PD-L1, Quanti IHC 점수는 셀 변경 즉시 재계산된다.

---

## 19. 결과 저장과 불러오기

- Save: 현재 결과를 본인 사용자 편집본으로 저장한다.
- Load: 같은 슬라이드, 같은 모델, 같은 variant의 저장본 목록을 본다.
- 다른 사용자 편집본은 불러와 비교할 수 있다.
- 본인 편집본만 삭제할 수 있다.
- 원본 AI 추론 캐시는 편집본 저장으로 바뀌지 않는다.

---

## 20. Visualize와 PDF Export

Visualize 다이얼로그는 모델별 결과를 여러 탭으로 보여준다.

- Class Distribution
- Tumor Analysis
- Spatial Heatmap
- Confidence Distribution
- Score Card

PDF Export는 슬라이드명, 모델, variant, score, 프리뷰, 카운트 표를 포함한 보고서를 만든다.

---

## 21. 폴더 자동 AI 추론

폴더별로 자동 실행할 AI 작업을 설정할 수 있다.

1. 폴더를 선택하고 자동 AI 설정을 연다.
2. 모델과 variant를 추가한다.
3. Enable을 켠다.
4. 워커가 60초 주기로 미완 슬라이드를 찾아 실행한다.

업로드 중, 사용자가 뷰어를 조작 중, 시스템이 바쁜 상태에서는 자동 AI가 양보한다.

---

## 22. 관리자 작업

### 사용자 승인

1. 관리자 페이지에서 승인 대기 탭을 연다.
2. 신규 사용자의 역할을 선택한다.
3. 승인 또는 거부를 누른다.
4. 거부 시 사유를 입력한다.

### 사용자 관리

- 역할 변경
- 활성/비활성 전환
- 잠금 해제
- 사용자 삭제
- 마지막 admin 보호

### 활동 로그

- 로그인, 슬라이드 조회, AI 분석 이력을 확인한다.
- IP, 위치, 디바이스 정보를 함께 본다.
- HMAC 체인 검증으로 감사 로그 변조 여부를 점검한다.

---

## 23. 운영 점검과 백업

권장 점검:

- 월 1회 감사 로그 HMAC 체인 검증
- 월 1회 임의 슬라이드 SHA-256 무결성 검증
- 타일 캐시 용량 확인
- AI 결과 캐시와 사용자 편집본 백업 정책 확인

백업 권장 대상:

- MongoDB `users`
- MongoDB `audit_logs`
- MongoDB `slides`
- `backend/.secrets.json` 별도 안전 보관
- 필요한 경우 `uploads`, `ai_results`

주의: `.secrets.json`을 잃으면 기존 JWT, 암호화 필드, pepper 기반 비밀번호 검증에 문제가 생길 수 있다.

---

## 24. 자주 발생하는 문제

| 증상 | 조치 |
| --- | --- |
| 로그인 후 빈 화면 | 새로고침 또는 재로그인 |
| 계정 잠김 | 30분 대기 또는 admin 잠금 해제 요청 |
| MFA 코드 오류 | 휴대폰 시간 자동 동기화 확인 |
| 슬라이드가 흐리게 보임 | 초기 타일 로딩이 끝날 때까지 대기 |
| Hamamatsu 색감 차이 | NDP 색보정 토글 ON |
| AI 결과가 이전과 같음 | 캐시 hit 가능성 확인 |
| 업로드 실패 | 파일 크기, 디스크 여유 공간, 네트워크 확인 |
| PDF 한글 표시 문제 | 서버/브라우저 폰트 환경 확인 |

---

## 25. 용어

| 용어 | 뜻 |
| --- | --- |
| WSI | Whole Slide Image, 전체 슬라이드 이미지 |
| MPP | Microns per pixel, 픽셀당 마이크로미터 |
| ICC | 색공간 보정 프로파일 |
| ROI | Region of Interest, 관심 영역 |
| CPS | Combined Positive Score |
| TPS | Tumor Proportion Score |
| Allred | ER/PR 점수 체계 |
| LI | Labeling Index |
| TOTP | 시간 기반 1회용 인증 코드 |
| SaMD | Software as a Medical Device |

---

## 26. 참고 문서

- [PRODUCT_BROCHURE.md](PRODUCT_BROCHURE.md) — 제품 소개서
- [FEATURES.md](FEATURES.md) — 전체 기능 명세
- [SECURITY.md](SECURITY.md) — 보안 설계와 SaMD 통제
- [COMPLIANCE_STATUS.md](COMPLIANCE_STATUS.md) — 규제 충족 현황
- [DATABASE.md](DATABASE.md) — DB 스키마
- [color_match_analysis.md](color_match_analysis.md) — 색 보정 분석

---

## 부록. PPT 변환 안내

이 문서는 `##` 단위로 슬라이드 변환하기 쉽게 구성했다.

```bash
pandoc docs/USER_GUIDE.md -o USER_GUIDE.pptx --reference-doc=template.pptx
npx @marp-team/marp-cli docs/USER_GUIDE.md --pptx -o USER_GUIDE.pptx
```
