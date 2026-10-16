"""Building blocks shared by every screen: cards, segmented choices, the sidebar, notices and Settings."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (QButtonGroup, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea,
                               QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

from . import ai_client, storage, theme, workers
from .texts import T

# ── line icons (16-point grid, drawn in the theme's colour) ─────────────────────────────────────
PATHS = {
    "plus":    '<path d="M8 3v10M3 8h10"/>',
    "gear":    '<circle cx="8" cy="8" r="2.200"/><path d="M8 1.800v1.700M8 12.500v1.700M1.800 8h1.700M12.500 8h1.700M3.600 3.600l1.200 1.200M11.200 11.200l1.200 1.200M3.600 12.400l1.200-1.200M11.200 4.800l1.200-1.200"/>',
    "trash":   '<path d="M3 4.500h10M6.500 4.500V3h3v1.500M4.500 4.500l.500 8.500h6l.500-8.500"/>',
    "refresh": '<path d="M13 8a5 5 0 1 1-1.600-3.700M13 3v2.800h-2.800"/>',
    "copy":    '<rect x="5.500" y="5.500" width="7.500" height="7.500" rx="1.500"/><path d="M3 10.500V4a1 1 0 0 1 1-1h6.500"/>',
    "file":    '<path d="M4 2.500h5l3 3v8H4v-11zM9 2.500v3h3"/>',
    "send":    '<path d="M8 13V3M4 7l4-4 4 4"/>',
    "mic":     '<rect x="6" y="2" width="4" height="8" rx="2"/><path d="M3.500 8a4.500 4.500 0 0 0 9 0M8 12.500V14"/>',
    "stop":    '<rect x="4.500" y="4.500" width="7" height="7" rx="1.200" fill="currentColor" stroke="none"/>',
    "speaker": '<path d="M3 6.200v3.600h2.300L8.500 12.500v-9L5.300 6.200H3zM11 6a3 3 0 0 1 0 4"/>',
    "check":   '<path d="M3.500 8.500l3 3 6-7"/>',
    "cross":   '<path d="M4 4l8 8M12 4l-8 8"/>',
    "left":    '<path d="M10 4 6 8l4 4"/>',
    "right":   '<path d="M6 4l4 4-4 4"/>',
    "export":  '<path d="M8 10V2.500M5 5.500l3-3 3 3M3 10v3h10v-3"/>',
    "book":    '<path d="M3 3h4a1.500 1.500 0 0 1 1.500 1.500V13A1.500 1.500 0 0 0 7 11.500H3V3zM13 3H9.500A1.500 1.500 0 0 0 8 4.500"/><path d="M13 3v8.500H9.500A1.500 1.500 0 0 0 8 13"/>',
    "chat":    '<path d="M3 3.500h10v7H7l-3 2.500v-2.500H3v-7z"/>',
    "cards":   '<rect x="2.500" y="4.500" width="9" height="8" rx="1.300"/><path d="M5 2.500h7.500a1 1 0 0 1 1 1V10"/>',
    "person":  '<circle cx="8" cy="5.500" r="2.500"/><path d="M3 13.500a5 5 0 0 1 10 0"/>',
}
_icon_cache: dict = {}


def icon(name: str, color: str | None = None, size: int = 16) -> QIcon:
    from PySide6.QtSvg import QSvgRenderer
    color = color or theme.palette()["text"]
    key = (name, color, size)
    if key not in _icon_cache:
        screen = QGuiApplication.primaryScreen()
        ratio = max(2.0, float(screen.devicePixelRatio()) if screen else 2.0)
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" stroke="{color}" '
               f'color="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
               f'{PATHS[name]}</svg>')
        pm = QPixmap(int(size * ratio), int(size * ratio))
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        QSvgRenderer(QByteArray(svg.encode())).render(painter, QRectF(0, 0, size * ratio, size * ratio))
        painter.end()
        pm.setDevicePixelRatio(ratio)
        _icon_cache[key] = QIcon(pm)
    return _icon_cache[key]


# ── simple pieces ────────────────────────────────────────────────────────────────────────────────
def label(text: str = "", role: str | None = None, wrap: bool = False, selectable: bool = False) -> QLabel:
    lab = QLabel(text)
    if role:
        lab.setProperty("role", role)
    if wrap:
        lab.setWordWrap(True)
    if selectable:
        lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lab


def button(text: str, kind: str | None = None, icon_name: str | None = None, on_click=None) -> QPushButton:
    btn = QPushButton(text)
    if kind:
        btn.setProperty("kind", kind)
    if icon_name:
        p = theme.palette()
        btn.setIcon(icon(icon_name, p["on_accent"] if kind == "primary" else p["text"]))
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if on_click:
        btn.clicked.connect(lambda *_: on_click())
    return btn


def card(margins=(18, 16, 18, 16), spacing: int = 10) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setProperty("card", True)
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    return frame, lay


def hairline() -> QFrame:
    line = QFrame()
    line.setProperty("hairline", True)
    return line


def clear(layout) -> None:
    """Remove (and delete) everything inside a layout."""
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            clear(item.layout())


def scroll_page(max_width: int = 760) -> tuple[QScrollArea, QVBoxLayout]:
    """A scrolling page whose content stays a readable width and centred."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    outer = QWidget()
    outer.setObjectName("Page")
    row = QHBoxLayout(outer)
    row.setContentsMargins(32, 28, 32, 32)
    inner = QWidget()
    inner.setMaximumWidth(max_width)
    inner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    col = QVBoxLayout(inner)
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(14)
    row.addStretch(1)
    row.addWidget(inner, 100)
    row.addStretch(1)
    area.setWidget(outer)
    return area, col


