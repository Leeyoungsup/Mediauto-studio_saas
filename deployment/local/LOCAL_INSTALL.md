# MeDIAuto Studio — 새 PC 설치 (모델만 이전)

이 배포본에는 최신 프로그램과 model_manifest.json에 등록된 모델만 들어 있습니다.
기존 DB, 계정, 로그인 세션, 감사 로그, WSI 원본, annotation, AI 분석 결과,
기존 .secrets.json과 DB 접속 설정은 포함하지 않습니다.
각 PC에서 새 DB와 새 보안키를 생성합니다. 최초 관리자 비밀번호도 PC마다 다릅니다.

## 준비

- Linux x86-64: Docker Engine + Docker Compose 플러그인.
- Windows x86-64: Docker Desktop을 설치하고 WSL2 기반 Linux 컨테이너로 실행.
- 최초 설치 시 인터넷 연결 필수. Python 패키지, 컨테이너 이미지는 번들에 포함되지 않습니다.
- 압축을 완전히 해제한 후 실행하세요. CPU 모드도 지원하지만 큰 WSI AI 분석은 느릴 수 있습니다.
- 압축 파일/모델/컨테이너 이미지와 앞으로 업로드할 WSI 및 결과를 위한 공간이 필요합니다.
- Philips iSyntax SDK와 라이선스는 포함하지 않습니다. 별도 구성 전에는 iSyntax 지원을 보장하지 않습니다.

## Linux

배포 폴더에서:

```bash
bash setup.sh              # CPU 모드 신규 설치 및 시작
# NVIDIA GPU 구성이 준비됐다면 대신:
bash setup.sh gpu
```

재시작: `bash start-local.sh`
정지: `bash stop-local.sh`
로그: `bash deployment/local/manage.sh logs`
상태: `bash deployment/local/manage.sh status`

## Windows

Docker Desktop을 실행하고 배포 폴더에서 `setup.bat`를 실행합니다.
CPU 모드로 설치합니다. GPU 설치는 CMD에서 `setup.bat gpu`를 실행합니다.
PowerShell로 직접 실행하려면:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deployment\local\manage.ps1 -Action setup -Device cpu
```

재시작: `start-local.bat`
정지: `stop-local.bat`
로그: `powershell -NoProfile -ExecutionPolicy Bypass -File .\deployment\local\manage.ps1 -Action logs`

이 구성은 Windows 네이티브 Python 설치가 아닌 Docker의 Linux 앱 컨테이너입니다.
Windows에 Conda, OpenSlide DLL, libvips를 따로 설치할 필요가 없습니다.

## 접속과 관리자

설치 성공 후 `http://localhost:8092`로 접속합니다.
ID는 `admin`, 비밀번호는 설치하면서 생성된 `ADMIN_LOGIN.txt`에서 확인합니다.
로그인 후 비밀번호를 변경하세요. `.deploy.env`와 `ADMIN_LOGIN.txt`는 외부에 공유하지 마세요.
설치를 다시 실행하면 기존 DB/관리자/키를 유지합니다.
기본 타일 캐시 한도는 100 GiB이며 `.deploy.env`의 `TILE_CACHE_QUOTA_BYTES`로 변경할 수 있습니다.

## NVIDIA GPU

Linux에서는 NVIDIA 드라이버와 NVIDIA Container Toolkit의 Docker 구성이 필요합니다.
Windows에서는 NVIDIA 드라이버와 Docker Desktop WSL2 GPU 지원이 필요합니다.
GPU 모드는 PyTorch 2.11.0 / torchvision 0.26.0의 CUDA 12.8 wheel을 설치합니다.
GPU와 드라이버가 이 CUDA 빌드를 지원해야 합니다. CPU 모드는 별도 CPU wheel을 사용합니다.
GPU 미지원 환경에서는 `setup`의 GPU 실행이 실패하며 CPU로 몰래 전환하지 않습니다.

최초 설치 후 장치 모드를 변경하려면 `.deploy.env`의 `MEDIAUTO_DEVICE`와
`TORCH_INDEX_URL`을 함께 변경(cpu: .../whl/cpu, gpu: .../whl/cu128)한 뒤
해당 모드로 setup을 다시 실행해 앱 이미지를 다시 빌드합니다.

## 다른 PC의 브라우저에서도 접속

기본값은 해당 PC 내부 접속만 허용합니다.
`.deploy.env`에서 `MEDIAUTO_BIND=0.0.0.0`으로 변경하고 start-local을 다시 실행한 뒤
방화벽에서 신뢰할 내부망에 TCP 8092를 허용하면 `http://서버PC_IP:8092`로 접속할 수 있습니다.
외부망 운영은 TLS 프록시 구성을 별도로 적용하세요. PostgreSQL 포트는 외부에 공개하지 않습니다.
포트 충돌 시 `MEDIAUTO_PORT`를 변경하고 같은 포트로 접속합니다.

## 새 데이터 보존

DB, 새 업로드·annotation·AI 결과, 보안키는 이 설치의 Docker named volume에 저장됩니다.
`stop-local`은 컨테이너만 정지하고 데이터를 유지합니다.
Docker 볼륨 삭제나 `docker compose down -v`는 새로 쌓은 데이터를 삭제하므로 사용하지 마세요.
`.deploy.env`의 `COMPOSE_PROJECT_NAME`을 바꾸면 다른 설치의 빈 볼륨을 사용하게 됩니다.
각 PC는 독립 서버입니다. 한 PC에서 생긴 계정·주석은 다른 PC에 자동 동기화되지 않습니다.

## 확인

- `/api/version`에서 배포 버전 확인.
- 최초 로그인, 프로젝트 생성, 테스트 슬라이드 업로드/열기.
- 사용하는 AI 모델을 실행하고 결과·annotation 저장 확인.
- Admin에서 새 활동 로그 확인.
- stop-local 후 start-local을 실행해 데이터 유지 확인.

`bundle-manifest.json`은 코드와 모델의 파일별 SHA-256을 담고 있습니다.
setup은 먼저 이 값을 검증하며 파일이 손상/변경되었으면 설치를 중단합니다.
검증 후 생성되는 로컬 설정과 비밀번호 파일은 배포 파일 해시에 포함되지 않습니다.
`SHA256SUMS.txt`는 배포 ZIP/TAR.GZ 자체의 해시입니다(압축 파일과 함께 배포).

## 공식 설치 자료

배포 검증: Linux CPU Docker 이미지 빌드, 빈 DB 초기화, 관리자 로그인,
프로젝트 생성과 앱 재시작 후 보존을 확인했습니다.
Windows 설치 스크립트는 PowerShell 문법 검사를 통과했습니다.
실제 Windows PC 설치, GPU 추론, WSI 업로드·분석은 대상 PC에서 추가 확인이 필요합니다.

- Docker Engine: https://docs.docker.com/engine/install/
- Docker Desktop Windows: https://docs.docker.com/desktop/setup/install/windows-install/
- Docker Windows GPU: https://docs.docker.com/desktop/features/gpu/
- Docker Compose GPU: https://docs.docker.com/compose/how-tos/gpu-support/
- PyTorch wheel 조합: https://pytorch.org/get-started/previous-versions/
