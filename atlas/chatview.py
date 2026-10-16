"""The chat used by Voice, Documents and Interview: messages, a text box, and a microphone button."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QPlainTextEdit, QProgressBar, QSizePolicy, QVBoxLayout,
                               QWidget)

from . import ai, audio
from .core import theme, workers
from .core.widgets import Notice, button, card, clear, icon, label, later, scroll_page


class Message(QWidget):
    def __init__(self, role: str, text: str):
        super().__init__()
        p = theme.palette()
        if role == "user":
            row = QHBoxLayout(self)
            row.setContentsMargins(80, 0, 0, 0)
            bubble = QFrame()
            bubble.setStyleSheet(f"QFrame {{ background: {p['well']}; border-radius: 12px; }}")
            lay = QVBoxLayout(bubble)
            lay.setContentsMargins(14, 9, 14, 9)
            body = label(text, wrap=True, selectable=True)
            natural = max(body.fontMetrics().horizontalAdvance(line) for line in text.splitlines() or [""])
            body.setMinimumWidth(min(natural + 4, 520))
            lay.addWidget(body)
            row.addStretch(1)
            row.addWidget(bubble)
        else:
            col = QVBoxLayout(self)
            col.setContentsMargins(0, 0, 60, 0)
            body = label("", wrap=True, selectable=True)
            body.setTextFormat(Qt.TextFormat.MarkdownText)
            body.setText(text)
            body.setOpenExternalLinks(True)
            body.setStyleSheet("font-size: 14px;")
            col.addWidget(body)
        self.body = body


class Composer(QPlainTextEdit):
    """Return sends, Shift+Return starts a new line."""
    send = Signal()

    def __init__(self, placeholder: str):
        super().__init__()
        self.setPlaceholderText(placeholder)
        self.setFixedHeight(60)
        self.setTabChangesFocus(True)
        self.setStyleSheet("QPlainTextEdit { border: none; background: transparent; }")

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and \
                not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.send.emit()
        else:
            super().keyPressEvent(event)


class ChatView(QWidget):
    """Shows messages and collects what you say or type. Emits `submitted(text)`; the page does the rest."""
    submitted = Signal(str)

    def __init__(self, placeholder: str, empty_text: str = ""):
        super().__init__()
        self.empty_text = empty_text
        self.recorder = audio.Recorder()
        self._thinking = None
        self._empty = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.area, self.col = scroll_page(760)
        self.area.widget().layout().setContentsMargins(32, 6, 32, 12)
        self.col.setSpacing(18)
        outer.addWidget(self.area, 1)

        bottom = QWidget()
        bottom_lay = QHBoxLayout(bottom)
        bottom_lay.setContentsMargins(32, 8, 32, 20)
        box, box_lay = card((10, 8, 10, 8), 6)
        box.setMaximumWidth(760)
        self.listening = QWidget()
        lrow = QHBoxLayout(self.listening)
        lrow.setContentsMargins(4, 4, 4, 0)
        self.listen_text = label("Listening…", "muted")
        self.meter = QProgressBar()
        self.meter.setRange(0, 100)
        self.meter.setTextVisible(False)
        self.meter.setFixedWidth(140)
        lrow.addWidget(self.listen_text)
        lrow.addWidget(self.meter)
        lrow.addStretch(1)
        lrow.addWidget(label("Esc cancels", "small"))
        self.listening.hide()
        box_lay.addWidget(self.listening)
        inner = QHBoxLayout()
        self.composer = Composer(placeholder)
        self.composer.send.connect(self.submit)
        inner.addWidget(self.composer, 1)
        self.mic = button("", icon_name="mic", on_click=self.toggle_mic)
        self.mic.setToolTip("Speak instead of typing")
        self.mic.setFixedWidth(42)
        inner.addWidget(self.mic, 0, Qt.AlignmentFlag.AlignBottom)
        self.send_btn = button("Send", "primary", on_click=self.submit)
        inner.addWidget(self.send_btn, 0, Qt.AlignmentFlag.AlignBottom)
        box_lay.addLayout(inner)
        bottom_lay.addStretch(1)
        bottom_lay.addWidget(box, 100)
        bottom_lay.addStretch(1)
        outer.addWidget(bottom)
        self.tick = QTimer(self)
        self.tick.setInterval(100)
        self.tick.timeout.connect(self._update_meter)
        QShortcut(QKeySequence("Escape"), self, context=Qt.ShortcutContext.WidgetWithChildrenShortcut,
                  activated=lambda: self.recorder.recording and self.stop_mic(cancel=True))

    # -- messages --
    def set_messages(self, messages: list[dict], extra: QWidget | None = None) -> None:
        if extra is not None:
            extra.setParent(None)
        clear(self.col)
        self._thinking = None
        if extra is not None:
            self.col.addWidget(extra)
        self._empty = None
        if not messages and self.empty_text:
            self._empty = label(self.empty_text, "muted", wrap=True)
            self.col.addWidget(self._empty)
        for m in messages:
            self.col.addWidget(Message(m["role"], m["content"]))
        self.col.addStretch(1)
        self.scroll_down()

    def add_message(self, role: str, text: str) -> None:
        self.end_thinking()
        if self._empty is not None:                       # the "ask me anything" line goes once you start
            self._empty.deleteLater()
            self._empty = None
        self.col.insertWidget(self.col.count() - 1, Message(role, text))
        self.scroll_down()

    def thinking(self, text: str) -> None:
        self.end_thinking()
        self._thinking = label(text, "muted")
        self.col.insertWidget(self.col.count() - 1, self._thinking)
        self.set_enabled(False)
        self.scroll_down()

    def end_thinking(self) -> None:
        if self._thinking is not None:
            self._thinking.deleteLater()
            self._thinking = None
        self.set_enabled(True)

    def show_error(self, message: str, retry=None) -> None:
        self.end_thinking()
        note = Notice()
        note.show_error(message)
        self.col.insertWidget(self.col.count() - 1, note)
        if retry:
            again = button("Try again")
            again.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            again.clicked.connect(lambda: (note.deleteLater(), again.deleteLater(), retry()))
            self.col.insertWidget(self.col.count() - 1, again)
        self.scroll_down()

    def set_enabled(self, on: bool) -> None:
        self.send_btn.setEnabled(on)
        self.mic.setEnabled(on)

    def scroll_down(self) -> None:
        later(30, lambda: self.area.verticalScrollBar().setValue(self.area.verticalScrollBar().maximum()))

    # -- typing --
    def submit(self) -> None:
        text = self.composer.toPlainText().strip()
        if text and self.send_btn.isEnabled():
            self.composer.clear()
            self.submitted.emit(text)

    # -- speaking --
    def toggle_mic(self) -> None:
        if self.recorder.recording:
            self.stop_mic()
            return
        try:
            self.recorder.start()
        except audio.AudioError as exc:
            self.show_error(str(exc))
            return
        self.listening.show()
        self.mic.setIcon(icon("stop", theme.palette()["bad"]))
        self.mic.setToolTip("Stop and send")
        self.send_btn.setEnabled(False)
        self.tick.start()

    def stop_mic(self, cancel: bool = False) -> None:
        self.tick.stop()
        self.listening.hide()
        self.mic.setIcon(icon("mic"))
        self.mic.setToolTip("Speak instead of typing")
        self.send_btn.setEnabled(True)
        if cancel:
            self.recorder.cancel()
            return
        try:
            wav = self.recorder.stop()
        except audio.AudioError as exc:
            self.show_error(str(exc))
            return
        self.thinking("Listening to what you said…")
        workers.run(ai.transcribe, wav, on_done=self._heard, on_error=self.show_error)

    def _heard(self, text: str) -> None:
        self.end_thinking()
        if not text.strip():
            self.show_error("I didn't catch that - try again a little closer to the microphone.")
            return
        self.submitted.emit(text.strip())

    def _update_meter(self) -> None:
        if not self.recorder.recording:
            return
        secs = self.recorder.seconds()
        self.listen_text.setText(f"Listening…  {int(secs) // 60}:{int(secs) % 60:02d}")
        self.meter.setValue(int(self.recorder.level() * 100))
        if secs >= audio.MAX_SECONDS:
            self.stop_mic()
