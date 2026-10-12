from pathlib import Path
import runpy
globals().update(runpy.run_path(str(Path(__file__).resolve().parents[1]/'native/existing_database.py')))
