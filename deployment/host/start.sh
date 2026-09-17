#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
if [[ $EUID -ne 0 ]]; then exec sudo bash "$PWD/start.sh"; fi
exec python3 install.py --action start
