"""Starting the app: logging, the Qt application, the look, and the main window."""
from __future__ import annotations

import importlib
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from . import APP_NAME, appicon, storage, theme


def setup_logging() -> None:
    handlers = [logging.StreamHandler()]
    try:
        handlers.append(RotatingFileHandler(storage.data_dir() / f"{APP_NAME.lower()}.log",
                                            maxBytes=500_000, backupCount=1, encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    for noisy in ("httpx", "httpcore", "groq"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def make_app(argv=None):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    package = importlib.import_module(__package__.rsplit(".", 1)[0])
    app.setWindowIcon(appicon.icon(getattr(package, "ICON", "")))    # also the Dock icon on macOS
    theme.apply(app)
    return app


def run(window_class) -> int:
    setup_logging()
    app = make_app()
    window = window_class()
    window.show()
    quit_after = os.environ.get(f"{APP_NAME.upper()}_QUIT_AFTER_MS")   # used by test launches
    if quit_after:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(int(quit_after), app.quit)
    return app.exec()
