# MeDIAuto Studio ↔ NDP.view2 색상 매칭 분석

## 1. 배경 & 목표

Hamamatsu NDPI 슬라이드는 ICC 프로파일이 임베드되어 있지 않다. 서버는 1차로 `γ=1.8 + Target.White.Intensity=235` 기반 전처리를 적용해 타일을 저장하지만, 이 결과는 **NDP.view2** 가 보여주는 색감과 완전히 일치하지 않는다.

- 원인: NDP.view2 가 ISP 단계에서 추가로 톤 커브 + 색공간 변환을 적용하는 것으로 보이는데, 공개된 사양이 없음.
- 목표: 두 뷰어의 출력이 최대한 일치하도록 **클라이언트 사이드 추가 보정식** 을 데이터 기반으로 유도.
- 방침: 서버 저장 타일은 그대로 두고, 사용자가 뷰어에서 토글로 ON/OFF 할 수 있게 함.

---

## 2. 데이터

| 항목 | 값 |
| --- | --- |
| 페어 수 | 5쌍 |
| 이미지 크기 | 960 × 1072 px (전 페어 동일) |
| 슬라이드 종류 | Hamamatsu NDPI (HE/IHC 혼합) |
| MeDIAuto 쪽 | 서버 γ=1.8 / white=235 전처리 후 렌더된 타일 스크린샷 |
| NDP 쪽 | NDP.view2 창 캡처 |
| 정합 상태 | 동일 해상도 + 스크린샷 기반 → phase correlation 으로 확인 후 정합 성공 |

저장 경로:
- `hamamastu/mediauto_studio/{1..5}.jpg`
- `hamamastu/ndp_viewer/{1..5}.jpg`

---

## 3. 분석 방법

분석 노트북: [`color_match_analysis.ipynb`](../color_match_analysis.ipynb) (프로젝트 루트). 주요 단계:

1. **기본 통계** — 전체 mean/median, 배경 99 percentile (≥180 픽셀), 조직 10 percentile (≤160 픽셀)
2. **채널별 히스토그램 오버레이** — R/G/B 분포 겹치기
3. **CDF 매칭 LUT** — 분포 기반 경험적 256-entry LUT 산출 (pool 전체)
4. **phase correlation 으로 pixel 정합 확인**
5. **pixel-wise 2D density map** — MeDIAuto vs NDP 의 채널별 산점도 (log-scale 밀도)
6. **NLLS γ/white 피팅** — `scipy.optimize.least_squares` 로 `v_ndp = 255·(v_m / white)^(1/γ)` 채널별 + 글로벌 피팅
7. **3×3 CCM 및 3×4 affine 피팅** — `np.linalg.lstsq` 로 γ 보정 후 잔차를 선형 변환으로 흡수
8. **공간 잔차 맵** — 페어마다 `|Δ|` 히트맵으로 공간적 오차 분포 확인

---

## 4. 결과

### 4-1. γ / white 피팅 (pixel-wise NLLS)

500k 무작위 subsample 기준, 채널별 및 전 채널 공통 글로벌 값:

| Channel | γ | white | RMSE |
| --- | --- | --- | --- |
| R | 1.039 | 247.38 | 5.73 |
| G | 1.067 | 247.27 | 4.67 |
| B | 1.293 | 252.09 | 3.93 |
| **Global** | **1.094** | **247.91** | **5.20** |

- γ 가 모든 채널에서 1 근처 → raw 에 추가 감마 보정은 거의 필요 없음 (서버가 이미 γ=1.8 을 걸어 놓음).
- white ≈ 248 → 서버의 γ=1.8/235 처리가 배경을 약간 252 근처까지 올려 놓은 결과와 일치.
- 채널 간 γ 차이가 존재 (R/G 1.04~1.07, B 1.29) → 단일 γ 로는 100% 일치 어려움, 보완이 필요.

### 4-2. 3×3 CCM (bias 없음)

γ 보정 후의 선형화 값에 `v_ndp ≈ v' @ M` 최소제곱:

```
[[ 1.4031  -0.1472   0.1164 ]
 [ 0.0369   1.067   -0.1092 ]
 [-0.4389   0.0832   0.9837 ]]
```

### 4-3. 3×3 + bias (affine)

블랙 레벨 오프셋을 함께 잡는 3×4 affine:

```
matrix:
[[ 1.3986  -0.1898   0.0633 ]
 [ 0.0432   1.1274  -0.034  ]
 [-0.449   -0.0141   0.8625 ]]

bias: [ 2.0654  19.8732  24.7427 ]
```

- 대각 성분이 R: 1.40, G: 1.13, B: 0.86 → 채널별 스케일이 다름을 확인. 특히 **R 을 올리고 B 를 내림**.
- bias 가 G: +19.87, B: +24.74 로 큼 → 서버 전처리 이후의 어두운 톤에 offset 이 밀려 있었다는 뜻 (NDP 쪽이 더 밝은 블랙 레벨).
- row 2 (B 입력) → R 출력 성분이 -0.449: 파랑 성분이 강할 때 빨강을 깎음 (헤마톡실린 영역의 보라 톤 조정으로 해석 가능).

