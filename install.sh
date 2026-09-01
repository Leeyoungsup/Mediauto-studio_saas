#!/usr/bin/env bash
# ============================================================
#  MeDIAuto Studio SaaS - Dependency Install Script (Linux)
#  - Detect distro
#  - Verify/install residual MongoDB + configure PostgreSQL
#  - Create/update conda env
#  - Install PyTorch with CUDA
#  - Install backend/requirements.txt
#  - Apply PostgreSQL schema and migrate legacy operational data when empty
#  - Optional: restore mongo_dump if present (migration)
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

install_mongodb_ubuntu_7() {
    local codename="${VERSION_CODENAME:-${UBUNTU_CODENAME:-}}"
    if [[ "$codename" != "jammy" && "$codename" != "focal" ]]; then
        log_error "MongoDB 7 apt automation supports Ubuntu 22.04 (jammy) and 20.04 (focal); found '$codename'."
        return 1
    fi
    log_info "Installing MongoDB 7 Community from the official MongoDB repository (sudo required) ..."
    sudo apt-get update || return 1
    sudo apt-get install -y gnupg curl || return 1
    curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | \
        sudo gpg --batch --yes -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor || return 1
    echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg] https://repo.mongodb.org/apt/ubuntu ${codename}/mongodb-org/7.0 multiverse" | \
        sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list >/dev/null || return 1
    sudo apt-get update || return 1
    sudo apt-get install -y mongodb-org || return 1
}

# ── Pre-checks ──
if ! command -v conda >/dev/null 2>&1; then
    log_error "conda not found. Install Miniconda/Anaconda first:"
    echo "         https://docs.conda.io/en/latest/miniconda.html"
    exit 1
fi

# ── STEP 1: MongoDB ──
section "[STEP 1/11] Residual MongoDB setup"
if command -v mongod >/dev/null 2>&1; then
    log_info "mongod found: $(command -v mongod)"
else
    log_warn "mongod not found in PATH."
    MONGO_URI_CHECK="${MONGO_URI:-mongodb://localhost:27017}"
    if [[ "$MONGO_URI_CHECK" != *"localhost"* && "$MONGO_URI_CHECK" != *"127.0.0.1"* && "$MONGO_URI_CHECK" != *"[::1]"* ]]; then
        log_info "Remote MONGO_URI is configured; local MongoDB installation is skipped."
    elif [[ "$DISTRO_ID" == "ubuntu" ]] && { [[ "${MEDIAUTO_AUTO_INSTALL_DB:-0}" == "1" ]] || confirm "Install MongoDB 7 Community automatically now"; }; then
        if ! install_mongodb_ubuntu_7; then
            log_error "MongoDB automatic installation failed."
            exit 1
        fi
        log_ok "MongoDB installed."
    else
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
section "[STEP 2/11] OpenSlide and libvips system libraries"
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

# ── STEP 3: Conda env ──
section "[STEP 3/11] Conda environment \"$ENV_NAME\""
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
section "[STEP 4/11] PyTorch (CUDA $CUDA_TAG)"
conda run -n "$ENV_NAME" pip install --upgrade pip
if ! conda run -n "$ENV_NAME" pip install torch torchvision \
        --index-url "https://download.pytorch.org/whl/$CUDA_TAG"; then
    log_warn "CUDA build failed. Falling back to CPU-only PyTorch ..."
    conda run -n "$ENV_NAME" pip install torch torchvision
fi

# ── STEP 5: backend requirements ──
section "[STEP 5/11] Backend requirements"
if ! conda run -n "$ENV_NAME" pip install -r "$SCRIPT_DIR/backend/requirements.txt"; then
    log_error "pip install failed."
    exit 1
fi

# ── STEP 6: PostgreSQL environment and service ──
section "[STEP 6/11] PostgreSQL environment and service"
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

# ── STEP 7: optional Philips SDK environment ──
section "[STEP 7/11] Optional Philips iSyntax environment"
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

# ── STEP 8: connectivity test ──
section "[STEP 8/11] MongoDB and PostgreSQL connectivity"
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

