#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
if [[ $EUID -ne 0 ]]; then exec sudo bash "$PWD/install.sh" "$@"; fi
if [[ "$(uname -m)" != x86_64 ]]; then echo 'This release requires x86-64.'; exit 1; fi
source /etc/os-release
case "$ID" in ubuntu|debian) ;; *) echo 'Automatic Linux installation supports Ubuntu/Debian with systemd.'; exit 1;; esac
[[ -d /run/systemd/system ]] || { echo 'A systemd host is required.'; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl python3 postgresql acl
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
python3 install.py "$@"
