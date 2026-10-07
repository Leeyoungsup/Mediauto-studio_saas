#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
if [[ $EUID -ne 0 ]]; then
  # Preserve a nonstandard Conda location when sudo resets PATH.
  mediauto_conda="${CONDA_EXE:-}"
  if [[ -z "$mediauto_conda" ]]; then mediauto_conda=$(command -v conda || true); fi
  exec sudo env "CONDA_EXE=$mediauto_conda" bash "$PWD/install.sh" "$@"
fi
[[ "$(uname -m)" == x86_64 ]] || { echo 'x86-64 required.'; exit 1; }
source /etc/os-release
case "$ID" in ubuntu|debian) ;; *) echo 'Automatic installation supports Ubuntu/Debian.'; exit 1;; esac
[[ -d /run/systemd/system ]] || { echo 'systemd required.'; exit 1; }
bash "$PWD/setup-nvidia-driver.sh"
export DEBIAN_FRONTEND=noninteractive
apt-get update
vips_package=libvips42
if apt-cache show libvips42t64 >/dev/null 2>&1; then vips_package=libvips42t64; fi
apt-get install -y git ca-certificates python3 python3-venv python3-dev build-essential postgresql acl libopenslide0 "$vips_package" libgomp1 libegl1 libgles2
if [[ "${1:-}" == --prepare-only ]]; then exit 0; fi
# Ubuntu 20.04's system Python 3.8 can run this bootstrap. The application
# installer itself is re-executed with a verified, isolated Conda Python.
exec /usr/bin/python3 "$PWD/bootstrap_python.py" "$PWD/install.py" "$@"
