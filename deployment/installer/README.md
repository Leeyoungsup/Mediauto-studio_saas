# MeDIAuto 통합 GPU 설치기

압축을 풀고 Windows는 **install.bat**, Linux는 **bash install.sh**를 실행하세요.
첫 화면에서 설치 방식을 선택합니다.

| 선택 | 앱 실행 환경 | 코드 |
|---|---|---|
| 1. Docker GPU (기본) | CUDA용 PyTorch, OpenSlide, libvips가 준비된 Linux 컨테이너 | Docker Hub `haribo1/mediautoai:3.3.2-gpu` |
| 2. 네이티브 GPU | PC의 Python 가상환경 | GitHub 저장소의 선택한 branch/tag/commit |

두 방식 모두 PostgreSQL은 PC에 직접 설치합니다. CPU로 자동 전환하지 않습니다.
Windows는 지원되는 Windows 10/11 x86-64, Linux는 Ubuntu 22.04 이상 / Debian 12 이상 x86-64 + systemd를 대상으로 합니다.
최초 설치에 인터넷과 관리자 권한이 필요합니다. Windows에 winget이 없으면 App Installer 설치를 안내합니다.
Docker 방식은 WSL 활성화 후 재부팅이 필요할 수 있으며, 같은 install.bat를 다시 실행하면 됩니다.

## 저장 위치: 세 가지만 입력

1. **외부 저장 루트** — 예: `D:\MeDIAutoData` 또는 `/mnt/data/mediauto`
2. **모델 폴더** — 예: `E:\Models`. 기존 모델 11개가 들어 있는 폴더를 지정합니다.
3. **슬라이드 폴더** — 별도 위치를 입력하거나, 빈칸으로 엔터를 누르면 `<외부 저장 루트>/slides` 사용.

그다음 웹 포트(기본 18093), DB 포트(기본 55432), 웹 bind를 입력합니다.
현재 18093을 사용하는 서비스가 있다면 18094 등 비어 있는 포트를 선택하세요.
웹 bind `0.0.0.0`은 LAN 공유, `127.0.0.1`은 해당 PC만 접속 허용입니다.
다른 PC에서는 `http://서버IP:포트`로 접속합니다.

외부 저장 루트의 기본 구성:

```text
MeDIAutoData/
  slides/          슬라이드 경로를 비웠을 때 사용
  patches/         추출 패치와 세포 주석 파일
  results/         AI 분석 결과
  annotations/     파일 기반 주석
  logs/            앱 실행·요청·오류 로그
  tiles/           뷰어 타일 캐시
  dicom/           DICOM 해제 캐시
  cache/           라이브러리·모델 다운로드 캐시
  app_config/      라이브러리 사용자 설정
  temp/            임시 작업 파일
  secrets/         앱 암호화·서명 키
  database/        PostgreSQL 데이터와 database/log 서버 로그
  config/          설치 설정, DB 접속 정보, 최초 로그인 정보
```

계정·활동 로그·프로젝트·일부 주석은 PostgreSQL에 저장됩니다. DB와 secrets를 함께 백업하세요.
Docker 앱 로그는 logs/app.log로 저장하며 파일당 20 MiB, 백업 10개로 순환합니다.
Docker 로그 드라이버는 none입니다. `docker logs` 대신 호스트의 logs/app.log를 확인하세요.
컨테이너 재생성 또는 앱 정지는 외부 폴더를 지우지 않습니다. 파일 삭제·디스크 고장은 별도 백업이 필요합니다.

설치 폴더에는 비밀정보 없는 `.install-location.json` 경로 포인터만 두며 실제 설정은 외부 루트/config에 있습니다.
설치 코드·PostgreSQL 실행 파일은 설치 폴더에도 필요하므로 이 폴더를 설치 후 임의로 옮기지 마세요.

## GitHub 인증 / 관리자

Docker 방식도 GitHub 소스를 clone합니다. 환경은 Docker Hub GPU 이미지를 기반으로 빌드합니다. 비공개 저장소에는 GitHub 인증이 필요합니다.
초기 관리자 ID는 `admin`, 비밀번호는 `admin1234!`입니다. 최초 로그인 정보는 `<외부 루트>/config/ADMIN_LOGIN.txt`에서 확인합니다.