if ! conda run -n "$ENV_NAME" python \
    "$SCRIPT_DIR/backend/scripts/configure_postgres_env.py" \
    --env-file "$POSTGRES_ENV_FILE" --mode "$POSTGRES_MODE" --check-connection; then
    log_error "PostgreSQL connectivity failed. Check POSTGRES_URI and the database service."
    exit 1
fi

# ── STEP 9: optional dump restore (migration) ──
section "[STEP 9/11] Optional: restore MongoDB dump"
DUMP_DB_NAME="${MONGO_DB_NAME:-medicus_studio}"
DUMP_FOLDER="$SCRIPT_DIR/mongo_dump/$DUMP_DB_NAME"
DUMP_ARCHIVE_GZ="$SCRIPT_DIR/mongo_dump.archive.gz"
DUMP_ARCHIVE="$SCRIPT_DIR/mongo_dump.archive"
DUMP_TYPE=""
DUMP_PATH=""
if [[ -d "$DUMP_FOLDER" ]]; then
    DUMP_TYPE="folder"; DUMP_PATH="$DUMP_FOLDER"
elif [[ -f "$DUMP_ARCHIVE_GZ" ]]; then
    DUMP_TYPE="archive_gz"; DUMP_PATH="$DUMP_ARCHIVE_GZ"
elif [[ -f "$DUMP_ARCHIVE" ]]; then
    DUMP_TYPE="archive"; DUMP_PATH="$DUMP_ARCHIVE"
fi

if [[ -n "$DUMP_PATH" && ! -f "$SCRIPT_DIR/backend/.secrets.json" ]]; then
    if [[ -z "${JWT_SECRET_KEY:-}" || -z "${FIELD_ENCRYPTION_KEY:-}" || -z "${AUTH_PEPPER:-}" ]]; then
        log_error "A MongoDB dump was found, but its matching application secrets are missing."
        echo "        Restore backend/.secrets.json from the source server, or export"
        echo "        JWT_SECRET_KEY, FIELD_ENCRYPTION_KEY, and AUTH_PEPPER before retrying."
        echo "        Continuing with new keys would break existing passwords/MFA data."
        exit 1
    fi
fi

if [[ -z "$DUMP_PATH" ]]; then
    log_info "No dump found at expected locations — skipping restore."
    echo "        Looked for:"
    echo "          $DUMP_FOLDER/         (mongodump --out=./mongo_dump)"
    echo "          $DUMP_ARCHIVE_GZ      (mongodump --archive=... --gzip)"
    echo "          $DUMP_ARCHIVE         (mongodump --archive=...)"
elif ! command -v mongorestore >/dev/null 2>&1; then
    log_warn "Found dump at $DUMP_PATH but mongorestore is not installed."
    echo "        Install MongoDB Database Tools:"
    if is_debian_family; then
        echo "          sudo apt install -y mongodb-database-tools"
    elif is_rhel_family; then
        echo "          sudo dnf install -y mongodb-database-tools"
    elif is_arch_family; then
        echo "          yay -S mongodb-tools-bin"
    else
        echo "          https://www.mongodb.com/try/download/database-tools"
    fi
    echo "        Then re-run this script, or restore manually."
