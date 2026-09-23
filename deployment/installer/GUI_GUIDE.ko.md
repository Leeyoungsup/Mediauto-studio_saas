# GUI 설치 관리자

화면 캡처와 설치·실행·개발 절차를 담은 10쪽 PDF: `MeDIAuto-GUI-Installation-Guide-KO-r15.pdf` (GUI 배포 폴더). 문서 원본은 `installation-guide.ko.html`과 `guide-assets/`입니다.

Windows: `MeDIAuto-Setup-windows-x64.exe`를 실행하고 설치기 폴더를 선택합니다. 관리자 권한으로 파일을 풀고 Python 3.12가 없으면 설치한 뒤 입력 창을 엽니다. 이미 압축을 푼 폴더에서는 `setup-gui.bat`로 다시 열 수 있습니다.

Linux 데스크톱(Ubuntu/Debian x64): `.run` 파일에 실행 권한을 주고 실행합니다. `$HOME/MeDIAuto-GPU-installer`에 설치기를 풀고 입력 창을 엽니다. `python3-tk`가 없으면 시스템 인증 창으로 설치를 요청합니다. 설치 시작 시에도 시스템 관리자 인증 창을 사용합니다. 그래픽 데스크톱과 polkit 인증 에이전트가 필요합니다. SSH 전용 서버는 기존 `install.sh`를 사용하세요.

1. Docker 또는 Native를 선택합니다. 둘 다 GitHub 소스와 로컬 Conda 개발 환경을 준비합니다.
2. 외부 데이터·모델 폴더를 선택합니다. 슬라이드 폴더는 비우면 외부 데이터 폴더/slides입니다.
3. 웹/DB 포트, 바인딩 IP, 저장소와 브랜치를 확인합니다.
4. 비공개 저장소는 GitHub 사용자명과 PAT를 입력합니다. PAT는 입력 창에서 가리고 파일이나 명령행에 저장하지 않습니다.
5. 설치 시작을 누릅니다. 포트 충돌은 별도 입력 창에서 새 포트를 선택합니다. Philips SDK 라이선스는 내용을 읽고 동의해야 합니다.

기존 설치가 있으면 저장된 설정을 표시하고 경로·포트 변경 입력은 잠급니다. 설치 재시도로 기존 데이터 경로를 임의로 바꾸지 않습니다. 기존 Git 작업 트리는 pull/reset하지 않습니다.

진행 로그와 성공/실패를 창에서 확인할 수 있습니다. 실패하면 원인을 해결한 뒤 같은 설치기로 재시도합니다. 패키지 설치를 중간에 강제 종료하지 않도록 진행 중에는 창 닫기를 제한합니다. 설치 완료 후 서버는 자동 실행하지 않습니다. 실행 명령은 완료 창과 새 PDF 가이드의 Windows·Linux 실행 페이지를 참조하세요.

Windows 실행파일은 코드 서명이 없는 배포물입니다. Windows 실기에서 UAC·네트워크·Docker Desktop·GPU 설치 전체 흐름을 별도로 검증해야 합니다. 모델 파일은 포함하지 않습니다.

## r15 GPU 드라이버 자동 설치

호환 드라이버가 없거나 오래된 경우 설치 초기에 자동 설치를 시도합니다. 이미 충분한 버전이면 유지합니다.

- Windows: Windows Update가 이 PC에 제공하는 NVIDIA Display 드라이버 중 기준 버전(570.65) 이상만 선택합니다. Windows Update 정책·네트워크·노트북 지원 여부에 따라 호환 드라이버가 제공되지 않을 수 있습니다. 이 경우 NVIDIA/제조사 드라이버 설치 안내와 함께 중단합니다.
- Ubuntu/Debian: OS 저장소의 추천/표준 NVIDIA 패키지를 설치합니다. CUDA 12.8 기준 버전(570.26) 이상 패키지가 없는 저장소에서는 중단합니다. 저장소를 임의로 교체하거나 비공식 드라이버를 설치하지 않습니다.
- 드라이버 설치 후 재부팅이 필요하면 직접 재부팅하고 같은 설치기를 실행하세요. 자동 재부팅하지 않습니다. Linux Secure Boot의 MOK 등록은 부팅 화면에서 직접 해야 할 수 있습니다.
- Linux Docker 메뉴는 NVIDIA Container Toolkit을 자동 설치하고 Docker runtime을 구성합니다. Windows Docker Desktop은 Windows NVIDIA 드라이버와 WSL2 GPU 지원을 사용합니다. Native 메뉴에는 Container Toolkit이 필요하지 않습니다.

드라이버 설치 분기는 모의 테스트와 구문 검증을 했습니다. 실제 Windows Update/리눅스 드라이버 변경 및 재부팅까지의 실기 검증은 수행하지 않았습니다.

## r16 Windows 한글 로그 수정

Python 진행 메시지는 UTF-8로 통일하고, Windows 도구의 출력은 UTF-8 또는 PC의 OEM/ANSI 코드 페이지로 읽습니다. 기존 r15 가이드의 설치·실행 절차는 동일합니다.