class Segments(QWidget):
    """A row of choices where exactly one is picked (like the Mac's segmented control)."""
    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], value: str | None = None):
        super().__init__()
        self.setObjectName("Segments")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)
        self._group = QButtonGroup(self)
        self._buttons: dict[str, QPushButton] = {}
        for key, text in options:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._group.addButton(btn)
            self._buttons[key] = btn
            lay.addWidget(btn)
            btn.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
        self.set_value(value if value is not None else options[0][0])
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

    def value(self) -> str:
        for key, btn in self._buttons.items():
            if btn.isChecked():
                return key
        return ""

    def set_value(self, key: str) -> None:
        if key in self._buttons:
            self._buttons[key].setChecked(True)

    def button(self, key: str) -> QPushButton:
        return self._buttons[key]


class Notice(QLabel):
    """A one-line message under a form: errors in red, other news in grey. Empty = hidden."""

    def __init__(self):
        super().__init__()
        self.setWordWrap(True)
        self.hide()

    def show_error(self, text: str) -> None:
        self._show(text, "error")

    def show_info(self, text: str) -> None:
        self._show(text, "muted")

    def _show(self, text: str, role: str) -> None:
        self.setProperty("role", role)
        theme.restyle(self)
        self.setText(text)
        self.setVisible(bool(text))

    def clear_text(self) -> None:
        self.setText("")
        self.hide()


class Busy(QWidget):
    """'Working…' line with a thin moving bar, shown while the AI is thinking."""

    def __init__(self, text: str | None = None):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(6)
        self.text = label(text or T["working"], "muted")
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(False)
        self.bar.setFixedWidth(220)
        lay.addWidget(self.text)
        lay.addWidget(self.bar)
        self.hide()

    def start(self, text: str | None = None) -> None:
        if text:
            self.text.setText(text)
        self.show()

    def stop(self) -> None:
        self.hide()


