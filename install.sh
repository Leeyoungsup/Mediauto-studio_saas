#!/usr/bin/env bash
# ============================================================
#  MeDIAuto Studio SaaS - Dependency Install Script (Linux)
#  - Detect distro
#  - Install/configure PostgreSQL
#  - Create/update conda env
#  - Install PyTorch with CUDA
#  - Install backend/requirements.txt
#  - Apply PostgreSQL schema
#  - Prepare runtime directories/secrets and validate models/native libraries
# ============================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ENV_NAME="${MEDIAUTO_CONDA_ENV:-medicus-saas}"
PY_VER="${MEDIAUTO_PYTHON_VERSION:-3.12}"
CUDA_TAG="${MEDIAUTO_CUDA_TAG:-cu121}"
PHILIPS_ENV_NAME="${PHILIPS_CONDA_ENV:-philips-sdk-py38}"
PHILIPS_PY_VER="3.8"
POSTGRES_ENV_NAME="${MEDIAUTO_POSTGRES_CONDA_ENV:-mediauto-postgres}"
POSTGRES_DATA_DIR="${MEDIAUTO_POSTGRES_DATA_DIR:-$SCRIPT_DIR/postgres_data}"
POSTGRES_UNIT_FILE="${MEDIAUTO_POSTGRES_UNIT_FILE:-$HOME/.config/systemd/user/mediauto-postgresql.service}"

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

# ── STEP 1: OpenSlide system library ──
section "[STEP 1/8] OpenSlide and libvips system libraries"
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
    log_error "Install OpenSlide with the command above, then rerun install.sh."
    exit 1
fi

# pyvips is a Python binding and still needs the native libvips shared library.
if ldconfig -p 2>/dev/null | grep -q "libvips\.so"; then
    log_ok "libvips already installed."
else
    log_warn "libvips not found."
    if is_debian_family; then
        echo "    sudo apt install -y libvips42 libvips-dev"
    elif is_rhel_family; then
        echo "    sudo dnf install -y vips vips-devel"
    elif is_arch_family; then
        echo "    sudo pacman -S --needed libvips"
    else
        echo "    Install libvips for your distro: https://www.libvips.org/install.html"
    fi
    log_error "Install libvips with the command above, then rerun install.sh."
    exit 1
fi

# ── STEP 2: Conda env ──
section "[STEP 2/8] Conda environment \"$ENV_NAME\""
if conda env list | awk '{print $1}' | grep -Fxq "$ENV_NAME"; then
    log_info "env \"$ENV_NAME\" already exists."
else
    log_info "Creating env: $ENV_NAME (python $PY_VER)"
    if ! conda create -y -n "$ENV_NAME" python="$PY_VER"; then
        log_error "Failed to create conda env."
        exit 1
    fi
fi

# ── STEP 3: PyTorch ──
section "[STEP 3/8] PyTorch (CUDA $CUDA_TAG)"
conda run -n "$ENV_NAME" pip install --upgrade pip
if ! conda run -n "$ENV_NAME" pip install torch torchvision \
        --index-url "https://download.pytorch.org/whl/$CUDA_TAG"; then
    log_warn "CUDA build failed. Falling back to CPU-only PyTorch ..."
    conda run -n "$ENV_NAME" pip install torch torchvision
fi

# ── STEP 4: backend requirements ──
section "[STEP 4/8] Backend requirements"
if ! conda run -n "$ENV_NAME" pip install -r "$SCRIPT_DIR/backend/requirements.txt"; then
    log_error "pip install failed."
    exit 1
fi
# Reused environments may still contain the retired database drivers.
conda run -n "$ENV_NAME" python -m pip uninstall -y motor pymongo >/dev/null 2>&1 || true

# ── STEP 5: PostgreSQL environment and service ──
section "[STEP 5/8] PostgreSQL environment and service"
POSTGRES_ENV_FILE="${MEDIAUTO_POSTGRES_ENV_FILE:-$SCRIPT_DIR/.env.postgres}"
POSTGRES_EXISTING_MODE=""
if [[ -f "$POSTGRES_ENV_FILE" ]]; then
    POSTGRES_EXISTING_MODE=$(awk -F= '$1 == "POSTGRES_DEPLOYMENT" {print tolower($2); exit}' "$POSTGRES_ENV_FILE")
