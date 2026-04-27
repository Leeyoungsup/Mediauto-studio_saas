#!/usr/bin/env bash
# ============================================================
#  MeDIAuto Studio SaaS - Dependency Install Script (Linux)
#  - Detect distro
#  - Verify/install MongoDB + OpenSlide system libs
#  - Create/update conda env
#  - Install PyTorch with CUDA
#  - Install backend/requirements.txt
#  - Verify MongoDB connectivity
# ============================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ENV_NAME="yslee"
PY_VER="3.12"
CUDA_TAG="cu121"

# ── Colors (skipped if not a tty) ──
if [[ -t 1 ]]; then
    C_RED=$'\033[31m'; C_YELLOW=$'\033[33m'; C_GREEN=$'\033[32m'
    C_CYAN=$'\033[36m'; C_BOLD=$'\033[1m'; C_RESET=$'\033[0m'
else
    C_RED=""; C_YELLOW=""; C_GREEN=""; C_CYAN=""; C_BOLD=""; C_RESET=""
fi
log_info()  { echo "${C_CYAN}[INFO]${C_RESET}  $*"; }
log_ok()    { echo "${C_GREEN}[OK]${C_RESET}    $*"; }
log_warn()  { echo "${C_YELLOW}[WARN]${C_RESET}  $*"; }
log_error() { echo "${C_RED}[ERROR]${C_RESET} $*"; }
section()   { echo; echo "${C_BOLD}============================================================${C_RESET}"; echo "${C_BOLD} $*${C_RESET}"; echo "${C_BOLD}============================================================${C_RESET}"; }

confirm() {
    # confirm "prompt" → returns 0 if yes, 1 if no. Default = no.
    local prompt="$1"
    read -r -p "$prompt [y/N] " ans
    [[ "$ans" =~ ^[Yy]$ ]]
}

# ── Distro detection ──
DISTRO_ID=""
DISTRO_LIKE=""
if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    DISTRO_ID="${ID:-}"
    DISTRO_LIKE="${ID_LIKE:-}"
fi

is_debian_family() { [[ "$DISTRO_ID" == "debian" || "$DISTRO_ID" == "ubuntu" || "$DISTRO_LIKE" == *"debian"* ]]; }
is_rhel_family()   { [[ "$DISTRO_ID" == "rhel" || "$DISTRO_ID" == "centos" || "$DISTRO_ID" == "fedora" || "$DISTRO_ID" == "rocky" || "$DISTRO_ID" == "almalinux" || "$DISTRO_LIKE" == *"rhel"* || "$DISTRO_LIKE" == *"fedora"* ]]; }
is_arch_family()   { [[ "$DISTRO_ID" == "arch" || "$DISTRO_LIKE" == *"arch"* ]]; }

# ── Pre-checks ──
if ! command -v conda >/dev/null 2>&1; then
    log_error "conda not found. Install Miniconda/Anaconda first:"
    echo "         https://docs.conda.io/en/latest/miniconda.html"
    exit 1
fi

# ── STEP 1: MongoDB ──
section "[STEP 1/6] MongoDB Setup"
if command -v mongod >/dev/null 2>&1; then
    log_info "mongod found: $(command -v mongod)"
else
    log_warn "mongod not found in PATH."
    echo
    echo "  Install commands (community edition — copy-paste, then rerun this script):"
    if is_debian_family; then
        cat <<'EOF'
    # Ubuntu/Debian — official MongoDB 7.0 repo:
    sudo apt update && sudo apt install -y gnupg curl
    curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | \
        sudo gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor
    echo "deb [signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg] \
        https://repo.mongodb.org/apt/ubuntu $(lsb_release -cs)/mongodb-org/7.0 multiverse" | \
        sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list
    sudo apt update && sudo apt install -y mongodb-org
    sudo systemctl enable --now mongod
EOF
    elif is_rhel_family; then
        cat <<'EOF'
    # RHEL/Fedora/Rocky — official MongoDB 7.0 repo:
    sudo tee /etc/yum.repos.d/mongodb-org-7.0.repo >/dev/null <<'REPO'
[mongodb-org-7.0]
name=MongoDB Repository
baseurl=https://repo.mongodb.org/yum/redhat/$releasever/mongodb-org/7.0/x86_64/
gpgcheck=1
enabled=1
gpgkey=https://www.mongodb.org/static/pgp/server-7.0.asc
REPO
    sudo dnf install -y mongodb-org
    sudo systemctl enable --now mongod
EOF
    elif is_arch_family; then
        cat <<'EOF'
    # Arch (AUR) — community edition:
    yay -S mongodb-bin    # or: paru -S mongodb-bin
    sudo systemctl enable --now mongodb
EOF
    else
        echo "    Distro '$DISTRO_ID' not recognized. See:"
        echo "    https://www.mongodb.com/docs/manual/administration/install-on-linux/"
    fi
    echo
    echo "  Or use a remote/managed MongoDB and export MONGO_URI=mongodb://host:port"
    if confirm "Continue without local MongoDB"; then
        log_warn "Continuing — backend won't start until a MongoDB is reachable."
    else
        exit 1
    fi
