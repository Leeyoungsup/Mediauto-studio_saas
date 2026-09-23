#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
echo 'MeDIAuto GPU installation'
echo '1. Docker GPU environment from GitHub + host PostgreSQL (recommended)'
echo '2. Native GPU environment from GitHub + host PostgreSQL'
read -r -p 'Choose installation method [1]: ' choice
case "${choice:-1}" in
 1) exec bash docker/install.sh "$@";;
 2) exec bash native/install.sh "$@";;
 *) echo 'Enter 1 or 2.'; exit 1;;
esac
