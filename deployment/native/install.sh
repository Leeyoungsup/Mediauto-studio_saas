#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
if [[ $EUID -ne 0 ]]; then exec sudo bash "$PWD/install.sh" "$@"; fi
[[ "$(uname -m)" == x86_64 ]] || { echo 'x86-64 required.'; exit 1; }
source /etc/os-release
case "$ID" in ubuntu|debian) ;; *) echo 'Automatic installation supports Ubuntu/Debian.'; exit 1;; esac
[[ -d /run/systemd/system ]] || { echo 'systemd required.'; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update
vips_package=libvips42
if apt-cache show libvips42t64 >/dev/null 2>&1; then vips_package=libvips42t64; fi
apt-get install -y ca-certificates python3 python3-venv python3-dev build-essential postgresql acl libopenslide0 "$vips_package" libgomp1 libegl1 libgles2
python3 install.py "$@"
