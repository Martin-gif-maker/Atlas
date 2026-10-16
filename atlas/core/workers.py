"""Run slow work (AI requests, reading files) off the main thread so the window never freezes.

    run(fn, arg1, arg2, on_done=show_result, on_error=show_error)

`fn` runs in a background thread; `on_done(result)` or `on_error(message)` is then called back on the
main (window) thread.
"""
from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, Qt, Signal, Slot

log = logging.getLogger(__name__)
_running: set["_Job"] = set()


class _Job(QObject):
    _finished = Signal(object, object)          # (result, error message or None)

    def __init__(self, on_done, on_error):
        super().__init__()
        self._on_done, self._on_error = on_done, on_error
        # The job object lives on the main thread, so a queued connection delivers there.
        self._finished.connect(self._deliver, Qt.ConnectionType.QueuedConnection)

    @Slot(object, object)
    def _deliver(self, result, error):
        _running.discard(self)
        try:
            if error is None:
                if self._on_done:
                    self._on_done(result)
            elif self._on_error:
                self._on_error(error)
        except Exception:                        # a broken callback must not take the app down
            log.exception("callback failed")


def run(fn, *args, on_done=None, on_error=None, **kwargs) -> None:
    job = _Job(on_done, on_error)
    _running.add(job)

    def work():
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            log.warning("background job failed: %s", exc)
            job._finished.emit(None, str(exc) or exc.__class__.__name__)
        else:
            job._finished.emit(result, None)

    threading.Thread(target=work, daemon=True).start()


def busy() -> bool:
    """True while any background job has not reported back yet (used by the tests)."""
    return bool(_running)