네이티브 방식은 GitHub 저장소(기본 Leeyoungsup/Mediauto-studio_saas), 브랜치(기본 main),
GitHub 아이디와 PAT를 입력합니다. 앱 초기 관리자 ID는 `admin`, 비밀번호는 `admin1234!`입니다.
GitHub 계정 비밀번호는 사용할 수 없습니다. 숨김 입력란에 대상 저장소 Contents: read 권한의 PAT를 넣으세요.
PAT는 파일·로그·URL·명령줄 인자에 저장하지 않습니다. 공개 저장소는 아이디를 비울 수 있습니다.

## GPU 준비

NVIDIA GPU와 정상 동작하는 호스트 드라이버가 먼저 필요합니다. 설치 전 `nvidia-smi`가 성공해야 합니다.
드라이버 설치/업데이트는 GPU 기종과 OS에 맞춰 별도로 해야 하며 이 설치기는 드라이버를 임의 교체하지 않습니다.
두 방식 모두 PyTorch 2.11.0 + torchvision 0.26.0 CUDA 12.8 패키지를 사용합니다.
모델에 필요한 GPU 구조/드라이버 호환성이 있어야 하며, 앱 시작 전 CUDA 행렬 연산과 torchvision NMS를 검사합니다.
Windows Docker는 Docker Desktop WSL2 GPU 지원을 사용합니다. Linux Docker는 NVIDIA Container Toolkit 설치/설정을 포함합니다.
Toolkit 최초 설정 시 Docker 재시작이 필요하므로 다른 컨테이너가 실행 중이라면 재시작을 고려하세요.

Docker가 이미 설치됐지만 GPU 연결 도구만 없다면 Ubuntu/Debian에서 다음을 사용할 수 있습니다.
`sudo bash setup-nvidia-runtime.sh` — Toolkit 설치와 Docker 재시작을 수행합니다.

## 재실행 / 방식 변경

같은 방식을 다시 선택하면 저장된 경로·DB·계정을 재사용합니다.
설치 방식 선택은 **자동 마이그레이션이나 실시간 전환 기능이 아닙니다.**
두 방식을 동시에 설치하려면 서로 다른 외부 루트와 포트를 사용하세요.
기존 데이터가 있는 루트/config 또는 DB 폴더를 새 설치가 덮어쓰지 않도록 중단합니다.
이전 단계에서 받은 여러 경로 입력 방식/CPU 설치본과 자동 호환하거나 기존 Docker를 제거하지 않습니다.

Docker 실행 관리: `docker compose -f <외부 루트>/config/compose.json up -d --wait --wait-timeout 900` / `stop`.
Linux에서는 설정 읽기에 sudo가 필요할 수 있습니다.
네이티브 앱은 자동 시작하지 않습니다. native/start.bat 또는 bash native/start.sh로 실행하고 Ctrl+C로 종료합니다.
PostgreSQL은 두 방식 모두 호스트 서비스로 자동 시작합니다.

## 모델 / 검증 범위

이 작은 설치 묶음에는 모델이 없습니다. 기존 배포본의 models 폴더 등을 먼저 준비하세요.
선택한 모델 폴더에서 해시를 검증하며 파일을 다른 경로로 복사하지 않습니다.
Philips SDK는 배포 폴더의 `Philips_SDK/`에 OS에 맞게 포함됩니다. 네이티브 설치는 SDK 라이선스 동의 확인 후 Conda 환경에 자동 설치하고 브리지 검사를 수행합니다.

경로 기본값·별도 슬라이드 경로·외부 마운트·설정 보존·GitHub 인증 처리 등을 자동 검사했습니다.
호스트 NVIDIA RTX 6000 Ada 2개에서 CUDA 행렬 연산과 torchvision NMS 검사를 통과했습니다.
Windows 전체 설치 및 드라이버별 호환성은 대상 PC에서 검증해야 합니다.