class Sidebar(QWidget):
    """Left column: app name, a main action, a list and Settings at the bottom."""

    def __init__(self, app_name: str, width: int = 220):
        super().__init__()
        self.setObjectName("Sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(width)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(12, 16, 12, 12)
        self.lay.setSpacing(6)
        name = label(app_name, "app")
        name.setContentsMargins(8, 0, 0, 8)
        self.lay.addWidget(name)
        self.bottom = QVBoxLayout()
        self.bottom.setSpacing(2)
        self.settings_button = button(T["settings"], "side", "gear")
        self.bottom.addWidget(self.settings_button)

    def finish(self) -> None:
        """Call after adding the middle part: pins Settings to the bottom."""
        self.lay.addLayout(self.bottom)


# ── Settings: the Groq key ───────────────────────────────────────────────────────────────────────
class SettingsDialog(QDialog):
    key_changed = Signal()

    def __init__(self, parent=None, extra: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(T["settings"])
        self.setModal(True)
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(10)
        lay.addWidget(label(T["key_heading"], "heading"))
        lay.addWidget(label(T["key_explain"], "muted", wrap=True))
        self.field = QLineEdit()
        self.field.setEchoMode(QLineEdit.EchoMode.Password)
        self.field.setPlaceholderText("gsk_…")
        source = storage.key_source()
        if source == "saved":
            self.field.setPlaceholderText(T["key_saved_placeholder"])
        lay.addWidget(self.field)
        link = button(T["get_key_link"], "quiet",
                      on_click=lambda: QDesktopServices.openUrl(QUrl(ai_client.KEY_URL)))
        link.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        lay.addWidget(link)
        self.notice = Notice()
        lay.addWidget(self.notice)
        if source in ("env", "dotenv"):
            where = T["where_env"] if source == "env" else T["where_dotenv"]
            self.notice.show_info(T["key_in_use"].format(where=where))
        if extra is not None:
            lay.addWidget(hairline())
            lay.addWidget(extra)
        row = QHBoxLayout()
        self.remove_btn = button(T["remove_key"], on_click=self._remove)
        self.remove_btn.setVisible(source == "saved")
        row.addWidget(self.remove_btn)
        row.addStretch(1)
        row.addWidget(button(T["close"], on_click=self.reject))
        self.save_btn = button(T["save_key"], "primary", on_click=self._save)
        self.save_btn.setDefault(True)
        row.addWidget(self.save_btn)
        lay.addSpacing(4)
        lay.addLayout(row)

    def _save(self) -> None:
        key = self.field.text().strip()
        if not key:
            self.notice.show_error(T["paste_key_first"])
            return
        self.save_btn.setEnabled(False)
        self.notice.show_info(T["checking_key"])
        workers.run(ai_client.check_key, key, on_done=lambda _: self._saved(key), on_error=self._failed)

    def _saved(self, key: str) -> None:
        storage.set_api_key(key)
        ai_client.reset()
        self.key_changed.emit()
        self.accept()

    def _failed(self, message: str) -> None:
        self.save_btn.setEnabled(True)
        self.notice.show_error(message)

    def _remove(self) -> None:
        storage.set_api_key("")
        ai_client.reset()
        self.key_changed.emit()
        self.accept()


class KeyPrompt(QFrame):
    """Shown in place of a screen's content while there is no API key."""
    open_settings = Signal()

    def __init__(self, what: str):
        super().__init__()
        self.setProperty("card", True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(8)
        lay.addWidget(label(T["one_step"], "heading"))
        lay.addWidget(label(T["key_prompt"].format(what=what), "muted", wrap=True))
        row = QHBoxLayout()
        row.addWidget(button(T["add_key"], "primary", on_click=self.open_settings.emit))
        row.addWidget(button(T["get_free_key"], on_click=lambda: QDesktopServices.openUrl(QUrl(ai_client.KEY_URL))))
        row.addStretch(1)
        lay.addSpacing(4)
        lay.addLayout(row)


class TwoLine(QWidget):
    """A list row with a bold first line and a grey second line."""

    def __init__(self, title: str, subtitle: str = ""):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(1)
        self.title = label(title)
        self.title.setStyleSheet("font-weight: 600;")
        self.subtitle = label(subtitle, "small")
        lay.addWidget(self.title)
        if subtitle:
            lay.addWidget(self.subtitle)


def two_line_list() -> QListWidget:
    lst = QListWidget()
    lst.setProperty("rows", "two")
    lst.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
    return lst


def add_two_line(lst: QListWidget, title: str, subtitle: str = "", data=None, tooltip: str = "") -> QListWidgetItem:
    item = QListWidgetItem()
    row = TwoLine(title, subtitle)
    item.setSizeHint(QSize(100, row.sizeHint().height()))
    item.setData(Qt.ItemDataRole.UserRole, data)
    item.setData(Qt.ItemDataRole.AccessibleTextRole, title)
    if tooltip:
        item.setToolTip(tooltip)
    lst.addItem(item)
    lst.setItemWidget(item, row)
    return item


class AppWindow(QMainWindow):
    """The main window every app starts from: sidebar on the left, pages on the right, Settings."""

    def __init__(self, app_name: str):
        super().__init__()
        self.app_name = app_name
        self.setWindowTitle(app_name)
        self.resize(1080, 740)
        self.setMinimumSize(880, 600)
        root = QWidget()
        self.setCentralWidget(root)
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.sidebar = Sidebar(app_name)
        self.sidebar.settings_button.clicked.connect(self.open_settings)
        row.addWidget(self.sidebar)
        self.pages = QStackedWidget()
        row.addWidget(self.pages, 1)
        add_shortcut(self, "Ctrl+,", self.open_settings)

    # Override these two when the app has more settings or must react to a new key.
    def settings_extra(self) -> QWidget | None:
        return None

    def key_changed(self) -> None:
        pass

    def open_settings(self) -> None:
        dialog = SettingsDialog(self, self.settings_extra())
        dialog.key_changed.connect(self.key_changed)
        dialog.exec()

    # The tests replace these, so nothing touches the real clipboard or waits for a click.
    def copy_text(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)

    def confirm(self, question: str, detail: str = "", action: str | None = None) -> bool:
        box = QMessageBox(QMessageBox.Icon.Question, self.app_name, question,
                          QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes, self)
        box.setInformativeText(detail)
        box.button(QMessageBox.StandardButton.Yes).setText(action or T["delete"])
        return box.exec() == QMessageBox.StandardButton.Yes


def add_shortcut(widget: QWidget, keys: str, fn) -> None:
    QShortcut(QKeySequence(keys), widget, activated=fn)


def later(ms: int, fn) -> None:
    QTimer.singleShot(ms, fn)