### 4-4. 모델별 RMSE 비교

| 모델 | RMSE | γ-only 대비 감소 |
| --- | --- | --- |
| γ-only (global) | 5.20 | 기준 |
| γ + 3×3 CCM | 4.37 | -16.0% |
| γ + affine (bias 포함) | **4.21** | **-19.0%** |

**γ + affine** 이 최적. affine 이 CCM 대비 추가 개선이 있는 것은 bias 성분이 유의미했다는 증거.

### 4-5. 공간적 잔차

모든 페어에서 γ-only 의 `|Δ|` 평균은 3–6 대역, affine 은 2–4 대역. **조직 경계의 진한 톤 (DAB 갈색 / Eosin 진한 핑크)** 에서 잔차가 크며, affine 적용 후에도 완전히 0 으로 떨어지진 않음 → 비선형적 톤 왜곡이 일부 남아 있으나 일반 판독 용도로 허용 가능한 수준.

---

## 5. 결론 및 프로젝트 적용

### 최종 선택
**`γ=1.094 + white=247.91 + 3×4 affine`**

### 적용 방식
1. **서버 저장 타일은 변경하지 않음.** 디스크 JPEG 는 현재 NDP 1차 전처리 (γ=1.8 / white=235) 가 이미 입혀진 상태로 유지.
2. **클라이언트 사이드에 2차 보정**을 얹음:
   - Hamamatsu 슬라이드에서만 **뷰어 왼쪽 위에 "NDP 색보정" 토글 버튼** 표시.
   - ON 시 받은 JPEG 타일을 `colorCorrectBitmap()` 으로 γ + affine 처리한 canvas 로 캐시.
   - OFF 시 raw JPEG 을 그대로 렌더.
   - 썸네일도 동일 규칙.
3. 상수는 [`frontend/js/color-correction.js`](../frontend/js/color-correction.js) 의 `NDP_FIT` 에서 관리.

### 핵심 코드 위치
| 파일 | 역할 |
| --- | --- |
| `frontend/js/color-correction.js` | 피팅 상수 + LUT + `colorCorrectBitmap(src)` |
| `frontend/js/tile-viewer.js` | `_tileCacheCorrected` 듀얼 캐시 + `setColorCorrectionEnabled()` |
| `frontend/js/app.js` | 벤더 감지 후 버튼 show/hide + 클릭 핸들러 |
| `frontend/app.html` | `#btn-ndp-color` 토글 버튼 |
| `frontend/css/style.css` | `.ndp-color-toggle` 스타일 (좌상단 고정) |

### 주의사항
- **AI 분석 경로에는 이 2차 보정 적용 안 함.** AI 모델은 raw 톤에 학습돼 있어 입력 색이 바뀌면 정확도 저하 우려.
- 벤더가 Hamamatsu 가 아니면 버튼 자체 hidden — 다른 스캐너에 피팅 값이 맞지 않음.

---

## 6. 재현 방법

```bash
# 환경: conda env yslee (pymongo, scipy, numpy, PIL, matplotlib 필요)
# 노트북 실행
cd c:/Users/liive/OneDrive/Desktop/project/Mediauto-studio_saas
jupyter lab color_match_analysis.ipynb
```

§1~§6 (기본 통계 / 히스토그램 / CDF LUT) 은 정합 없이도 동작. §8~§12 (pixel-wise 피팅) 은 phase correlation 기반 정합이 선행. 새 페어를 추가하려면 같은 사이즈로 `hamamastu/mediauto_studio/N.jpg` + `hamamastu/ndp_viewer/N.jpg` 에 저장하면 자동 인식.

---

## 7. 다음 단계 (선택 사항)

- 페어 수 확장 (5 → 20~30) 후 재피팅하면 RMSE 가 더 낮아질 수 있음 (특히 IHC 진한 갈색 영역 보강).
- H&E 전용 / IHC 전용 두 피팅으로 나눠 stain-class 별 모델 운영도 가능. 다만 현재 단일 글로벌 모델로도 육안 차이가 미미하면 유지 비용이 큰 만큼 권장하지 않음.
- 슬라이드 종류(스캐너 모델 / firmware) 가 바뀌면 재피팅 필요. Target.White.Intensity 값을 따로 로깅해 두면 모니터링 편함.

---

## 부록: 핵심 수식

```
# Stage 1 — 서버에서 이미 적용 (slide_manager._build_ndp_lut)
v_s1 = 255 · clip(v_raw / 235, 0, 1)^(1/1.8)

# Stage 2 — 클라이언트 토글로 ON/OFF (color-correction.js)
v_s2 = 255 · clip(v_s1 / 247.91, 0, 1)^(1/1.094)

# Stage 3 — Stage 2 결과에 3×4 affine 적용
v_out[c] = sum_k( v_s2[k] · M[k,c] ) + bias[c]

  M = [[ 1.3986, -0.1898,  0.0633],
       [ 0.0432,  1.1274, -0.034 ],
       [-0.449,  -0.0141,  0.8625]]
  bias = [2.0654, 19.8732, 24.7427]
```

최종 전체 파이프라인: `raw → Stage 1 (server) → Stage 2 + 3 (client, toggle-gated) → display`.