공식 자료:
- https://docs.docker.com/desktop/setup/install/windows-install/
- https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html
- https://pytorch.org/get-started/previous-versions/
- https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens

## Windows Python 감지 수정 (2026-09-16)

시스템/현재 사용자 레지스트리와 기본 설치 경로에서 Python 3.12를 찾고,
64비트 및 SSL·SQLite·venv·ensurepip 모듈을 실행 검증한 뒤 재사용합니다.
사용자용 Python이 있는데 전체 사용자용으로 다시 설치하는 동작을 방지합니다.
기존 Python이 손상된 경우 자동 재설치/설치 범위 변경 대신 복구 안내 후 중단합니다.
이 변경은 Windows Installer 서비스 자체를 복구하는 기능은 아닙니다.

초기 `admin/admin1234!`은 빈 DB의 최초 계정 생성에만 적용됩니다. 기존 설정과 이미 생성된 계정의 비밀번호는 설치기를 재실행해도 변경하지 않습니다.

## Windows PostgreSQL 서비스 누락 복구 (2026-09-16)

DB 초기화는 됐지만 전용 서비스가 없는 경우, 같은 설치기의 재실행으로 서비스 등록을 복구합니다.
설치 소유 정보·DB 경로·PostgreSQL 실행 파일이 일치하는 기존 서비스는 이름이 달라도 재사용합니다.
같은 DB를 가리키는 서비스가 여러 개이거나 실행 파일이 다르면 중단합니다. 서비스 없이 DB만 실행 중인 경우에도 자동 등록하지 않습니다.
기존 DB를 삭제하거나 초기화하지 않으며, 서비스 등록 후 기존 설정으로 시작합니다.

## 네이티브 두 번째 가상환경 / Conda (2026-09-16)

메인 GPU 앱도 Conda 환경 mediauto-gpu를 사용합니다. 두 번째 Philips 환경은 Conda로
Windows Python 3.7 (`philips-sdk-py37`), Linux Python 3.8 (`philips-sdk-py38`)을 생성합니다.
기존 Conda를 탐색·검증하여 재사용하며, 없으면 SHA-256을 검증한 Miniconda를 자동 설치합니다.
Miniconda와 환경은 설치 폴더, 다운로드·패키지 캐시는 외부 루트/cache/conda에 저장합니다.
앱에 PHILIPS_PYTHON을 설정하므로 conda activate는 필요 없습니다.
배포 폴더의 Philips SDK·OpenPhi를 해시 검증한 뒤 두 번째 환경에 설치합니다. SDK 라이선스는 최초 1회 동의 여부를 입력하며, SDK 모듈 로딩 검사가 실패하면 앱 설치도 중단합니다.
Docker 선택 시에도 호스트 로컬 개발용 Conda/Philips 환경과 GPU 앱 Conda 환경를 함께 준비합니다.

배포 폴더 구성: `install.bat`, `install.sh`, `docker/`, `native/`, `Philips_SDK/`. 전체 폴더를 유지하세요. Windows 묶음은 py37 SDK, Linux 묶음은 py38 SDK를 포함합니다. 모델 폴더는 별도 지정합니다.

Windows 묶음의 `vendor/`에는 공식 OpenSlide DLL이 들어 있는 openslide-bin wheel과 SHA-256 정보가 포함됩니다. 네이티브 설치는 이 파일을 검증해 메인 환경에 설치하고 OpenSlide import를 검사합니다. DLL을 수동 복사할 필요는 없습니다.

## Windows DB 초기화 분리 (2026-09-16)

EDB 설치 프로그램은 명시적인 unattended / extract-only 옵션으로 실행 파일만 추출합니다.
지정한 새 DB는 initdb로 생성하고 전용 서비스를 등록합니다. 이전 설치의 GUI 업그레이드 흐름에 DB 초기화를 맡기지 않습니다.
실행 파일만 있고 DB가 없는 재시도도 초기화를 진행하며, 비어 있지 않은 미완성 DB 폴더는 삭제하지 않고 중단합니다.
추출 로그는 외부 루트/config/postgresql-extract.log, 초기화 로그는 config/postgresql-initdb.log에 남습니다.

