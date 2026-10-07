#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
if [[ $EUID -ne 0 ]]; then
  # Preserve a nonstandard Conda location when sudo resets PATH.
  mediauto_conda="${CONDA_EXE:-}"
  if [[ -z "$mediauto_conda" ]]; then mediauto_conda=$(command -v conda || true); fi
  exec sudo env "CONDA_EXE=$mediauto_conda" bash "$PWD/install.sh" "$@"
fi
if [[ "$(uname -m)" != x86_64 ]]; then echo 'This release requires x86-64.'; exit 1; fi
source /etc/os-release
case "$ID" in ubuntu|debian) ;; *) echo 'Automatic Linux installation supports Ubuntu/Debian with systemd.'; exit 1;; esac
[[ -d /run/systemd/system ]] || { echo 'A systemd host is required.'; exit 1; }
bash "$PWD/setup-nvidia-runtime.sh" --prepare-repositories
bash "$PWD/setup-nvidia-driver.sh"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y git ca-certificates curl gnupg python3 python3-venv python3-dev build-essential postgresql acl libopenslide0 libgomp1 libegl1 libgles2
vips_package=libvips42
if apt-cache show libvips42t64 >/dev/null 2>&1; then vips_package=libvips42t64; fi
apt-get install -y "$vips_package"
# Preserve an existing Docker installation; do not remove packages or change daemon configuration.
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/$ID/gpg" -o /etc/apt/keyrings/mediauto-docker.asc
  chmod a+r /etc/apt/keyrings/mediauto-docker.asc
  echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/mediauto-docker.asc] https://download.docker.com/linux/$ID $VERSION_CODENAME stable" > /etc/apt/sources.list.d/mediauto-docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker
nvidia-smi -L || { echo 'Install/fix the NVIDIA host driver first. CPU fallback is disabled.'; exit 1; }
if ! docker info --format '{{json .Runtimes}}' | grep -q nvidia; then
  bash "$PWD/setup-nvidia-runtime.sh"
fi
if [[ "${1:-}" == --prepare-only ]]; then exit 0; fi
# Ubuntu 20.04's system Python 3.8 can run this bootstrap. The application
# installer itself is re-executed with a verified, isolated Conda Python.
exec /usr/bin/python3 "$PWD/bootstrap_python.py" "$PWD/install.py" "$@"