fi

# Try to ensure mongod service is running (if systemd available).
if command -v systemctl >/dev/null 2>&1; then
    # Service name varies: 'mongod' (official repo) or 'mongodb' (Arch / older Debian).
    for svc in mongod mongodb; do
        if systemctl list-unit-files --type=service 2>/dev/null | awk '{print $1}' | grep -Fxq "${svc}.service"; then
            if systemctl is-active --quiet "$svc"; then
                log_ok "service $svc already active."
            else
                log_info "Starting $svc (sudo) ..."
                if sudo systemctl start "$svc"; then
                    log_ok "$svc started."
                else
                    log_warn "Could not start $svc. Check 'journalctl -u $svc -n 50'."
                fi
            fi
            break
        fi
    done
fi

# ── STEP 2: OpenSlide system library ──
section "[STEP 2/6] OpenSlide system library"
# openslide-python wraps libopenslide.so.0. Wheel doesn't bundle it on Linux.
if ldconfig -p 2>/dev/null | grep -q "libopenslide\.so"; then
    log_ok "libopenslide already installed."
else
    log_warn "libopenslide not found."
    if is_debian_family; then
        echo "    sudo apt install -y libopenslide0 libopenslide-dev"
    elif is_rhel_family; then
        echo "    sudo dnf install -y openslide openslide-devel"
    elif is_arch_family; then
        echo "    sudo pacman -S --needed openslide"
    else
        echo "    Install OpenSlide for your distro: https://openslide.org/download/"
    fi
    if confirm "Continue without OpenSlide"; then
        log_warn "Continuing — slide loading will fail until OpenSlide is installed."
    else
        exit 1
    fi
fi

# ── STEP 3: Conda env ──
section "[STEP 3/6] Conda environment \"$ENV_NAME\""
if conda env list | awk '{print $1}' | grep -Fxq "$ENV_NAME"; then
    log_info "env \"$ENV_NAME\" already exists."
else
    log_info "Creating env: $ENV_NAME (python $PY_VER)"
    if ! conda create -y -n "$ENV_NAME" python="$PY_VER"; then
        log_error "Failed to create conda env."
        exit 1
    fi
fi

# ── STEP 4: PyTorch ──
section "[STEP 4/6] PyTorch (CUDA $CUDA_TAG)"
conda run -n "$ENV_NAME" pip install --upgrade pip
if ! conda run -n "$ENV_NAME" pip install torch torchvision \
        --index-url "https://download.pytorch.org/whl/$CUDA_TAG"; then
    log_warn "CUDA build failed. Falling back to CPU-only PyTorch ..."
    conda run -n "$ENV_NAME" pip install torch torchvision
fi

# ── STEP 5: backend requirements ──
section "[STEP 5/6] Backend requirements"
if ! conda run -n "$ENV_NAME" pip install -r "$SCRIPT_DIR/backend/requirements.txt"; then
    log_error "pip install failed."
    exit 1
fi

# ── STEP 6: connectivity test ──
section "[STEP 6/6] MongoDB connectivity test"
MONGO_URI="${MONGO_URI:-mongodb://localhost:27017}"
if conda run -n "$ENV_NAME" python -c "
import os
from pymongo import MongoClient
uri = os.environ.get('MONGO_URI', 'mongodb://localhost:27017')
MongoClient(uri, serverSelectionTimeoutMS=3000).admin.command('ping')
print(f'[OK] MongoDB ping succeeded @ {uri}')
"; then
    :
else
    log_warn "MongoDB ping failed."
    echo "        Causes:"
    echo "          - service not running          (sudo systemctl start mongod)"
    echo "          - wrong URI                    (export MONGO_URI=mongodb://host:port)"
    echo "          - firewall / auth required     (check journalctl -u mongod)"
    echo "        Backend will still install but won't start without a reachable MongoDB."
fi

# ── Done ──
echo
echo "${C_BOLD}============================================================${C_RESET}"
echo "${C_GREEN}[DONE]${C_RESET} Install complete."
echo
echo " Run ./start.sh to launch the SaaS server."
echo
echo " NOTE (Migration to another machine):"
echo "   Copy these from the original install:"
echo "     - backend/.secrets.json   (password pepper, AES key — CRITICAL)"
echo "     - backend/uploads/        (WSI files, tile cache)"
echo "     - backend/model/          (AI weights)"
echo "     - MongoDB dump            (mongodump on old / mongorestore on new)"
echo "   Losing .secrets.json breaks all existing user passwords."
echo
echo " MongoDB defaults:"
echo "   URI    = mongodb://localhost:27017   (override: export MONGO_URI=...)"
echo "   DB     = medicus_studio              (override: export MONGO_DB_NAME=...)"
echo "${C_BOLD}============================================================${C_RESET}"
