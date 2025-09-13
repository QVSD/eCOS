# main.py
import sys, os, atexit
from pathlib import Path
from PySide6 import QtWidgets, QtCore
from app.ui.main_window import MainWindow

LOCKFILE = Path(".app.lock")

def _cleanup_lock():
    try:
        LOCKFILE.unlink(missing_ok=True)
    except Exception:
        pass

if LOCKFILE.exists():
    print("Aplicația rulează deja.")
    sys.exit(1)
LOCKFILE.write_text(str(os.getpid()))
atexit.register(_cleanup_lock)

if __name__ == "__main__":
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    ret = app.exec()
    _cleanup_lock()
    sys.exit(ret)