fi
POSTGRES_MODE="${MEDIAUTO_POSTGRES_MODE:-${POSTGRES_EXISTING_MODE:-docker}}"
if [[ "${MEDIAUTO_POSTGRES_EXTERNAL:-0}" == "1" || ( ! -f "$POSTGRES_ENV_FILE" && -n "${POSTGRES_URI:-}" ) ]]; then
    POSTGRES_MODE="external"
fi
if ! conda run -n "$ENV_NAME" python \
    "$SCRIPT_DIR/backend/scripts/configure_postgres_env.py" \
    --env-file "$POSTGRES_ENV_FILE" --mode "$POSTGRES_MODE"; then
    log_error "PostgreSQL environment setup failed."
    exit 1
fi
set -a
# shellcheck disable=SC1090
source "$POSTGRES_ENV_FILE"
set +a

if [[ "${POSTGRES_DEPLOYMENT:-docker}" == "docker" ]]; then
    if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
        log_error "Docker Engine with the Compose plugin is required for the default PostgreSQL deployment."
        echo "        Install Docker, or set POSTGRES_URI and MEDIAUTO_POSTGRES_EXTERNAL=1."
        exit 1
    fi
    if ! docker info >/dev/null 2>&1; then
        log_error "Docker is installed but this user cannot access the daemon."
        echo "        Re-login after joining the docker group, then rerun install.sh."
        exit 1
    fi
    if ! docker compose --env-file "$POSTGRES_ENV_FILE" \
        -f "$SCRIPT_DIR/compose.postgres.yml" up -d; then
        log_error "PostgreSQL container startup failed."
        exit 1
    fi
    POSTGRES_CONTAINER_ID=$(docker compose --env-file "$POSTGRES_ENV_FILE" \
        -f "$SCRIPT_DIR/compose.postgres.yml" ps -q postgres)
    POSTGRES_HEALTH=""
    for _ in $(seq 1 60); do
        POSTGRES_HEALTH=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
            "$POSTGRES_CONTAINER_ID" 2>/dev/null || true)
        [[ "$POSTGRES_HEALTH" == "healthy" ]] && break
        sleep 1
    done
    if [[ "$POSTGRES_HEALTH" != "healthy" ]]; then
        log_error "PostgreSQL container did not become healthy (status: ${POSTGRES_HEALTH:-unknown})."
        exit 1
    fi
    log_ok "Persistent PostgreSQL container is healthy on 127.0.0.1:${POSTGRES_PORT:-5432}."
elif [[ "${POSTGRES_DEPLOYMENT}" == "native" ]]; then
    if [[ "$(uname -s)" != "Linux" ]] || ! command -v systemctl >/dev/null 2>&1; then
        log_error "Native PostgreSQL installation currently requires Linux with user systemd."
        exit 1
    fi
    if conda env list | awk '{print $1}' | grep -Fxq "$POSTGRES_ENV_NAME"; then
        log_info "Native PostgreSQL env '$POSTGRES_ENV_NAME' already exists."
    else
        log_info "Installing native PostgreSQL 18 in Conda env '$POSTGRES_ENV_NAME'."
        if ! conda create -y -n "$POSTGRES_ENV_NAME" -c conda-forge "postgresql=18"; then
            log_error "Native PostgreSQL package installation failed."
            exit 1
        fi
    fi
    POSTGRES_CONDA_PREFIX=$(conda env list | awk -v name="$POSTGRES_ENV_NAME" '$1 == name {print $NF; exit}')
    if [[ -z "$POSTGRES_CONDA_PREFIX" || ! -x "$POSTGRES_CONDA_PREFIX/bin/postgres" ]]; then
        log_error "Could not locate native PostgreSQL binaries for '$POSTGRES_ENV_NAME'."
        exit 1
    fi
    if ! conda run -n "$ENV_NAME" python \
        "$SCRIPT_DIR/backend/scripts/manage_native_postgres.py" \
        --bin-dir "$POSTGRES_CONDA_PREFIX/bin" \
        --data-dir "$POSTGRES_DATA_DIR" \
        --unit-file "$POSTGRES_UNIT_FILE" \
        --port "$POSTGRES_PORT" \
        --user "$POSTGRES_USER" \
        --database "$POSTGRES_DB"; then
        log_error "Native PostgreSQL initialization failed."
        exit 1
    fi
    loginctl enable-linger "$(id -un)" >/dev/null 2>&1 || \
        log_warn "Could not enable user lingering; native PostgreSQL may stop after logout."
    log_ok "Native PostgreSQL service is enabled: mediauto-postgresql.service"
