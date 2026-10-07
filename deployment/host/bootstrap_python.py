"""Development-tree entry point; packaged installers receive the shared source."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).resolve().parents[1]/'native/bootstrap_python.py'), run_name='__main__')
