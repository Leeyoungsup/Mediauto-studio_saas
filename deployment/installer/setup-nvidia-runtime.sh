#!/usr/bin/env bash
set -euo pipefail
if [[ $EUID -ne 0 ]]; then exec sudo bash "$0" "$@"; fi
source /etc/os-release
case "$ID" in ubuntu|debian) ;; *) echo 'Ubuntu/Debian is required.'; exit 1;; esac

# Undo only this installer's duplicate NVIDIA entry, preserving a backup.
existing=/etc/apt/sources.list.d/nvidia-container-toolkit.list
added=/etc/apt/sources.list.d/mediauto-nvidia.list
if [[ -f "$existing" && -f "$added" ]] && grep -qE '^deb .*https://nvidia.github.io/libnvidia-container/stable/deb/' "$existing"; then
  mv "$added" "$added.disabled-$(date +%s)"
  echo 'Disabled duplicate MeDIAuto NVIDIA source; keeping the existing toolkit source.'
fi
# The Ubuntu add-apt-repository entry duplicates the signed Docker entry on this host.
legacy=/etc/apt/sources.list.d/archive_uri-https_download_docker_com_linux_ubuntu-jammy.list
canonical=/etc/apt/sources.list.d/docker.list
if [[ -f "$legacy" && -f "$canonical" ]] && [[ $(grep -cE '^deb ' "$legacy") == 1 ]] &&
   grep -qE '^deb .*https://download.docker.com/linux/ubuntu +jammy +stable *$' "$legacy" &&
   grep -qE '^deb .*https://download.docker.com/linux/ubuntu +jammy +stable *$' "$canonical"; then
  mv "$legacy" "$legacy.disabled-$(date +%s)"
  echo 'Disabled duplicate Docker source; keeping docker.list.'
fi
if [[ "${1:-}" == --prepare-repositories ]]; then exit 0; fi

nvidia-smi -L
command -v docker >/dev/null || { echo 'Install Docker Engine first.'; exit 1; }
apt-get update
apt-get install -y ca-certificates curl gnupg
# Existing repository entries own their Signed-By path. Do not add a second one.
if ! grep -Eq '^[[:space:]]*(deb .*|URIs: *)https://nvidia.github.io/libnvidia-container/' /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources /etc/apt/sources.list 2>/dev/null; then
  key_file=$(mktemp)
  trap 'rm -f "$key_file"' EXIT
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey -o "$key_file"
  gpg --batch --yes --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg "$key_file"
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' > /etc/apt/sources.list.d/nvidia-container-toolkit.list
fi
apt-get update
apt-get install -y nvidia-container-toolkit
nvidia-ctk runtime configure --runtime=docker
systemctl restart docker
echo 'NVIDIA Container Toolkit configured. Docker has been restarted.'
