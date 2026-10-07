#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
echo 'MeDIAuto GPU installation'
echo 'REQUIRED: Internet for installation/updates, sudo, x86-64 Ubuntu/Debian with systemd.'
echo 'NVIDIA GPU + Linux driver >= 570.26 (CUDA 12.8). Separate model folder required.'
echo 'No CPU fallback. Driver setup may require a manual reboot and rerun.'
echo '1. Docker GPU environment from GitHub + host PostgreSQL (recommended)'
echo '2. Native GPU environment from GitHub + host PostgreSQL'
read -r -p 'Choose installation method [1]: ' choice
case "${choice:-1}" in
 1) exec bash docker/install.sh "$@";;
 2) exec bash native/install.sh "$@";;
 *) echo 'Enter 1 or 2.'; exit 1;;
esac
