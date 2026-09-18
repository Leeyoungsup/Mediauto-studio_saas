# Windows / Linux 공통 경로 설정

앱은 `backend/app/config.py`에서 환경변수를 읽습니다. 실제 PC의 절대 경로는 코드에 넣거나 Git에 커밋하지 않습니다. 환경변수를 생략하거나 공백으로 두면 기존 프로젝트 기본 경로를 사용합니다. 상대 경로는 실행 터미널 위치와 무관하게 `backend` 기준입니다.

| 환경변수 | 기존 프로젝트 기본값 | 설치기 설정 |
|---|---|---|
| `MODEL_DIR` | `backend/model` | 선택한 모델 폴더 |
| `UPLOAD_DIR` | `backend/uploads` | 선택한 슬라이드 폴더 |
| `TILES_DIR` | `backend/tiles` | 외부 루트의 tiles |
| `AI_RESULTS_DIR` | `backend/ai_results` | 외부 루트의 results |
| `ANNOTATIONS_DIR` | `backend/annotations` | 외부 루트의 annotations |
| `CELL_ANNOTATION_DIR` | `backend/cell_annotation` | 외부 루트의 patches |
| `DICOM_CACHE_DIR` | `backend/dicom_cache` | 외부 루트의 dicom |
| `MEDIAUTO_SECRETS_FILE` | `backend/.secrets.json` | 외부 루트의 secrets/.secrets.json |
| `OPENSLIDE_PATH` | 패키지/시스템 및 기존 libs 탐색 | 별도 DLL 디렉터리가 필요한 경우 지정 |
| `PHILIPS_PYTHON` | Conda 환경 조회 | 설치기가 확인한 Philips Python 실행 파일 |

두 설치 메뉴, Windows와 Linux 모두 동일한 환경변수 이름을 사용합니다. 네이티브 및 Docker 메뉴의 로컬 실행 설정은 외부 `config/app.json`에 저장됩니다. Docker 실행은 외부 `config/app.env`에 컨테이너 내부 경로를 지정하고 실제 호스트 폴더를 마운트합니다. 따라서 Windows 호스트 경로를 Linux 컨테이너에 그대로 전달하지 않습니다.

기존 설치의 설정 파일은 설치기를 재실행할 때 갱신됩니다. 새 소스에서는 패치·비밀키 경로용 심볼릭 링크가 필요 없습니다. 이전 브랜치는 설정을 지원하지 않을 수 있으므로 설치기는 호환 링크를 유지합니다. 기존 링크나 데이터는 자동 삭제하거나 이동하지 않습니다.

설치 완료 후 앱은 자동 실행하지 않습니다. `native/start.bat` / `bash native/start.sh`, Docker 메뉴의 로컬 개발은 `docker/start-local.bat` / `bash docker/start-local.sh`로 실행합니다. 소스를 수정한 뒤 서버를 재시작하세요. `application` 안의 원본 start 스크립트는 설치기의 app.json을 읽지 않으므로 설치기용 상위 실행 스크립트를 사용하세요.

일반 프로젝트 실행은 현재 프로세스 환경변수 또는 Git에서 제외된 `.env.postgres`를 사용합니다. 환경변수 이름은 같고 값만 PC별로 다릅니다. Windows `.env.postgres`는 `KEY=value` 형식입니다. Linux에서 source하는 파일은 셸 문법을 사용하므로 공백 포함 값에는 따옴표가 필요합니다.

`medicus-saas`, `philips-sdk-py37`(Windows), `philips-sdk-py38`(Linux)의 실제 경로는 Conda에서 조회합니다. 설치기 실행은 확인된 Philips Python을 명시적으로 전달합니다.

비밀키 파일은 기존 파일을 계속 사용해야 기존 암호화 데이터와 인증 설정을 유지할 수 있습니다. 경로만 바꾸면서 빈 파일을 새로 생성하지 마세요. 브랜치 병합은 코드만 병합하며, 각 PC의 DB·설정·데이터·비밀키는 독립적으로 유지합니다. DB 마이그레이션과 OS 전용 DLL 변경은 각 환경에서 별도 검증해야 합니다.

## 2026-09-18-r11: 데이터 경로 Git 추적 방지

Windows·Linux, 메뉴 1·2 모두 소스 준비 단계에서 다음 사항을 확인합니다.

- 설정한 저장 경로가 `application` Git 체크아웃 내부이면 설치를 중단합니다. 외부 폴더를 지정해야 합니다.
- `backend/cell_annotation`, `.secrets.json`, uploads, tiles, ai_results, annotations, dicom_cache, model이 Git에 추적 중이면 설치를 중단합니다. 설치기가 자동으로 파일을 삭제하거나 Git 인덱스를 변경하지 않습니다. 소스 브랜치에서 추적 제외를 커밋한 뒤 재시도하세요.
- 추적되지 않은 데이터 경로와 호환 링크는 해당 체크아웃의 `.git/info/exclude`에도 등록합니다. 디렉터리 안의 파일뿐 아니라 링크 자체도 제외합니다.

제외 규칙은 이미 추적된 파일이나 강제 `git add -f`를 차단하지 않습니다. 다른 브랜치에서도 데이터 경로 추적 삭제를 반영하세요. 설치기는 기존 소스를 자동 pull/reset하지 않으므로, 기존 설치의 브랜치는 사용자가 직접 업데이트해야 합니다.

앱 버전은 바꾸지 않았으며 이 날짜·번호는 설치 패키지의 개정 번호입니다. 설치 후 앱 자동 실행은 하지 않습니다.
