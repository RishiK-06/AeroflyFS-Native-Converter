"""Offscreen GUI smoke test: builds the main window without a display."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication

import ttx_gui


def main() -> int:
    app = QApplication(sys.argv)
    w = ttx_gui.MainWindow()
    assert w.windowTitle() == "Aerofly FS Converter", w.windowTitle()
    assert w._fmt_combo is not None and w._mode_combo is not None
    assert w._convert_btn is not None and w._flip_cb is not None
    w.close()
    app.quit()
    print("GUI SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())