## 통합 수정 배포본 2026-09-16-r1

이 표시는 설치기 개정 번호이며 앱 버전과 별개입니다. Docker 이미지 버전은 변경하지 않습니다.

- Windows Philips 환경은 Pillow 9.5.0 바이너리를 사용합니다. 기존 9.2.0 또는 손상된 설치도 검사 후 자동 교체합니다.
- Pillow 설치는 `conda run`으로 실행해 OpenSSL DLL 검색 환경을 적용합니다. SSL, NumPy, `PIL.Image` 로딩과 실제 이미지 생성을 검사합니다.
- DB 시작 전 포트 점유 프로세스의 실행 파일과 데이터 경로를 확인합니다. 다른 DB이면 PID와 경로를 표시하고 중단하며 자동 종료하지 않습니다.
- `native/diagnose_philips.py`를 포함합니다. 이 도구는 반드시 Philips Conda 환경에서 실행하세요.

### 기존 설치를 이어서 진행하는 방법

1. 이 ZIP의 `MeDIAuto-GPU-installer` **내용을 기존 설치 폴더에 덮어씁니다**. 같은 이름의 하위 폴더를 한 겹 더 만들지 마세요.
2. 기존 `native/.install-location.json`, `native/envs`, `native/programs`, 외부 데이터 폴더와 모델 폴더는 삭제하지 않습니다. ZIP에는 이 런타임 데이터가 포함되지 않습니다.
3. 기존 위치의 `install.bat` 실행 → 사용하던 방식(현재 네이티브는 2번) 선택. 기존 설정을 재사용하고 검사를 다시 수행합니다.
4. `Philips bridge smoke test passed`와 최종 `Ready` 출력까지 확인합니다.

새 PC에는 전체 ZIP을 고정된 경로에 풀고 모델 폴더를 준비한 뒤 `install.bat`을 실행하세요.
GitHub 소스와 의존성은 인터넷에서 내려받으므로 이 ZIP은 오프라인 설치본이 아닙니다.
Windows 실제 전체 설치 성공은 아직 확인되지 않았습니다. Pillow 교체 후 SSL/이미지 생성 성공은 사용자 PC에서 확인됐으며, 나머지 변경은 자동 회귀 검사 및 패키지 무결성 검사로 검증합니다.

## 최종 정리 2026-09-17-r2

- 새 DB 최초 관리자: `admin` / `admin1234!`. 일반 비밀번호 정책을 그대로 적용합니다.
- 기존 DB의 계정 비밀번호는 변경하지 않습니다. 예전 admin 비밀번호 계정은 이 배포본을 덮어쓰는 것만으로 갱신되지 않습니다.
- Windows 실행기는 파일 핸들과 Python stdout/stderr를 함께 설정하고 자식 프로세스 출력도 로그로 연결합니다. 서버 시작 표시와 예외가 logs/app.log에 기록됩니다.
- Windows 사용자 PC에서 수정 실행기 적용 후 로그인 화면 접속이 확인됐습니다. 새 PC 전체 설치 및 로그인/슬라이드/GPU 추론은 별도 확인이 필요합니다.

### 처음부터 재검증: 기존 설치는 보존하고 새 경로 사용

현재 PC의 기존 작업을 관리자 CMD에서 먼저 비활성화하고 중지합니다.

```bat
schtasks /Change /TN "mediauto-native-317aee0702-app" /DISABLE
schtasks /End /TN "mediauto-native-317aee0702-app"
```

작업이 이미 중지되어 있으면 End가 실행 중이 아니라고 표시할 수 있습니다.
기존 DB 서비스와 데이터는 삭제하지 않습니다. 다음처럼 경로와 포트를 분리합니다.

