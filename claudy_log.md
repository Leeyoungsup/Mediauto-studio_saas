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
