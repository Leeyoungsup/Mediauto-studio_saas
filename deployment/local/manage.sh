#!/usr/bin/env bash
set -euo pipefail
bundle_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$bundle_dir"
action="${1:-setup}"
mode="${2:-cpu}"
case "$action" in setup|start|stop|logs|status) ;; *) echo 'Usage: bash deployment/local/manage.sh setup [cpu|gpu] | start | stop | logs | status'; exit 2;; esac
command -v docker >/dev/null || { echo 'Install Docker Engine and Docker Compose first.'; exit 1; }
docker compose version >/dev/null
docker info >/dev/null
if [[ "$action" == setup ]]; then
  [[ "$mode" == cpu || "$mode" == gpu ]] || { echo 'Device must be cpu or gpu'; exit 2; }
  docker run --rm --user "$(id -u):$(id -g)" --mount "type=bind,source=$bundle_dir,target=/bundle" -w /bundle python:3.10-slim-bookworm python deployment/local/configure.py --mode "$mode"
fi
[[ -f .deploy.env ]] || { echo 'Run setup first.'; exit 1; }
compose=(docker compose --env-file "$bundle_dir/.deploy.env" -f "$bundle_dir/deployment/local/compose.yml")
if grep -q '^MEDIAUTO_DEVICE=gpu$' .deploy.env; then compose+=(-f "$bundle_dir/deployment/local/compose.gpu.yml"); fi
case "$action" in
 setup) "${compose[@]}" up -d --build --wait --wait-timeout 900; echo 'Ready: http://localhost:8092 — initial login is in ADMIN_LOGIN.txt';;
 start) "${compose[@]}" up -d --wait --wait-timeout 900;;
 stop) "${compose[@]}" stop;;
 logs) "${compose[@]}" logs --tail 100 -f app;;
 status) "${compose[@]}" ps;;
esac
