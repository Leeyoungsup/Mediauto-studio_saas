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

Docker 방식은 공개 Docker Hub 이미지를 받아 실행하므로 GitHub 인증이 필요하지 않습니다.
초기 관리자 ID와 비밀번호는 모두 `admin`입니다. 최초 로그인 정보는 `<외부 루트>/config/ADMIN_LOGIN.txt`에서 확인합니다.

네이티브 방식은 GitHub 저장소(기본 Leeyoungsup/Mediauto-studio_saas), 브랜치(기본 main),
GitHub 아이디와 PAT를 입력합니다. 앱 초기 관리자 ID와 비밀번호는 모두 `admin`입니다.
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
네이티브 Windows 앱은 설치 사용자 로그인 시 작업 스케줄러에서 시작하며, Linux 앱은 systemd 서비스입니다.
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

초기 `admin/admin`은 빈 DB의 최초 계정 생성에만 적용됩니다. 기존 설정과 이미 생성된 계정의 비밀번호는 설치기를 재실행해도 변경하지 않습니다.

## Windows PostgreSQL 서비스 누락 복구 (2026-09-16)

DB 초기화는 됐지만 전용 서비스가 없는 경우, 같은 설치기의 재실행으로 서비스 등록을 복구합니다.
설치 소유 정보·DB 경로·PostgreSQL 실행 파일이 일치하는 기존 서비스는 이름이 달라도 재사용합니다.
같은 DB를 가리키는 서비스가 여러 개이거나 실행 파일이 다르면 중단합니다. 서비스 없이 DB만 실행 중인 경우에도 자동 등록하지 않습니다.
기존 DB를 삭제하거나 초기화하지 않으며, 서비스 등록 후 기존 설정으로 시작합니다.

## 네이티브 두 번째 가상환경 / Conda (2026-09-16)

메인 GPU 앱은 기존 Python venv를 유지합니다. 두 번째 Philips 환경은 Conda로
Windows Python 3.7 (`philips-sdk-py37`), Linux Python 3.8 (`philips-sdk-py38`)을 생성합니다.
기존 Conda를 탐색·검증하여 재사용하며, 없으면 SHA-256을 검증한 Miniforge를 자동 설치합니다.
Miniforge와 환경은 설치 폴더, 다운로드·패키지 캐시는 외부 루트/cache/conda에 저장합니다.
앱에 PHILIPS_PYTHON을 설정하므로 conda activate는 필요 없습니다.
배포 폴더의 Philips SDK·OpenPhi를 해시 검증한 뒤 두 번째 환경에 설치합니다. SDK 라이선스는 최초 1회 동의 여부를 입력하며, SDK 모듈 로딩 검사가 실패하면 앱 설치도 중단합니다.
Docker 모드는 호스트 Conda 환경을 사용하지 않습니다. 이 변경은 네이티브 설치에 적용됩니다.

배포 폴더 구성: `install.bat`, `install.sh`, `docker/`, `native/`, `Philips_SDK/`. 전체 폴더를 유지하세요. Windows 묶음은 py37 SDK, Linux 묶음은 py38 SDK를 포함합니다. 모델 폴더는 별도 지정합니다.
