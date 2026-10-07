"""Build four illustrated A4 PDF guides from the actual installer and frontend.
Requires playwright + a Chromium executable (CHROME_PATH override).
No application server, production account or installation is started.
"""
import argparse
import html
import json
import os
from pathlib import Path
import shutil
import subprocess
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'deployment/release-guide'
RELEASE = '2026-10-07-r20'
DEFAULT_OUT = ROOT / 'artifacts/local-deployment/final' / RELEASE
E = html.escape
CSS = '''
@page {size:A4;margin:0} *{box-sizing:border-box} body{margin:0;color:#193048;font-family:"Noto Sans CJK KR",Arial,sans-serif;font-size:10pt;line-height:1.55}
.page{width:210mm;height:297mm;padding:17mm 18mm 20mm;position:relative;break-after:page;background:white}.page:last-child{break-after:auto}
.kicker{font-size:8.5pt;letter-spacing:1.3px;color:#147d83;font-weight:700}h1{font-size:33pt;line-height:1.24;margin:16mm 0 8mm;letter-spacing:-1px}h2{font-size:23pt;line-height:1.3;margin:4mm 0 6mm}h3{font-size:12pt;color:#126e78;margin:5mm 0 2mm}p{margin:2mm 0 3mm}ul,ol{padding-left:6mm;margin:2mm 0 4mm}li{margin:1.8mm 0}
.hero{background:#12354b;color:white;padding:8mm;border-radius:3mm;margin:8mm 0}.hero h3{color:#7ee0d4;margin-top:0}.box{background:#eaf5f3;border-left:3px solid #209385;padding:3.5mm 4mm;margin:4mm 0}.warning{background:#fff5e5;border-color:#c58321}.small,.caption{font-size:8.4pt;color:#536678}.caption{margin:2mm 0 4mm}table{border-collapse:collapse;width:100%;font-size:9pt;margin:4mm 0}th,td{border-bottom:1px solid #d9e3e9;padding:2.5mm 3mm;text-align:left;vertical-align:top}th{background:#edf3f7}td:first-child{width:29%}pre{font-family:"DejaVu Sans Mono",monospace;font-size:8.2pt;line-height:1.55;background:#edf2f7;padding:3.5mm;white-space:pre-wrap;overflow-wrap:anywhere;margin:3mm 0}code{font-family:"DejaVu Sans Mono",monospace;font-size:8.4pt;overflow-wrap:anywhere}a{color:#0a7684;text-decoration:none;overflow-wrap:anywhere}.shot{display:block;max-width:100%;object-fit:contain;margin:3mm auto;border:1px solid #d7e0e8}.gui{height:176mm}.license{height:103mm}.login{height:88mm}.cli{max-height:65mm}.footer{position:absolute;left:18mm;right:18mm;bottom:10mm;border-top:1px solid #d9e3e9;padding-top:2mm;display:flex;justify-content:space-between;font-size:7.7pt;color:#687e8d}.checklist li{margin:3mm 0}
'''

def p(t): return '<p>'+t+'</p>'
def box(t, warning=False): return '<div class="box'+(' warning' if warning else '')+'">'+t+'</div>'
def listing(items, ordered=False):
    tag='ol' if ordered else 'ul'
    return '<'+tag+'>'+''.join('<li>'+x+'</li>' for x in items)+'</'+tag+'>'
def table(rows, heads): return '<table><tr>'+''.join('<th>'+x+'</th>' for x in heads)+'</tr>'+''.join('<tr>'+''.join('<td>'+x+'</td>' for x in row)+'</tr>' for row in rows)+'</table>'
def code(t): return '<pre>'+E(t)+'</pre>'
def shot(name, caption, cls=''): return '<img class="shot '+cls+'" src="assets/'+name+'"><p class="caption">'+caption+'</p>'