| 입력 | 새 검증 설치 예시 |
|---|---|
| 압축 해제 위치 | C:\mediautoAI-clean\MeDIAuto-GPU-installer |
| 설치 방식 | 2 (Native GPU) |
| 외부 저장 루트 | C:\mediautoAI-clean\MeDIAutoData |
| 모델 폴더 | 기존 C:\mediautoAI\model (실제 모델 11개 폴더) |
| 슬라이드 폴더 | 엔터: 새 외부 루트/slides |
| 웹 포트 | 18094 |
| DB 포트 | 55433 |
| 웹 bind | 0.0.0.0 |

새 ZIP에는 설정 포인터나 기존 환경이 없습니다. 예전 native 폴더 전체를 새 경로로 복사하지 마세요.
새 경로의 install.bat을 실행합니다. 이 과정은 DB, 앱 가상환경, Philips 환경을 새로 만들지만 기존 OS Python/Conda가 정상이라면 재사용할 수 있습니다.
Ready 출력 후 http://localhost:18094 에서 admin / admin1234!로 로그인하고 슬라이드 업로드·열기·GPU 분석을 확인하세요.
기존 설정에는 예전 계정 비밀번호가 유지됩니다. 신규 DB에만 새 초기 비밀번호가 적용됩니다.
새 설치가 확인되기 전에는 예전 database, secrets, models 폴더를 삭제하지 마세요.

## 포트 충돌 입력 개선 2026-09-17-r3

새 설치에서 웹/DB 포트가 사용 중이면 사용 가능한 다음 번호를 제안하고 다시 입력받습니다.
Windows에서는 중단 후 재실행 시에도 DB 시작 전에 점유 프로세스를 확인합니다. 다른 DB가 사용 중이면
`New PostgreSQL port [55433]:`처럼 대체 포트를 물어보고, 선택 값을 settings.json과 identity.json에 저장합니다.
PostgreSQL 설정과 이후 앱 연결 설정은 새 포트를 사용합니다. 기존 DB 프로세스와 데이터는 건드리지 않습니다.
설치기 코드만 기존 폴더에 덮어쓴 뒤 같은 방식으로 재실행하면 됩니다. 설정 파일을 수동으로 고칠 필요는 없습니다.

## Git 작업 폴더 + 수동 실행 (2026-09-17-r4, 네이티브 방식)

네이티브 설치는 환경·DB·모델 검사를 마친 뒤 종료합니다. 앱을 실행하거나 로그인 자동 실행 작업을 등록하지 않습니다.
같은 설치 ID로 남아 있는 앱 작업/서비스는 비활성화하고 중지합니다. 다른 설치 ID의 앱에는 영향을 주지 않습니다.
PostgreSQL은 DB 서비스로 유지합니다. Docker 방식도 설치 후 자동 실행하지 않습니다.

- Git이 없으면 설치합니다. GitHub 브랜치/태그를 최초 clone하고 `.git`을 보존합니다.
- VS Code에서 `native/application` 폴더를 엽니다. 네이티브 전용 묶음은 `application` 폴더입니다.
- 기존 Git 작업 폴더에는 자동 pull/checkout/reset/clean을 하지 않습니다. 선택한 브랜치, 수정 파일과 미추적 파일을 보존합니다.
- 설치 시 PAT는 명령 인자·원격 URL·설정 파일에 저장하지 않습니다. 이후 수동 Git 작업의 인증은 VS Code/Git에서 별도로 설정합니다.
- 태그는 detached HEAD이므로 개발에는 브랜치를 선택하세요.

Windows: 설치 폴더에서 `native\start.bat` 실행.
Linux: 일반 사용자 터미널에서 `bash native/start.sh` 실행.
종료: 실행 중인 터미널에서 `Ctrl+C`. 터미널을 닫으면 실행을 유지하는 방식이 아닙니다.
로그인 URL은 설정한 웹 포트이며, 새 DB 최초 계정은 admin / admin1234!입니다.

업데이트: 서버 종료 → native/application을 VS Code로 열기 → 로컬 변경을 커밋하거나 필요 시 직접 stash → git fetch origin → 원하는 브랜치로 switch/merge → 필요하면 install 재실행으로 의존성·마이그레이션 갱신 → start로 직접 실행.
설치기를 재실행해도 Git 작업 폴더의 브랜치와 로컬 수정은 유지합니다. 마이그레이션이 있는 업데이트 전에는 DB를 백업하세요.

