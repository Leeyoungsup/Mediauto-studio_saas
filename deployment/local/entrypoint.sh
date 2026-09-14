#!/usr/bin/env bash
set -euo pipefail
mkdir -p /data/cell_annotation
python -m alembic upgrade head
python scripts/bootstrap_runtime.py --strict-models --strict-db
exec python -m uvicorn main:app --host 0.0.0.0 --port 8092
