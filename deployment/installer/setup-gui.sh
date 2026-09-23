#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
if ! /usr/bin/python3 -c 'import tkinter' >/dev/null 2>&1; then
  if ! command -v pkexec >/dev/null; then
    echo 'Install python3-tk and policykit-1, then run setup-gui.sh again.' >&2
    exit 1
  fi
  pkexec /usr/bin/apt-get install -y python3-tk
fi
exec /usr/bin/python3 "$PWD/gui.py"