구형 ZIP 소스 설치의 application 폴더는 자동 변환하거나 삭제하지 않습니다.
처음부터 검증하려면 새 설치 폴더와 새 외부 데이터 루트를 사용하고 모델만 기존 폴더를 지정하세요.
예: C:\mediautoAI-dev\MeDIAuto-GPU-installer, 외부 루트 C:\mediautoAI-dev\data, 웹 18094, DB 55433.
기존 앱 자동 실행은 이전 설치 ID에 대해 별도로 중지해야 합니다.

## 두 방식 공통 Git + 수동 실행 (2026-09-17-r5, 이후 r6에서 로컬 개발 환경 추가)

1번 Docker와 2번 네이티브 모두 Git clone, 브랜치/로컬 수정 보존, 설치 후 앱 자동 실행 없음, 수동 업데이트 원칙을 적용합니다.
1번은 환경이 준비된 GPU 이미지를 기반으로 Git 작업 폴더의 코드를 빌드합니다. Docker Hub에 코드를 업로드하지 않습니다.
설치 중에는 build까지만 수행하며 컨테이너를 시작하지 않습니다. restart 정책은 no입니다.
이 설치의 기존 컨테이너가 있으면 restart=no로 변경하고 중지합니다. PostgreSQL과 Docker 엔진 자체의 서비스는 유지합니다.

| 항목 | 1번 Docker | 2번 네이티브 |
|---|---|---|
| VS Code 소스 폴더 | docker/application | native/application |
| Windows 시작 | docker\start.bat | native\start.bat |
| Linux 시작 | bash docker/start.sh | bash native/start.sh |
| 종료 | Ctrl+C 또는 docker/stop.bat (Linux: bash docker/stop.sh) | Ctrl+C |

Docker start는 현재 소스를 다시 build하고 포그라운드로 실행합니다. 코드를 수정하거나 브랜치를 병합한 후 종료·재실행하면 반영됩니다.
Docker 빌드 입력에서 .git, 모델, .env 및 운영 데이터를 제외합니다. 데이터는 기존 외부 마운트를 사용합니다.
GitHub PAT는 clone할 때만 프로세스 환경으로 전달하며 Git 설정/원격 URL/빌드 입력에 저장하지 않습니다.
네이티브의 의존성 변경은 install 재실행, Docker 의존성 변경은 start의 build로 반영합니다.
두 방식 모두 DB 마이그레이션 전에는 백업하세요. 기존 계정 비밀번호는 자동 변경하지 않습니다.

## 1번도 로컬 개발 환경 포함 (2026-09-17-r6)

1번 Docker 선택 시 Docker 이미지뿐 아니라 PC의 로컬 GPU 앱 환경(Conda)과 Philips SDK 환경(Conda)을 모두 준비합니다.
Conda가 없으면 검증된 Miniconda를 설치합니다. Windows Philips 환경은 Python 3.7, Linux는 Python 3.8입니다.
SDK, OpenSlide/libvips, PyTorch CUDA, DB 마이그레이션 및 모델 검사를 로컬에서도 수행합니다. CPU로 자동 전환하지 않습니다.

통합 설치 폴더 기준:
- 공통 소스: `docker/application` — Docker와 로컬에서 같은 브랜치와 수정 파일을 사용합니다.
- 로컬 GPU 앱: `docker/envs/mediauto-gpu`
- Philips SDK: `docker/envs/philips-sdk-py37` (Windows) 또는 `philips-sdk-py38` (Linux)
- VS Code: `docker/MeDIAuto-local.code-workspace` 열기. Python 확장과 디버거 확장이 있으면 제공된 실행 구성을 선택할 수 있습니다.
- 로컬 실행: Windows `docker\start-local.bat`, Linux `bash docker/start-local.sh`
- Docker 실행: Windows `docker\start.bat`, Linux `bash docker/start.sh`
- 종료: Ctrl+C (Docker는 stop.bat/stop.sh도 제공)

