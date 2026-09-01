#!/usr/bin/env bash

# ============================================================
#  MeDICus Studio SaaS - Server Start Script
#  - conda env "medicus-saas" activate (via env Python)
#  - uvicorn FastAPI start
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/backend"

# Load the local PostgreSQL cutover configuration when present. The file is
# git-ignored and created with owner-only permissions by the deployment setup.
POSTGRES_ENV_FILE="${MEDIAUTO_POSTGRES_ENV_FILE:-$SCRIPT_DIR/.env.postgres}"
if [[ -f "$POSTGRES_ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$POSTGRES_ENV_FILE"
  set +a
fi

ENV_NAME="${MEDIAUTO_CONDA_ENV:-medicus-saas}"
HOST="${MEDIAUTO_HOST:-0.0.0.0}"
PORT="${MEDIAUTO_PORT:-8092}"
export PHILIPS_CONDA_ENV="${PHILIPS_CONDA_ENV:-philips-sdk-py38}"

if ! command -v conda >/dev/null 2>&1; then
  echo "[ERROR] conda not found. Install Miniconda/Anaconda first."
  exit 1
fi

if ! conda env list | awk '{print $1}' | grep -Fxq "$ENV_NAME"; then
  echo "[ERROR] conda env \"$ENV_NAME\" not found."
  echo "        Run ./install.sh first."
  exit 1
fi

CONDA_BASE="$(conda info --base)"
ENV_PYTHON="${CONDA_BASE}/envs/${ENV_NAME}/bin/python"
if [[ ! -x "$ENV_PYTHON" ]]; then
  echo "[ERROR] python not found in conda env: $ENV_PYTHON"
  exit 1
fi

# Avoid pollution from any active .venv / user site-packages so the conda env
# python doesn't accidentally pick up packages from elsewhere.
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH
export PYTHONNOUSERSITE=1

# Background worker CPU policy. Existing environment values win, so operators
# can still override these per run without editing this file.
export MEDIAUTO_CPU_TILE="${MEDIAUTO_CPU_TILE:-6}"
export MEDIAUTO_TILE_WORKER_IDLE_PARALLELISM="${MEDIAUTO_TILE_WORKER_IDLE_PARALLELISM:-2}"
export MEDIAUTO_TILE_WORKER_BUSY_PARALLELISM="${MEDIAUTO_TILE_WORKER_BUSY_PARALLELISM:-1}"
export TILE_CACHE_QUOTA_BYTES="${TILE_CACHE_QUOTA_BYTES:-1099511627776}"

echo
echo "============================================================"
echo " MeDICus Studio SaaS"
echo " URL: http://localhost:${PORT}"
echo " Press Ctrl+C to stop."
echo "============================================================"
echo
exec "$ENV_PYTHON" -m uvicorn main:app --host "$HOST" --port "$PORT"
