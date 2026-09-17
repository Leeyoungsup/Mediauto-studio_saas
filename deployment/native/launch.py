"""Run the app in this terminal; Ctrl+C stops it. No scheduler or background task."""
import json
import os
from pathlib import Path
import sys

root=Path(__file__).resolve().parent
locator=root/'.install-location.json'
if not locator.is_file():
    raise SystemExit('Run install first; installation settings were not found.')
runtime=Path(json.loads(locator.read_text(encoding='utf-8'))['data_root'])/'config'
if not (runtime/'app.json').is_file():
    raise SystemExit('Application environment is incomplete; run install first.')
settings=json.loads((runtime/'app.json').read_text(encoding='utf-8'))
command=settings['command']
os.execv(command[0],command+[str(root/'runner.py'),str(runtime/'app.json'),'--console'])