else
    log_info "External PostgreSQL deployment selected; Docker startup skipped."
fi

# ── STEP 6: optional Philips SDK environment ──
section "[STEP 6/8] Optional Philips iSyntax environment"
if [[ "${MEDIAUTO_ENABLE_PHILIPS:-0}" == "1" || -n "${MEDIAUTO_PHILIPS_SDK_SOURCE:-}" ]]; then
    if [[ "${MEDIAUTO_ACCEPT_PHILIPS_EULA:-0}" != "1" ]]; then
        log_error "Review the licensed Philips SDK EULA, then set MEDIAUTO_ACCEPT_PHILIPS_EULA=1."
        exit 1
    fi
    if conda env list | awk '{print $1}' | grep -Fxq "$PHILIPS_ENV_NAME"; then
        log_info "Philips env '$PHILIPS_ENV_NAME' already exists."
    else
        log_info "Creating Philips env: $PHILIPS_ENV_NAME (python $PHILIPS_PY_VER)"
        if ! conda create -y -n "$PHILIPS_ENV_NAME" python="$PHILIPS_PY_VER" pip; then
            log_error "Failed to create Philips SDK environment."
            exit 1
        fi
    fi
    if ! conda run -n "$PHILIPS_ENV_NAME" python \
        "$SCRIPT_DIR/backend/scripts/bootstrap_philips.py"; then
        log_error "Philips SDK environment setup failed."
        exit 1
    fi
else
    log_info "Philips setup skipped. Set MEDIAUTO_ENABLE_PHILIPS=1 and MEDIAUTO_PHILIPS_SDK_SOURCE to enable it."
fi

# ── STEP 7: connectivity test ──
section "[STEP 7/8] PostgreSQL connectivity and schema"
if ! conda run -n "$ENV_NAME" python \
    "$SCRIPT_DIR/backend/scripts/configure_postgres_env.py" \
    --env-file "$POSTGRES_ENV_FILE" --mode "$POSTGRES_MODE" --check-connection; then
    log_error "PostgreSQL connectivity failed. Check POSTGRES_URI and the database service."
    exit 1
fi

if ! (cd "$SCRIPT_DIR/backend" && conda run -n "$ENV_NAME" python -m alembic upgrade head); then
    log_error "PostgreSQL schema migration failed."
    exit 1
fi

# ── STEP 8: runtime bootstrap ──
section "[STEP 8/8] Runtime bootstrap and preflight"
BOOTSTRAP_ARGS=()
if [[ "${MEDIAUTO_STRICT_MODELS:-0}" == "1" ]]; then
    BOOTSTRAP_ARGS+=(--strict-models)
fi
if [[ "${MEDIAUTO_STRICT_DB:-0}" == "1" ]]; then
    BOOTSTRAP_ARGS+=(--strict-db)
fi
if ! conda run -n "$ENV_NAME" python "$SCRIPT_DIR/backend/scripts/bootstrap_runtime.py" "${BOOTSTRAP_ARGS[@]}"; then
    log_error "Runtime bootstrap failed. Resolve the errors above and rerun install.sh."
    exit 1
fi

# ── Done ──
echo
echo "${C_BOLD}============================================================${C_RESET}"
echo "${C_GREEN}[DONE]${C_RESET} Install complete."
echo
echo " Run ./start.sh to launch the SaaS server."
echo " Conda env: $ENV_NAME (override with MEDIAUTO_CONDA_ENV)"
echo " Model bundle: set MEDIAUTO_MODEL_SOURCE=/path/to/models-or-archive before install."
echo
echo " NOTE (Migration to another machine):"
echo "   Copy these from the original install:"
echo "     - backend/.secrets.json   (password pepper, AES key — CRITICAL)"
echo "     - backend/uploads/        (WSI files, tile cache)"
echo "     - backend/model/          (AI weights)"
echo "     - PostgreSQL backup       (all application database data)"
echo "   Losing .secrets.json breaks all existing user passwords."
echo
echo " PostgreSQL runtime:"
echo "   Environment = $POSTGRES_ENV_FILE"
echo "   Backend     = postgresql"
echo "   Deployment  = ${POSTGRES_DEPLOYMENT:-docker}"
if [[ "${POSTGRES_DEPLOYMENT:-}" == "native" ]]; then
    echo "   Data dir    = $POSTGRES_DATA_DIR"
    echo "   Service     = mediauto-postgresql.service"
fi
echo "${C_BOLD}============================================================${C_RESET}"
