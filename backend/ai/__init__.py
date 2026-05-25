"""
AI Module — SaaS Backend

text text ai/ text PyQt5 (QObject/QThread/pyqtSignal) text text
text SaaS text PyQt5 text text text.
import text PyQt5 text no-op text sys.modules text text text text.

text(app/routers/ai.py)text text/text text import text text __init__.py
text sub-module text eager-import text text.
"""

import sys
import types


def _install_pyqt5_stub() -> None:
    if 'PyQt5.QtCore' in sys.modules:
        return

    class _Signal:
        def __init__(self, *_a, **_kw):
            pass

        def __get__(self, _obj, _objtype=None):
            return self

        def emit(self, *_a, **_kw):
            pass

        def connect(self, *_a, **_kw):
            pass

        def disconnect(self, *_a, **_kw):
            pass

    class _QObject:
        def __init__(self, *_a, **_kw):
            pass

    class _QThread(_QObject):
        def __init__(self, *_a, **_kw):
            super().__init__()
            self._is_running = False

        def start(self, *_a, **_kw):
            self._is_running = True
            run = getattr(self, 'run', None)
            if run is not None:
                try:
                    run()
                finally:
                    self._is_running = False

        def quit(self):
            self._is_running = False

        def wait(self, *_a, **_kw):
            pass

        def isRunning(self):
            return self._is_running

        def terminate(self):
            self._is_running = False

        def msleep(self, *_a, **_kw):
            pass

        def requestInterruption(self):
            self._is_running = False

        def isInterruptionRequested(self):
            return False

    pyqt5 = types.ModuleType('PyQt5')
    qtcore = types.ModuleType('PyQt5.QtCore')
    qtgui = types.ModuleType('PyQt5.QtGui')
    qtwidgets = types.ModuleType('PyQt5.QtWidgets')

    qtcore.QObject = _QObject
    qtcore.QThread = _QThread
    qtcore.pyqtSignal = lambda *_a, **_kw: _Signal()
    qtcore.pyqtSlot = lambda *_a, **_kw: (lambda fn: fn)
    qtcore.Qt = types.SimpleNamespace(
        AlignCenter=0, AlignLeft=0, AlignRight=0,
        KeepAspectRatio=0, SmoothTransformation=0,
    )
    qtcore.QTimer = type('QTimer', (_QObject,), {})
    qtcore.QMutex = type('QMutex', (), {'lock': lambda self: None, 'unlock': lambda self: None})

    _stub_cls = lambda name: type(name, (), {'__init__': lambda self, *a, **kw: None})
    qtgui.QImage = _stub_cls('QImage')
    qtgui.QPixmap = _stub_cls('QPixmap')
    qtgui.QPainter = _stub_cls('QPainter')
    qtgui.QColor = _stub_cls('QColor')
    qtgui.QPen = _stub_cls('QPen')
    qtgui.QBrush = _stub_cls('QBrush')

    qtwidgets.QApplication = _stub_cls('QApplication')

    pyqt5.QtCore = qtcore
    pyqt5.QtGui = qtgui
    pyqt5.QtWidgets = qtwidgets

    sys.modules['PyQt5'] = pyqt5
    sys.modules['PyQt5.QtCore'] = qtcore
    sys.modules['PyQt5.QtGui'] = qtgui
    sys.modules['PyQt5.QtWidgets'] = qtwidgets


_install_pyqt5_stub()