else
    # 대상 DB 에 컬렉션이 이미 있는지 확인 — --drop 은 파괴적이라 명시적 확인 필요.
    EXISTING_COLLECTIONS=$(conda run -n "$ENV_NAME" python - <<PYEOF 2>/dev/null || echo "0"
import os
from pymongo import MongoClient
uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
db_name = os.environ.get("MONGO_DB_NAME", "$DUMP_DB_NAME")
try:
    cli = MongoClient(uri, serverSelectionTimeoutMS=3000)
    print(len(cli[db_name].list_collection_names()))
except Exception:
    print(0)
PYEOF
)
    EXISTING_COLLECTIONS="${EXISTING_COLLECTIONS//[!0-9]/}"
    EXISTING_COLLECTIONS="${EXISTING_COLLECTIONS:-0}"

    log_info "Found dump: $DUMP_PATH ($DUMP_TYPE)"
    if [[ "$EXISTING_COLLECTIONS" -gt 0 ]]; then
        log_warn "Target DB '$DUMP_DB_NAME' already has $EXISTING_COLLECTIONS collections."
        echo "        Restoring with --drop will WIPE existing data."
        if ! confirm "Drop existing '$DUMP_DB_NAME' and restore from dump"; then
            log_info "Restore skipped. Existing data preserved."
            DUMP_PATH=""
        fi
    else
        if ! confirm "Restore '$DUMP_DB_NAME' from $DUMP_PATH"; then
            log_info "Restore skipped."
            DUMP_PATH=""
        fi
    fi

    if [[ -n "$DUMP_PATH" ]]; then
        MONGO_URI_USE="${MONGO_URI:-mongodb://localhost:27017}"
        case "$DUMP_TYPE" in
            folder)
                mongorestore --uri="$MONGO_URI_USE" --db="$DUMP_DB_NAME" --drop "$DUMP_PATH"
                ;;
            archive_gz)
                mongorestore --uri="$MONGO_URI_USE" --archive="$DUMP_PATH" --gzip --drop \
                    --nsInclude="$DUMP_DB_NAME.*"
                ;;
            archive)
                mongorestore --uri="$MONGO_URI_USE" --archive="$DUMP_PATH" --drop \
                    --nsInclude="$DUMP_DB_NAME.*"
                ;;
        esac
        if [[ $? -eq 0 ]]; then
            log_ok "Restore complete."
        else
            log_warn "mongorestore exited with non-zero status — check output above."
        fi
    fi
fi

# ── STEP 10: PostgreSQL schema and one-time legacy migration ──
section "[STEP 10/11] PostgreSQL schema and legacy data migration"
if ! (cd "$SCRIPT_DIR/backend" && conda run -n "$ENV_NAME" python -m alembic upgrade head); then
    log_error "PostgreSQL schema migration failed."
    exit 1
fi
if ! conda run -n "$ENV_NAME" python \
    "$SCRIPT_DIR/backend/scripts/migrate_auth_to_postgres.py" --if-empty; then
    log_error "Authentication data migration failed. Existing PostgreSQL data was preserved."
    exit 1
fi
if ! conda run -n "$ENV_NAME" python \
    "$SCRIPT_DIR/backend/scripts/migrate_operational_to_postgres.py" --if-empty; then
    log_error "Operational data migration failed. Existing PostgreSQL data was preserved."
    exit 1
fi

# ── STEP 11: runtime bootstrap ──
section "[STEP 11/11] Runtime bootstrap and preflight"
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
echo "     - MongoDB dump            (remaining project/slide/AI/annotation data)"
echo "     - PostgreSQL backup       (users/sessions/audit/geo/clinical data)"
echo "   Losing .secrets.json breaks all existing user passwords."
echo
echo "   Dump on the OLD machine (any of these formats):"
echo "     mongodump --uri=mongodb://localhost:27017 --db=medicus_studio --out=./mongo_dump"
echo "     mongodump --uri=mongodb://localhost:27017 --db=medicus_studio --archive=./mongo_dump.archive --gzip"
echo
echo "   Then on the NEW machine, drop the dump folder/archive at the project root"
echo "   and re-run this script — STEP 9 will auto-restore."
echo
echo " PostgreSQL runtime:"
echo "   Environment = $POSTGRES_ENV_FILE"
echo "   Backend     = postgresql"
echo "   Deployment  = ${POSTGRES_DEPLOYMENT:-docker}"
if [[ "${POSTGRES_DEPLOYMENT:-}" == "native" ]]; then
    echo "   Data dir    = $POSTGRES_DATA_DIR"
    echo "   Service     = mediauto-postgresql.service"
fi
echo
echo " MongoDB defaults:"
echo "   URI    = mongodb://localhost:27017   (override: export MONGO_URI=...)"
echo "   DB     = medicus_studio              (override: export MONGO_DB_NAME=...)"
echo "${C_BOLD}============================================================${C_RESET}"
