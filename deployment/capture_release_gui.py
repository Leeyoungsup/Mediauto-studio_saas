"""Capture the real installer without running installation or accessing saved settings.

Run with a working Tk/X11 environment. Images are Linux captures of the shared GUI,
not Windows desktop captures. The SDK dialog is closed without accepting its license.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'deployment/installer'))
import gui

assets = ROOT / 'deployment/release-guide/assets'
assets.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='mediauto-guide-ui-') as directory:
    isolated = Path(directory)
    (isolated / 'Philips_SDK').symlink_to(ROOT / 'backend/Philips_SDK', target_is_directory=True)
    gui.ROOT = isolated
    app = gui.Installer()
    app.geometry('1080x1120+10+10')
    app.vars['model_path'].set('/mnt/models')
    app.update()

    def capture(window, name):
        window.update()
        box = (window.winfo_rootx(), window.winfo_rooty(),
               window.winfo_rootx()+window.winfo_width(), window.winfo_rooty()+window.winfo_height())
        code = 'from PIL import ImageGrab; ImageGrab.grab(bbox='+repr(box)+').save('+repr(str(assets/name))+')'
        subprocess.run([os.environ.get('SCREENSHOT_PYTHON', sys.executable), '-c', code], check=True)

    capture(app, 'installer-linux.png')
    def license_capture():
        window = [w for w in app.winfo_children() if isinstance(w, gui.tk.Toplevel)][-1]
        window.geometry('940x680+50+50')
        capture(window, 'sdk-license-linux.png')
        window.destroy()
    app.after(300, license_capture)
    app.license(accept=True)
    app.destroy()
(assets/'capture-provenance.json').write_text(json.dumps({
    'platform': 'Linux X11 (virtual display)',
    'source': 'deployment/installer/gui.py',
    'installation_started': False, 'license_accepted': False,
    'windows_native_capture': False,
    'notes': 'Actual shared Tk GUI. Linux paths and driver floor are shown; Windows uses its own defaults.'
}, indent=2)+'\n')
print('Captured actual shared GUI and SDK license dialog; no installation performed.')
