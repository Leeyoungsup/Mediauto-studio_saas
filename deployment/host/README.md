# MeDIAuto 3.3.2 — 호스트 DB / 외부 저장소 설치

앱만 Docker Hub에서 받습니다. PostgreSQL은 PC의 서비스로 설치합니다.
기존 Docker DB 설치와는 별개의 새 설치이며, 기존 데이터를 자동으로 옮기거나 삭제하지 않습니다.
Docker를 정지·재생성해도 아래 호스트 폴더는 남습니다. 디스크 고장에 대비한 별도 백업은 필요합니다.

## Windows

Windows x86-64, Docker Desktop이 지원하는 Windows 10/11과 하드웨어 가상화가 필요합니다.
압축을 완전히 풀고 `install.bat`를 실행합니다. 관리자 권한(UAC)을 허용하세요.

1. WSL2 기능 확인/활성화. 재부팅 안내가 나오면 Windows를 재부팅하고 같은 `install.bat`를 다시 실행합니다.
2. Docker Desktop과 설치 도구용 Python을 자동 설치합니다. Docker Desktop의 최초 시작 화면이 나오면 완료합니다.
3. 저장 경로와 포트를 입력합니다. 엔터를 누르면 표시된 기본값을 사용합니다.
4. PostgreSQL 18을 별도 Windows 서비스로 설치하고 앱용 DB·계정을 생성합니다.
5. 모델을 선택한 경로에 복사/검증하고 Docker Hub 이미지를 받아 앱을 시작합니다.

Microsoft App Installer(winget)가 없으면 스토어를 열어 설치를 안내합니다.
관리자 승인, 필요한 재부팅, 최초 Docker 화면까지 무인으로 건너뛰는 설치는 아닙니다.
최초 설치는 인터넷이 필요합니다. Docker Desktop 이용 조건은 공식 설치 안내를 확인하세요.

## Linux

Ubuntu/Debian x86-64 + systemd를 지원합니다. 배포 폴더에서 `bash install.sh`를 실행하세요.
sudo 비밀번호가 필요할 수 있습니다. Docker Engine/Compose, Python, PostgreSQL 패키지를 설치합니다.
별도 PostgreSQL 클러스터와 systemd 서비스를 만듭니다. 기존 DB 서비스를 지우거나 재설정하지 않습니다.
다른 배포판에서는 이 자동 설치 스크립트를 실행하지 않습니다.

## 경로와 포트

설치 중 `install.bat` / `install.sh`에서 다음 폴더를 각각 지정합니다.
Windows 예: `D:\MeDIAuto\slides`, Linux 예: `/mnt/storage/mediauto/slides`.
서로 다른 로컬 폴더를 사용하세요. DB 폴더는 네트워크 드라이브에 두지 마세요.

| 입력 항목 | 저장 내용 |
|---|---|
| models | AI 모델 11개. 앱에서는 읽기 전용 |
| slides | 업로드한 슬라이드 원본 |
| patches | 추출된 패치 JPEG, 세포 주석 내보내기 파일 |
| results | AI 분석 결과 |
| annotations | 파일 기반 annotation |
| tiles | 뷰어 타일 캐시 (기본 100 GiB 한도) |
| dicom | DICOM 압축 해제 캐시 |
| secrets | 앱 암호화·서명 키. 반드시 DB와 함께 보존 |
| temp | 임시 작업/내보내기 파일. 영구 결과 저장소는 아님 |
| database | 호스트 PostgreSQL 데이터 파일 |

일부 주석·계정·로그는 PostgreSQL에 저장됩니다. 패치 추론 중 메모리에서만 사용하는 이미지는 파일로 생성하지 않습니다.
기본 웹 포트는 `18093`, 전용 DB 포트는 `55432`입니다. 사용 중이면 초기 설정을 바꾸고 재시도하세요.
웹 bind 기본 `0.0.0.0`은 같은 LAN에서 접속 가능, `127.0.0.1`은 해당 PC만 접속 가능합니다.
다른 PC에서는 `http://서버IP:포트`를 사용합니다. localhost는 각 PC 자신입니다.
Windows 방화벽은 LAN 범위에 웹/DB 규칙을 추가합니다. Linux DB는 해당 Docker 네트워크에서만 인증 연결을 허용합니다.

