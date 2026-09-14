# MeDIAuto 플랫폼 차별성 — 비주얼 브리프 v2.0

작성일: 2026-09-14. 기존 기술 분석 문서를 보완하는 11페이지 가로형 문서입니다.

- `MeDIAuto_visual_differentiation_v2.pdf`: 공유·검토용 전체 문서
- `MeDIAuto_visual_differentiation_v2.docx`: 본문과 설명을 수정할 수 있는 Word 원본. 인포그래픽 내부 글자는 이미지입니다.
- `MeDIAuto_visual_differentiation_v2.html`: 이미지를 클릭해 확대할 수 있는 화면 중심 요약. 특허 연결표까지 포함한 전체 내용은 PDF·Word에서 확인합니다.
- `visual-content.json`: 화면별 제목·설명 및 비교 출처
- `assets/infographic-workflow.png`: 전체 작업 흐름 개념도
- `assets/infographic-tiles.png`: 화면 요청과 타일 생성 처리 개념도
- `assets/generation-prompts.json`: 내장 `image_gen.imagegen`으로 제작할 때 사용한 정확한 프롬프트 2개
- `assets/screenshot-sources.json`: 실제 스크린샷 6장의 저장소 출처

실제 스크린샷은 `figure/manual-redacted/`의 기존 비식별 사본을 변경 없이 복사했습니다. 이미지 속 UI는 촬영 당시 기준이며 현재 소스와 명칭·배치가 다를 수 있습니다. 생성 인포그래픽은 실제 제품 화면과 구분해 표시했습니다. 기존 8페이지 분석 문서는 상위 폴더에 보존했습니다.

## 재생성

Python의 `python-docx`, `Pillow`와 시스템의 LibreOffice가 필요합니다. 애플리케이션 환경과 분리한 임시 의존성 경로에서 이번 문서를 생성했습니다.

```bash
PYTHONPATH=/tmp/mediauto-report-deps python docs/platform-differentiation/visual-v2/build_visual.py
```

다른 환경에서는 별도 가상환경에 의존성을 설치한 후 `python build_visual.py`를 실행합니다. 인포그래픽은 재사용하며 빌드 시 이미지 생성 API를 호출하지 않습니다.

검증: PDF 11페이지, Word 내 이미지 8개 및 출처 링크 20개, 스크린샷 사본과 출처 파일의 바이트 일치, 주요 페이지의 렌더링을 확인했습니다. 이번 작업은 문서 변경이며 앱 버전·코드·배포를 변경하지 않았습니다.