def pages_for(platform, lang):
    ko=lang=='KO';win=platform=='Windows'
    def t(k,e): return k if ko else e
    oslabel='Windows' if win else 'Linux'
    driver='570.65' if win else '570.26'
    root='C:\\MeDIAutoData' if win else '/srv/mediauto'
    file='MeDIAuto-Setup-windows-x64.exe' if win else 'MeDIAuto-Setup-linux-x64.run'
    pages=[]
    def add(title, body): pages.append((title,body))
    add(t('설치 · 실행 가이드','Installation & operation'),
        '<h1>MeDIAuto AI<br>'+oslabel+'</h1>'+p(t('GUI 설치 전용' if win else 'GUI · 터미널 설치','GUI installer' if win else 'GUI & terminal installers'))+
        '<div class="hero"><h3>'+t('설치 전 필수 확인','Before you begin')+'</h3>'+p(t('인터넷 연결 · 관리자 권한 · NVIDIA GPU','Internet access · administrator privileges · NVIDIA GPU'))+p(t('NVIDIA 드라이버 ', 'NVIDIA driver ')+driver+t(' 이상 / CUDA 12.8 런타임',' or newer / CUDA 12.8 runtime'))+'</div>'+
        p(t('앱 기준 버전 3.3.2 · 설치기 개정 '+RELEASE,'Application baseline 3.3.2 · Installer revision '+RELEASE))+
        box(t('모델 가중치는 별도입니다. 설치가 끝나면 서버를 직접 시작하세요.','Model weights are supplied separately. Start the server manually after installation.'))+
        listing([t('이 문서: 준비 → 설치 → 실행·종료 → 백업·문제 해결','In this guide: prepare → install → start/stop → backup & troubleshooting'),t('Windows 배포물은 GUI EXE 한 종류입니다.' if win else '데스크톱은 GUI .run, SSH/서버는 CLI .tar.gz를 사용합니다.','Windows is distributed as one GUI EXE.' if win else 'Use GUI .run on a desktop, or CLI .tar.gz over SSH/on a server.'),t('GUI/CLI는 입력 방식입니다. Docker/Native는 그 안에서 선택하는 실행 환경입니다.','GUI/CLI selects the input interface. Docker/Native selects the application runtime inside it.')])+
        p(t('이 설치기는 GitHub에서 선택한 브랜치/태그를 받는 온라인 설치기입니다. main은 변경될 수 있으며 설치된 commit은 외부 루트/config/source.json에 기록됩니다.','This online installer clones the selected GitHub branch/tag. main can change; the installed commit is recorded in the external root/config/source.json.')))
    rows=[
        (t('운영체제','Operating system'),t('Windows 11 x86-64 권장. Windows 10은 지원 상태와 의존성 호환성을 별도 확인합니다.' if win else 'Ubuntu 22.04+ / Debian 12+, x86-64, systemd. 해당 OS 저장소에 호환 드라이버가 있어야 합니다.','Prefer Windows 11 x86-64. For Windows 10, verify servicing status and dependency compatibility.' if win else 'Ubuntu 22.04+ / Debian 12+, x86-64, systemd. A compatible driver must be available for the selected OS.')),
        ('NVIDIA',t('드라이버 '+driver+' 이상. 드라이버 버전만으로 모든 GPU 모델의 지원이 보장되지는 않습니다.','Driver '+driver+' or newer. A driver version alone does not guarantee support for every GPU model.')),
        (t('GPU 검증','GPU validation'),t('설치 시 CUDA 행렬 연산과 torchvision NMS를 검사합니다. 실패하면 중단하며 CPU로 전환하지 않습니다.','Setup tests CUDA matrix operations and torchvision NMS. Failure stops setup; there is no CPU fallback.')),
        (t('Python / AI 환경','Python / AI runtime'),'Python 3.12 · PyTorch 2.11.0 · torchvision 0.26.0 · CUDA 12.8'),
        (t('권한','Privileges'),t('관리자/UAC 승인, winget(App Installer). 필요 도구를 다운로드·설치합니다.' if win else 'sudo 관리자 권한. GUI는 그래픽 데스크톱, python3-tk, polkit 인증 에이전트와 pkexec가 필요합니다.','Administrator/UAC approval and winget (App Installer). Setup downloads and installs dependencies.' if win else 'sudo privileges. GUI additionally needs a graphical desktop, python3-tk, a polkit authentication agent and pkexec.')),
        (t('모델','Models'),t('별도 모델 폴더의 가중치 11개를 SHA-256으로 확인합니다. 파일명을 변경하지 마세요.','11 separately supplied model files are verified by SHA-256. Keep their filenames unchanged.')),
        (t('메모리·저장 공간','Memory & storage'),t('모든 작업에 공통인 RAM/VRAM/디스크 최소치는 확정되지 않았습니다. WSI·타일·모델·DB·다운로드 캐시 용량을 확보하고 실제 작업으로 확인하세요.','No universal RAM/VRAM/disk minimum has been validated. Allow space for WSI, tiles, models, DB and download caches; qualify capacity with your actual workload.'))]
    add(t('시스템 요구사항','System requirements'),table(rows,[t('항목','Item'),t('필수 조건 / 확인사항','Requirement / check')])+p(t('570.xx 기준은 이 배포본의 설치 정책입니다. CUDA minor-version compatibility의 더 낮은 한계와 혼동하지 마세요.','The 570.xx floor is this installer’s policy, not the lower CUDA minor-version compatibility floor.'))+code('nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv')+p(t('CUDA Toolkit을 별도로 수동 설치하는 절차는 없습니다. 설치기가 CUDA용 PyTorch를 준비하지만 호스트 NVIDIA 드라이버는 필요합니다.','The procedure does not require a separate manual CUDA Toolkit installation. Setup supplies CUDA-enabled PyTorch; the host NVIDIA driver is still required.'))+
        box(t('Docker 선택 시: Windows는 WSL2 GPU 지원 및 Docker Desktop 요구사항을 충족해야 합니다. WSL 2.1.5 이상, 가상화 활성화, Microsoft 지원 기간 내 OS를 확인하세요.' if win else 'Docker 선택 시 NVIDIA Container Toolkit을 구성하며 Docker가 재시작될 수 있습니다. Native에는 Toolkit이 필요하지 않습니다.','For Docker: satisfy Docker Desktop requirements, including WSL 2.1.5+, enabled virtualization and a Windows release within Microsoft servicing support.' if win else 'Docker setup configures NVIDIA Container Toolkit and may restart Docker. Native mode does not require Container Toolkit.')))
    add(t('인터넷 · 준비물','Internet access & preparation'),
        box(t('<b>최초 설치와 업데이트에는 인터넷 연결이 필수입니다.</b> 이 파일은 오프라인 설치본이 아닙니다.','<b>Internet access is required for initial installation and updates.</b> This is not an offline installer.'),True)+
        table([(t('다운로드 대상','Downloads'),t('GitHub 소스, Python/Conda 패키지, PyTorch CUDA 패키지, PostgreSQL 및 OS 필수 도구','GitHub source, Python/Conda packages, PyTorch CUDA packages, PostgreSQL and OS dependencies')),('Docker',t('Docker 도구·GPU 기본 이미지·빌드 의존성. 시작 스크립트도 build를 실행하므로 추가 다운로드가 필요할 수 있습니다.','Docker tools, GPU base image and build dependencies. The start script also builds the image and may need downloads.')),(t('외부 접속 예시','Example endpoints'),'github.com · pypi.org · files.pythonhosted.org · download.pytorch.org · repo.anaconda.com · conda.anaconda.org · get.enterprisedb.com · Docker registry/CDN · '+t('Windows Update/winget' if win else 'Ubuntu/Debian 저장소 · download.docker.com · nvidia.github.io','Windows Update/winget' if win else 'Ubuntu/Debian mirrors · download.docker.com · nvidia.github.io'))],[t('범위','Scope'),t('안내','Details')])+
        p(t('HTTPS/DNS 접속과 조직 프록시·인증서를 사전에 확인하세요. 위 목록은 예시이며 저장소 리디렉션/CDN에 따라 추가 주소가 필요합니다. 인증서 검증을 끄지 마세요.','Verify HTTPS/DNS connectivity and your organization’s proxy/certificate configuration. Endpoints above are examples; redirects/CDNs can add destinations. Do not disable certificate verification.'))+
        listing([t('OS용 설치 파일과 해당 PDF, 별도 모델 폴더를 준비합니다.','Prepare the OS-specific installer, this PDF and the separate model folder.'),t('비공개 GitHub 저장소는 사용자명과 Contents: read 권한 PAT를 준비합니다. 일반 로그인 비밀번호를 입력하지 마세요.','For a private GitHub repository, prepare a username and PAT with Contents: read access. Do not enter your GitHub account password.'),t('설치 폴더, 외부 데이터 루트, 모델 폴더를 분리합니다. 기존 설치와 다른 설치를 병행하면 데이터 루트와 포트도 분리합니다.','Separate the installer folder, external data root and model folder. Separate roots and ports for concurrent installations.'),t('배포물의 SHA256SUMS.txt와 설치 파일의 해시를 비교합니다.','Compare installer hashes against SHA256SUMS.txt.')],True)+
        code("Get-FileHash .\\MeDIAuto-Setup-windows-x64.exe -Algorithm SHA256" if win else 'sha256sum -c SHA256SUMS.txt')+
        p(t('설치 후에도 완전한 폐쇄망 동작을 보증하지 않습니다. 의존성·이미지·모델 캐시를 준비하고 실제 차단망에서 실행/분석을 검증해야 합니다.','Fully offline operation after setup is not certified. Prepare dependencies/image/model caches and validate startup and analysis in the intended restricted network.')))
    add(t('GUI 설치 시작','Start the GUI installer'),
        listing(([t('EXE를 고정된 설치 위치에 다운로드한 뒤 더블클릭합니다. UAC 관리자 권한 요청을 승인합니다.','Download the EXE and double-click it. Approve the administrator/UAC prompt.'),t('설치기 압축 해제 폴더를 선택합니다. 기본값은 C:\\MeDIAutoAI\\MeDIAuto-GPU-installer 입니다.','Choose the extraction folder. Default: C:\\MeDIAutoAI\\MeDIAuto-GPU-installer.'),t('필요한 Python 3.12를 준비하면 GUI가 열립니다. 다시 열 때는 같은 폴더의 setup-gui.bat 또는 바탕화면 바로가기를 사용합니다.','The bootstrap prepares Python 3.12 and opens the GUI. Reopen it using setup-gui.bat in the same folder or the desktop shortcut.')] if win else [t('일반 사용자로 그래픽 데스크톱에 로그인합니다. SSH 전용 서버는 다음 CLI 절차를 사용합니다.','Log in to a graphical desktop as a regular user. On an SSH-only server, use the CLI procedure.'),t('아래 명령으로 실행합니다. GUI 실행기 전체를 sudo로 실행하지 마세요.','Run the commands below. Do not run the entire GUI launcher with sudo.'),t('$HOME/MeDIAuto-GPU-installer에 설치기를 풉니다. python3-tk 설치 및 작업 시작 시 시스템 인증 창에 관리자 암호를 입력합니다.','The launcher extracts to $HOME/MeDIAuto-GPU-installer. Approve system authentication for python3-tk installation and installation tasks.')]),True)+
        (code('chmod +x MeDIAuto-Setup-linux-x64.run\n./MeDIAuto-Setup-linux-x64.run\n\n# Reopen\nbash "$HOME/MeDIAuto-GPU-installer/setup-gui.sh"') if not win else box(t('Windows EXE에는 코드 서명이 없습니다. 기관 보안 정책에 따라 제공자와 SHA-256을 확인하고 진행하세요.','The Windows EXE is unsigned. Verify the supplier and SHA-256 under your organization’s security policy.')))+
        '<h3>'+t('실행 환경 선택','Choose the runtime')+'</h3>'+table([('1. Docker',t('Git 소스 + Docker GPU 이미지 + 호스트 PostgreSQL. 로컬 Conda 앱/Philips 환경도 준비합니다.','Git source + Docker GPU image + host PostgreSQL. Also prepares local Conda app/Philips environments.')),('2. Native',t('Git 소스 + 호스트 Conda GPU 앱/Philips 환경 + 호스트 PostgreSQL. Docker 없이 실행합니다.','Git source + host Conda GPU app/Philips environments + host PostgreSQL. Runs without Docker.'))],[t('선택','Option'),t('설치 내용','Installed components')])+
        p(t('메인 Conda 환경은 medicus-saas입니다. Philips 환경은 '+('philips-sdk-py37' if win else 'philips-sdk-py38')+'입니다. 같은 Conda의 이름 환경을 다른 설치와 공유할 수 있으므로 업데이트 영향을 확인하세요.','Main Conda environment: medicus-saas. Philips environment: '+('philips-sdk-py37' if win else 'philips-sdk-py38')+'. Named environments may be shared by installations using the same Conda; consider update effects.'))+
        box(t('설치 폴더는 이후 실행·재시도에 필요합니다. 설치 후 임의로 이동하거나 삭제하지 마세요.','The installer folder is needed for startup and retries. Do not move or delete it after setup.')))
    caption=t('실제 공통 GUI의 Linux 캡처입니다. Windows에서는 기본 경로가 C:/MeDIAutoData, 드라이버 기준이 570.65이며 창 장식·글꼴이 다릅니다. Windows 실기 캡처가 아닙니다.' if win else '최종 설치기 GUI를 Linux 가상 디스플레이에서 실제 실행해 캡처했습니다. 모델 경로는 입력 예시이며 설치는 실행하지 않았습니다.','Actual shared GUI captured on Linux, not a native Windows screenshot. On Windows the default root is C:/MeDIAutoData, the driver floor is 570.65, and fonts/window decoration differ.' if win else 'Actual final installer GUI captured on a Linux virtual display. The model path is an example; installation was not started.')
    add(t('설치 화면 살펴보기','Installer screen reference'),shot('installer-linux.png',caption,'gui')+p(t('위에서부터 실행 환경 → 경로 → 포트 → GitHub 정보를 입력합니다. 하단의 설치 시작, 라이선스 보기, 로그 저장 버튼을 사용합니다. 화면이 작으면 오른쪽 스크롤 막대를 내리세요.','Read top to bottom: runtime → paths → ports → GitHub. Bottom buttons: 설치 시작 (Start installation), Philips SDK 라이선스 보기 (View license), 로그 저장 (Save log). Scroll down on smaller screens.')))
    add(t('입력값 설정','Configure the fields'),table([
        ('외부 데이터 폴더',t('DB·결과·주석·로그 저장 루트. 예: ','Root for DB, results, annotations and logs. Example: ')+E(root)),
        ('모델 폴더',t('필수. 가중치 11개가 들어 있는 기존 폴더. 설치기가 별도 복사하지 않습니다.','Required. Existing folder with 11 weights. Setup uses this location without making a separate copy.')),
        ('슬라이드 폴더',t('비우면 외부 루트/slides. 별도 경로도 지정할 수 있습니다.','Blank uses external root/slides; a separate path is allowed.')),
        ('웹 포트 / PostgreSQL 포트','18093 / 55432. '+t('이미 사용 중이면 다른 포트를 선택합니다.','Choose other ports if occupied.')),
        ('웹 바인딩 IP',t('0.0.0.0: LAN 허용 / 127.0.0.1: 해당 PC만. LAN 브라우저에는 실제 서버 IP를 입력합니다.','0.0.0.0: LAN access / 127.0.0.1: this PC only. Use the actual server IP in LAN browsers.')),
        ('GitHub 저장소','Leeyoungsup/Mediauto-studio_saas'),
        ('브랜치 / 태그',t('기본 main. 배포 담당자가 지정한 브랜치/태그가 있으면 그 값을 사용합니다. commit 문자열 직접 clone은 이 입력에서 지원하지 않습니다.','Default main. Use a release branch/tag supplied by the deployment owner if available. Direct cloning by commit hash is not supported by this input.')),
        ('GitHub 사용자명 / PAT',t('공개 저장소는 둘 다 빈칸. 비공개는 읽기 권한 PAT. PAT는 파일·명령 인자에 저장하지 않습니다.','Leave both blank for public repositories. Private repositories need a read PAT. PATs are not persisted to files or command-line arguments.'))
    ],[t('화면 항목','GUI field (Korean UI)'),t('입력 / 동작','Value / behavior')])+box(t('기존 설치를 다시 열면 저장된 경로·포트·브랜치 입력이 잠깁니다. 기존 작업 폴더를 자동 pull/reset하지 않습니다.','When reopening an installation, saved path/port/branch fields are locked. Existing source trees are not automatically pulled or reset.'))+p(t('설치 시작을 누르면 진행 로그가 표시됩니다. 진행 막대는 작업 중 표시이며 정확한 완료 퍼센트가 아닙니다.','Click 설치 시작 to begin. The progress bar indicates activity, not an exact completion percentage.')))
    if not win:
        add(t('터미널 / SSH 설치','Terminal / SSH installation'),
            p(t('GUI 없이 같은 설치 기능을 사용합니다. 다운로드한 tar.gz를 고정된 사용자 소유 폴더에 풉니다.','Use the same installation functionality without a GUI. Extract the tar.gz into a permanent, user-owned location.'))+
            code('tar -xzf MeDIAuto-Setup-linux-x64-cli.tar.gz\ncd MeDIAuto-GPU-installer\nbash install.sh')+
            shot('linux-cli.png',t('실제 install.sh의 초기 메뉴 출력을 브라우저에 표시한 캡처입니다. 설치 선택·sudo 작업은 실행하지 않았습니다.','Capture of actual install.sh startup output rendered in a browser. No installation selection or privileged installation was performed.'),'cli')+
            listing([t('1 또는 Enter: Docker / 2: Native. 요청 시 sudo 암호를 입력합니다.','1 or Enter: Docker / 2: Native. Enter your sudo password when prompted.'),t('External data root → Model folder → Slide folder → Web port → Dedicated PostgreSQL port → Web bind를 입력합니다.','Enter External data root → Model folder → Slide folder → Web port → Dedicated PostgreSQL port → Web bind.'),t('GitHub repository와 branch/tag를 확인합니다. 비공개 저장소에는 사용자명/PAT를 입력합니다. PAT 입력은 표시되지 않습니다.','Confirm GitHub repository and branch/tag. Supply username/PAT for a private repository; PAT input is hidden.'),t('SDK 라이선스를 검토하고 동의 여부를 직접 입력합니다. 재부팅이 필요하면 재부팅 후 같은 명령을 실행합니다.','Review the SDK license and explicitly answer the consent prompt. If a reboot is required, reboot and rerun the same command.')],True)+
            box(t('CLI 패키지는 그래픽 데스크톱이나 Tk가 필요하지 않습니다. 모델·인터넷·NVIDIA·sudo 조건은 GUI와 동일합니다.','The CLI path does not need a graphical desktop or Tk. Model, internet, NVIDIA and sudo requirements are the same as GUI setup.')))
    if not win:
        add(t('Python · Conda 자동 준비 / 재설치','Automatic Python & Conda setup / retry'),
            p(t('r20은 시스템 Python 3.8에서도 설치 준비를 시작합니다. Python 버전 검사 전에 Conda와 설치기용 Python을 자동 준비하므로 수동 Conda 설치나 base 업그레이드가 필요하지 않습니다.','r20 can bootstrap from system Python 3.8. It prepares Conda and installer Python before the installer version check; no manual Conda installation or base upgrade is required.'))+
            listing([t('기존 Conda를 찾아 재사용합니다. 없으면 공식 Miniconda를 다운로드하고 SHA-256 검증 후 설치합니다.','Find and reuse existing Conda, or download official Miniconda and verify its SHA-256 before installation.'),t('별도 mediauto-installer 환경에 Python 3.12를 준비합니다. 정상 환경은 재사용하며 기존 base Python은 변경하지 않습니다.','Prepare Python 3.12 in the separate mediauto-installer environment. Reuse a working environment without changing base Python.'),t('준비된 Python으로 설치를 자동 재개하고 이후 앱 및 Philips 환경을 구성합니다. sudo 인증·GitHub 인증정보·SDK 동의는 직접 입력합니다.','Continue setup automatically using that Python, then configure app and Philips environments. Enter sudo authorization, GitHub credentials and SDK consent yourself.')],True)+
            p(t('현재 경로 예시: r20 CLI 파일을 /mnt/hdd1/KNUCH에 저장한 뒤 아래 명령을 실행합니다. 기존 설치기 폴더에 설치 코드만 덮어쓰며 별도 모델·데이터 폴더는 유지합니다.','Existing-path example: save the r20 CLI archive in /mnt/hdd1/KNUCH and run the following. It replaces packaged installer code in place and preserves separate model/data folders.'))+
            code('cd /mnt/hdd1/KNUCH\ntar -xzf MeDIAuto-Setup-linux-x64-cli.tar.gz\ncd MeDIAuto-GPU-installer\nbash install.sh')+
            table([('Mode','2 (Native)'),('External data root','/mnt/hdd1/KNUCH/MeDIAutoData'),('Model folder','/mnt/hdd1/KNUCH/model')],[t('입력','Field'),t('예시','Example')])+
            p(t('기존 데이터 루트가 있다면 반드시 기존 값을 사용하세요. 설치 완료 후 같은 폴더에서 bash native/start.sh로 실행합니다.','If a data root already exists, keep its saved value. After setup completes, run bash native/start.sh from the same installer folder.'))+
            box(t('다운로드에는 인터넷이 필요합니다. 초기 준비 캐시는 선택한 native 또는 docker 폴더의 programs/bootstrap-cache에 저장됩니다. Ubuntu 20.04의 Python 3.8 진입 경로는 회귀 검증했지만 해당 OS 전체 설치는 검증하지 않았습니다.','Internet access is required. Bootstrap downloads are cached under programs/bootstrap-cache in the selected native or docker folder. The Python 3.8 bootstrap path was regression tested; a full Ubuntu 20.04 installation was not validated.')))
    add(t('드라이버 · 라이선스 · 완료','Driver, license & completion'),
        p(t('설치기는 호환 드라이버가 있으면 유지합니다. 부족하면 '+('Windows Update' if win else 'Ubuntu/Debian OS 저장소')+'에서 설치를 시도합니다. 제공되는 호환 패키지가 없으면 중단하고 수동 설치를 안내합니다.','Setup keeps a compatible driver. Otherwise it attempts installation from '+('Windows Update' if win else 'Ubuntu/Debian OS repositories')+'. If no compatible package is offered, it stops and requests manual installation.'))+
        box(t('재부팅 안내가 나오면 직접 재부팅하고 같은 설치기로 이어서 진행하세요. 자동 재부팅하지 않습니다.'+('' if win else ' Secure Boot 사용 시 부팅 화면에서 MOK 등록이 필요할 수 있습니다.'),'If a restart is requested, reboot manually and rerun the same installer. Setup does not reboot automatically.'+('' if win else ' Secure Boot may require MOK enrollment during boot.')),True)+
        shot('sdk-license-linux.png',t('공통 SDK 라이선스 창의 실제 Linux 캡처. 전체 내용을 읽고 동의 여부를 직접 선택하세요.','Actual Linux capture of the shared SDK license dialog. Read the complete terms and choose whether to accept.'),'license')+
        p(t('Philips SDK의 연구용 라이선스가 포함돼 있습니다. 허용 범위를 확인한 뒤 사용하세요. 설치 파일은 OS별 SDK와 지원 파일을 포함하지만 모델은 포함하지 않습니다.','The Philips SDK includes research-use license terms. Review the permitted use. Packages include OS-specific SDK/support files, but not model weights.'))+
        box(t('<b>설치 완료 후 서버는 자동 시작되지 않습니다.</b> GUI 완료 메시지 또는 터미널의 Installation complete를 확인하고 다음 페이지대로 시작합니다.','<b>The application does not start automatically after setup.</b> Check the GUI completion message or terminal Installation complete, then start it as shown next.')))
    start=('native\\start.bat' if win else 'bash native/start.sh')
    docker=('docker\\start.bat' if win else 'bash docker/start.sh')
    local=('docker\\start-local.bat' if win else 'bash docker/start-local.sh')
    stop=('docker\\stop.bat' if win else 'bash docker/stop.sh')
    add(t('서버 실행 · 로그인 · 종료','Start, sign in & stop'),
        p(t('설치기 폴더에서 선택한 방식의 파일을 실행합니다. Windows는 탐색기에서 start.bat를 더블클릭할 수 있습니다.' if win else '일반 사용자 터미널에서 설치기 폴더로 이동해 실행합니다.','Run the entry point for your selected runtime from the installer folder. On Windows, double-click start.bat in File Explorer.' if win else 'Use a regular-user terminal and change to the installer folder.'))+
        table([('Native',code(start)),('Docker',code(docker)),(t('Docker 설치의 로컬 실행','Local run after Docker setup'),code(local))],[t('방식','Runtime'),t('실행 파일 / 명령','Entry point / command')])+
        p(t('동일 설치의 Docker와 로컬 실행은 DB·데이터·포트를 공유합니다. 한 번에 하나만 실행하세요.','Docker and local execution for the same installation share the DB, data and port. Run only one at a time.'))+
        shot('login.png',t('현재 프론트엔드 로그인 화면의 실제 브라우저 캡처. 운영 계정 로그인은 수행하지 않았습니다.','Actual browser capture of the current frontend login page. No production account login was performed.'),'login')+
        p(t('접속: http://localhost:18093 (포트를 변경했다면 해당 포트). 새 DB 최초 계정: <b>admin / admin1234!</b>. 로그인 후 비밀번호를 변경하세요. 기존 DB 계정은 재설치로 바뀌지 않습니다.','Open http://localhost:18093 (use your configured port). New DB initial account: <b>admin / admin1234!</b>. Change the password after signing in. Reinstalling does not reset existing DB accounts.'))+
        p(t('종료: 실행 터미널에서 Ctrl+C. Docker는 '+stop+'도 사용할 수 있습니다. PostgreSQL 서비스는 별도로 유지됩니다.','Stop with Ctrl+C in the running terminal. Docker also supports '+stop+'. The PostgreSQL service remains separate.')))
    add(t('설치 확인 · 재시도 · 백업','Verify, retry & back up'),
        listing([t('설치 로그에 실패가 없고 GPU 검사 및 Philips bridge 검사가 통과했는지 확인합니다.','Confirm setup completed without errors and GPU/Philips bridge checks passed.'),t('서버를 시작하고 브라우저 로그인, 테스트 슬라이드 업로드·열기, GPU AI 분석, 주석 저장·재열기를 확인합니다.','Start the server and verify login, test-slide upload/opening, GPU AI analysis, and annotation save/reload.'),t('LAN 사용 시 다른 PC에서 실제 서버 IP와 웹 포트로 접속합니다. 기관 방화벽 정책에 따라 접근을 설정합니다.','For LAN use, test access from another PC with the server IP and web port. Configure access under your network policy.'),t('설치가 실패하면 로그를 보존하고 원인을 해결한 뒤 같은 설치 파일/폴더로 재시도합니다. database·secrets부터 지우지 마세요.','If setup fails, keep logs, resolve the cause and retry from the same installer folder. Do not delete database or secrets to fix an error.')],True)+
        '<h3>'+t('백업 범위','Backup scope')+'</h3>'+code(root+'\n  config/       settings, source.json, ADMIN_LOGIN.txt\n  database/     PostgreSQL data\n  secrets/      signing/encryption keys\n  slides/       default slide storage\n  annotations/  annotation files\n  patches/      patch and cell annotation files\n  results/      AI outputs\n  logs/         application logs')+
        p(t('별도 지정한 슬라이드·모델 경로도 포함하세요. DB는 일관된 PostgreSQL 백업 도구 또는 정상 종료 후 복사 방식으로 백업하고 secrets와 함께 복원해야 합니다. 실행 중인 database 폴더를 단순 복사하는 것만으로 충분하지 않습니다.','Include separately configured slide/model paths. Use a consistent PostgreSQL backup or a cleanly stopped copy, and restore it with the matching secrets. A plain copy of the live database directory is insufficient.'))+
        '<h3>'+t('업데이트','Updates')+'</h3>'+p(t('서버 종료 → DB·키·파일 백업 → Git 로컬 변경 보존 → 원하는 브랜치/태그 반영 → 의존성 변경 시 설치 재실행 → 서버 시작. 설치기 재실행만으로 기존 Git 소스가 최신화되지는 않습니다.','Stop → back up DB/keys/files → preserve local Git changes → update the intended branch/tag → rerun setup for dependency changes → start. Rerunning setup alone does not update an existing Git checkout.')))
    add(t('문제 해결 · 검증 범위','Troubleshooting & validation scope'),
        table([
            (t('드라이버 / CUDA 실패','Driver / CUDA failure'),t('nvidia-smi 및 '+driver+' 기준을 확인합니다. 지원되는 드라이버 설치 후 재부팅하고 재시도합니다. 기준을 만족해도 GPU 모델/패키지 호환성 검사를 통과해야 합니다.','Check nvidia-smi and the '+driver+' floor. Install a supported driver, reboot and retry. GPU/package runtime compatibility must also pass.')),
            (t('다운로드 / 인증서','Download / certificate'),t('인터넷·DNS·시스템 시간·프록시 인증서를 확인합니다. Windows Update/OS 저장소 정책도 확인합니다.','Check internet/DNS, system time, proxy certificates and Windows Update/OS repository policies.')),
            (t('CXXABI / greenlet 오류','CXXABI / greenlet error'),t('새 설치기로 재실행하세요. Conda C++ 런타임을 자동 보완하고 GPU 라이브러리보다 먼저 불러옵니다. 시스템 libstdc++는 교체하지 않습니다.','Rerun the updated installer. It prepares the Conda C++ runtime and loads it before GPU libraries. System libstdc++ is not replaced.')),
            (t('포트 충돌','Port conflict'),t('다른 DB·서버의 포트를 사용하지 마세요. 새 설치는 다른 포트를 선택하고 기존 설치 재시도는 저장된 설정을 확인합니다.','Do not reuse another DB/server’s port. Choose another port for a new install; review saved settings for retries.')),
            (t('모델 검사 실패','Model check failure'),t('지정 폴더·파일명·11개 가중치의 배포 버전을 확인합니다. 해시 검사를 우회하지 마세요.','Check the selected folder, filenames and supplied version of all 11 weights. Do not bypass hash validation.')),
            (t('GUI가 열리지 않음','GUI does not open'),t('setup-gui.bat로 재시도하고 Python 3.12, winget, UAC 정책을 확인합니다.' if win else 'DISPLAY/Wayland 데스크톱, Tk, pkexec/polkit을 확인합니다. SSH는 CLI 패키지를 사용합니다.','Retry setup-gui.bat and check Python 3.12, winget and UAC policy.' if win else 'Check the graphical session, Tk and pkexec/polkit. Use CLI over SSH.')),
            (t('접속되지 않음','Cannot connect'),t('설치만 끝낸 상태인지 확인하고 start를 실행합니다. 실제 웹 포트·서버 IP·바인딩·방화벽·logs/app.log를 확인합니다.','Run start if only installation has finished. Check the web port, server IP, binding, firewall and logs/app.log.'))
        ],[t('증상','Symptom'),t('확인 / 조치','Check / action')])+
        code(('powershell -NoProfile -Command "Get-Content -LiteralPath \'C:\\MeDIAutoData\\logs\\app.log\' -Tail 100"') if win else 'tail -n 100 /srv/mediauto/logs/app.log')+
        p(t('GUI의 로그 저장 기능으로 설치 로그를 남길 수 있습니다. config/ADMIN_LOGIN.txt와 설정 파일에는 인증정보가 있으므로 공유하지 마세요.','Save installation logs with 로그 저장. config/ADMIN_LOGIN.txt and configuration files contain credentials; do not share them.'))+
        box(t('이 문서의 공통 GUI·SDK 화면은 Linux 캡처이며, Windows 전체 설치·드라이버 변경·재부팅과 실제 GPU 분석 완료를 증명하는 캡처는 아닙니다. 대상 PC의 새 설치 검증이 필요합니다.','Shared GUI/SDK images were captured on Linux. They do not prove a full Windows installation, driver change/reboot or completed GPU analysis. Qualify a clean installation on the target PC.'))+
        '<p class="small">'+t('공식 근거: ','Official references: ')+
        '<a href="https://docs.nvidia.com/cuda/archive/12.8.0/cuda-toolkit-release-notes/index.html">NVIDIA CUDA 12.8, Table 3</a> · <a href="https://pytorch.org/get-started/previous-versions/">PyTorch 2.11.0</a> · <a href="https://docs.docker.com/desktop/setup/install/windows-install/">Docker Desktop / Windows</a></p>')
    return pages