두 실행 방식은 같은 외부 데이터 루트·모델·DB·웹 포트를 사용합니다. 한 번에 한 방식만 실행하세요.
설치 후 서버 자동 시작이나 로그인 자동 실행은 없습니다. PostgreSQL과 Docker 엔진은 서비스로 유지됩니다.
설치 재실행 시 기존 Git 수정과 VS Code 작업 공간 편집을 보존합니다. 소스 변경 후 Docker는 다시 start하면 빌드에 반영됩니다.
로컬 의존성 변경은 install을 재실행하고, DB 마이그레이션 변경 전에는 DB를 백업하세요.
기존 r5의 Git 설치에는 새 ZIP 내용을 동일 위치에 덮어쓰고 install.bat → 1번으로 재실행하면 됩니다. 기존 envs/programs/설정 포인터/외부 데이터를 삭제하지 마세요.

## Conda 두 환경으로 통일 (2026-09-17-r7)

1번과 2번 모두 Conda가 없으면 Miniconda를 자동 설치하고, GPU 앱도 venv 대신 Conda로 생성합니다.
- 메인 앱: envs/mediauto-gpu (Python 3.12, CUDA PyTorch)
- Philips: envs/philips-sdk-py37 (Windows), envs/philips-sdk-py38 (Linux)
패키지 설치와 수동 실행은 conda run을 사용합니다. 기존 venv는 삭제하지 않지만 새 실행 경로에서는 사용하지 않습니다.
기존 정상 Conda가 있으면 재사용합니다. 설치 후 자동 서버 실행은 하지 않습니다.

## 기존 프로젝트와 동일한 이름 기반 Conda 환경 (2026-09-17-r9)

이 개정부터 설치 폴더의 envs 경로에 생성하지 않고 Conda의 이름 기반 환경을 사용합니다.
- 메인 앱: `conda activate medicus-saas`
- Windows Philips: `conda activate philips-sdk-py37`
- Linux Philips: `conda activate philips-sdk-py38`

환경 생성/실행은 `conda create --name` / `conda run --name` 방식입니다.
기존 이름의 환경이 있으면 검증하고 재사용합니다. 이전 배포본이 만든 경로 기반 환경은 삭제하지 않습니다.
같은 Conda를 쓰는 설치끼리는 이름 환경을 공유하므로 패키지 변경이 함께 반영됩니다.
Windows CMD / Linux bash 초기화를 포함합니다. 설치 후 터미널을 완전히 닫고 새로 여세요.
두 activate 명령은 각각의 환경으로 전환하는 명령이며 동시에 두 환경을 활성화하는 뜻은 아닙니다.
서버 시작은 기존 start/start-local 스크립트를 사용하면 외부 DB·모델·로그 경로 설정까지 적용됩니다.


## Windows / Linux 공통 경로

경로 설정과 브랜치 병합 시 유지할 PC별 설정은 `PATH_CONFIGURATION.ko.md`를 참조하세요. 패치와 비밀키 경로도 환경변수로 전달하며, 기존 프로젝트 기본값은 유지합니다.

### 설치 패키지 2026-09-18-r11

Windows/Linux 및 두 설치 메뉴에 데이터 경로 Git 추적 검사, 소스 내부 데이터 경로 차단, 로컬 Git 제외 규칙을 추가했습니다. 기존 데이터와 로컬 코드 수정은 삭제하지 않습니다. 상세 내용은 `PATH_CONFIGURATION.ko.md`를 확인하세요.

### 설치 패키지 2026-09-22-r12

PostgreSQL/Miniconda 다운로드 중 Python의 인증서 검증이 실패하면 Windows PowerShell의 HTTPS 다운로드로 재시도합니다. 인증서 검증을 끄지 않으며 고정 SHA-256 검사도 유지합니다. Windows에서도 실패하면 시스템 시각, 루트 인증서 및 사내 HTTPS 프록시 설정을 확인해야 합니다. PostgreSQL 다운로드는 임시 파일을 검증한 뒤 설치파일로 교체합니다. Linux 다운로드는 기존 인증서 검증 방식을 유지합니다.