## 계정 / 시작 / 중지

로그인 정보는 `.runtime/ADMIN_LOGIN.txt`, 설치 설정은 `.runtime/settings.json`에 있습니다.
이 폴더에는 DB 비밀번호도 있으므로 공유하지 마세요. Windows는 관리자/설치 사용자만, Linux는 root만 읽도록 보호합니다.

Docker Desktop / Docker Engine이 실행된 상태에서 배포 폴더 기준:

```text
docker compose -f .runtime/compose.json up -d --wait --wait-timeout 900
docker compose -f .runtime/compose.json stop
docker compose -f .runtime/compose.json logs --tail 100 -f app
```

Linux에서 설정 읽기 권한 때문에 필요한 경우 명령 앞에 `sudo`를 붙이세요.
PostgreSQL 서비스는 PC 부팅 시 자동 시작합니다. Windows Docker Desktop도 로그인 시 시작하도록 설정하세요.
앱 컨테이너를 삭제해도 다시 위 up 명령으로 생성할 수 있습니다. 호스트 저장 폴더는 삭제되지 않습니다.
DB 마이그레이션, 모델 검사, 관리자 초기화가 성공한 뒤에만 설치 완료를 표시합니다.

## 재설치 / 저장 위치 변경

같은 설치 폴더에서 다시 실행하면 저장된 경로와 계정 정보를 사용합니다. 관리자 비밀번호를 초기화하지 않습니다.
최초 실행 때 입력한 폴더는 `.runtime/settings.json`에서 확인할 수 있습니다.
아직 초기화하지 못한 경우에만 해당 파일의 포트/경로를 수정하고 재실행하세요.
이미 DB를 만든 설치의 저장 경로 변경은 자동 데이터 이동이 아닙니다. 설치기는 잘못된 경로로 빈 DB가 생기는 것을 막기 위해 변경을 거부합니다.
운영 후 경로를 옮길 때는 앱·DB를 정지하고 파일을 복사하며, DB는 pg_dump/pg_restore로 이전하는 별도 작업이 필요합니다.
`.runtime`와 PostgreSQL 바이너리가 있는 배포 폴더도 설치 후 임의로 이동하지 마세요.
기존 Docker 볼륨의 데이터를 옮기는 기능은 포함하지 않습니다.

## 범위 / 검증

현재 공개 앱 이미지는 CPU용 3.3.2이며 digest를 고정했습니다. 이 설치기는 GPU 이미지 설치를 제공하지 않습니다.
Philips iSyntax SDK/라이선스는 포함하지 않습니다.
Windows 자동 설치는 PowerShell 문법 및 설정 생성 검사까지 가능하며, 실제 Windows PC의 WSL/UAC/서비스 설치는 대상 PC에서 검증해야 합니다.
Linux 호스트에서 PostgreSQL 14를 직접 실행한 별도 테스트로 Docker 앱 로그인, 외부 폴더 저장,
컨테이너 재생성 후 프로젝트·보안 키 보존을 확인했습니다. OS 패키지 설치와 systemd 등록 전체는 운영 PC에서 실행하지 않았습니다.

## 공식 자료

- Docker Windows: https://docs.docker.com/desktop/setup/install/windows-install/
- Docker Ubuntu: https://docs.docker.com/engine/install/ubuntu/
- PostgreSQL Windows: https://www.postgresql.org/download/windows/
- EDB 설치 옵션: https://www.enterprisedb.com/docs/supported-open-source/postgresql/installing/command_line_parameters/
- Windows PostgreSQL 다운로드 해시 출처: https://github.com/microsoft/winget-pkgs/blob/master/manifests/p/PostgreSQL/PostgreSQL/18/18.6-3/PostgreSQL.PostgreSQL.18.installer.yaml