def render_document(platform, lang):
    pages=pages_for(platform,lang);total=len(pages)
    chunks=['<!doctype html><html lang="'+('ko' if lang=='KO' else 'en')+'"><meta charset="utf-8"><title>MeDIAuto '+platform+' '+lang+' Installation Guide</title><style>'+CSS+'</style><body>']
    for i,(title,body) in enumerate(pages,1):
        chunks.append('<section class="page"><div class="kicker">MeDIAuto / '+platform.upper()+' / '+RELEASE+'</div><h2>'+title+'</h2><div class="content">'+body+'</div><footer class="footer"><span>MeDIAuto AI · '+platform+' · '+lang+'</span><span>'+str(i).zfill(2)+' / '+str(total).zfill(2)+'</span></footer></section>')
    return ''.join(chunks)+'</body></html>'


def build(output=DEFAULT_OUT):
    output=Path(output);docs=output/'guides';docs.mkdir(parents=True,exist_ok=True)
    assets=docs/'assets';assets.mkdir(exist_ok=True)
    for name in ('installer-linux.png','sdk-license-linux.png','capture-provenance.json'):
        shutil.copy2(SOURCE/'assets'/name,assets/name)
    # Invalid menu input exits before dispatch to any privileged installer.
    cli=subprocess.run(['bash',str(ROOT/'deployment/installer/install.sh')],input='3\n',capture_output=True,text=True,check=False)
    if cli.returncode!=1 or 'Enter 1 or 2.' not in cli.stdout: raise RuntimeError('Unexpected CLI capture behavior')
    cli_text=cli.stdout.replace('Enter 1 or 2.\n','')+'Choose installation method [1]: '
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=os.environ.get('CHROME_PATH','/opt/google/chrome/chrome'),headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1100,'height':760},device_scale_factor=1.5)
        page.goto((ROOT/'frontend/login.html').as_uri());page.evaluate('document.fonts.ready');page.locator('.login-card').screenshot(path=str(assets/'login.png'))
        page.set_content('<body style="margin:0;background:#102331;color:#def7ea;font:19px monospace;padding:30px"><main><p style="color:#7ed6cf">Linux · installer startup output</p><pre style="white-space:pre-wrap;line-height:1.6">'+E(cli_text)+'</pre></main></body>')
        page.locator('main').screenshot(path=str(assets/'linux-cli.png'))
        checks=[]
        for platform in ('Windows','Linux'):
            for lang in ('KO','EN'):
                name='MeDIAuto-'+platform+'-Installation-Guide-'+lang
                source=docs/(name+'.html');source.write_text(render_document(platform,lang),encoding='utf-8')
                page.goto(source.as_uri());page.emulate_media(media='print');page.evaluate('document.fonts.ready')
                check=page.evaluate('''() => ({pages:document.querySelectorAll('.page').length, brokenImages:[...document.images].filter(i=>!i.complete||!i.naturalWidth).map(i=>i.src), overflow:[...document.querySelectorAll('.page')].flatMap((s,i)=>{const content=s.querySelector('.content').getBoundingClientRect(); const footer=s.querySelector('.footer').getBoundingClientRect();return content.bottom>footer.top-6 ? [{page:i+1,bottom:content.bottom,footer:footer.top}] : []})})''')
                if check['overflow'] or check['brokenImages']: raise RuntimeError(name+': '+json.dumps(check))
                page.pdf(path=str(docs/(name+'.pdf')),format='A4',print_background=True,prefer_css_page_size=True)
                checks.append(dict(document=name,**check));print(name+'.pdf',check['pages'],'pages')
        browser.close()
    (docs/'layout-validation.json').write_text(json.dumps(checks,indent=2)+'\n')
    return docs

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=DEFAULT_OUT)
    build(parser.parse_args().output)
