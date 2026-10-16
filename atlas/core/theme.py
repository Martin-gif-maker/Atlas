"""Colours and the stylesheet: a quiet Mac look that follows the system's light / dark setting.

Two palettes - "Paper" (light) and "Graphite" (dark): warm neutral surfaces, hairline borders and one
ink-blue accent. Widgets pick up their style from Qt properties, for example::

    button.setProperty("kind", "primary")     # the one blue button on a screen
    frame.setProperty("card", True)           # white card with a hairline border
    label.setProperty("role", "muted")        # secondary text
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

PAPER = {
    "dark": False,
    "window": "#FBFAF8", "side": "#F4F2EE", "line": "#E2DFD9",
    "card": "#FFFFFF", "card_line": "#DDD9D1", "well": "#ECE9E3",
    "text": "#1D1D1F", "muted": "#68655E",
    "accent": "#1F4FD8", "accent_hover": "#1A43B8", "accent_text": "#1F4FD8", "on_accent": "#FFFFFF",
    "ok": "#2E7D4F", "bad": "#B83227", "warn": "#9A6200",
}
GRAPHITE = {
    "dark": True,
    "window": "#1E1E20", "side": "#252528", "line": "#343437",
    "card": "#2A2A2E", "card_line": "#3E3E43", "well": "#35353A",
    "text": "#E8E8EA", "muted": "#A3A3A9",
    "accent": "#3D6BF0", "accent_hover": "#5580FF", "accent_text": "#7FA3FF", "on_accent": "#FFFFFF",
    "ok": "#5BBF85", "bad": "#E8796A", "warn": "#E0B060",
}


def is_dark() -> bool:
    app = QGuiApplication.instance()
    if app is None:
        return False
    return app.styleHints().colorScheme() == Qt.ColorScheme.Dark


def palette() -> dict:
    return GRAPHITE if is_dark() else PAPER


def stylesheet(p: dict) -> str:
    return f"""
* {{ color: {p['text']}; font-size: 13px; }}
QMainWindow, QDialog, #Page {{ background: {p['window']}; }}
QWidget#Page, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {p['window']}; border: none; }}

#Sidebar {{ background: {p['side']}; border-right: 1px solid {p['line']}; }}
#Sidebar QListWidget {{ background: transparent; border: none; outline: none; }}
#Sidebar QListWidget::item {{ padding: 7px 10px; border-radius: 6px; margin: 1px 0; color: {p['text']}; }}
#Sidebar QListWidget::item:hover {{ background: {p['well']}; }}
#Sidebar QListWidget::item:selected {{ background: {p['well']}; color: {p['text']}; font-weight: 600; }}
QListWidget[rows="two"] {{ background: transparent; border: none; outline: none; }}
QListWidget[rows="two"]::item, #Sidebar QListWidget[rows="two"]::item {{ padding: 0; margin: 1px 0; border-radius: 6px; }}
QListWidget[rows="two"]::item:hover, QListWidget[rows="two"]::item:selected {{ background: {p['well']}; }}

QFrame[card="true"] {{ background: {p['card']}; border: 1px solid {p['card_line']}; border-radius: 10px; }}
QFrame[card="true"] QLabel {{ background: transparent; border: none; }}
QFrame[hairline="true"] {{ background: {p['line']}; border: none; max-height: 1px; min-height: 1px; }}

QLabel {{ background: transparent; }}
QLabel[role="app"] {{ font-size: 15px; font-weight: 600; }}
QLabel[role="title"] {{ font-size: 22px; font-weight: 600; }}
QLabel[role="heading"] {{ font-size: 15px; font-weight: 600; }}
QLabel[role="section"] {{ font-size: 11px; font-weight: 600; color: {p['muted']}; letter-spacing: 0.4px; }}
QLabel[role="muted"] {{ color: {p['muted']}; }}
QLabel[role="small"] {{ color: {p['muted']}; font-size: 12px; }}
QLabel[role="error"] {{ color: {p['bad']}; }}
QLabel[role="ok"] {{ color: {p['ok']}; }}
QLabel[role="big"] {{ font-size: 34px; font-weight: 600; }}
QLabel[role="link"] {{ color: {p['accent_text']}; }}

QPushButton {{
    background: {p['card']}; border: 1px solid {p['card_line']}; border-radius: 7px;
    padding: 6px 14px; min-height: 18px;
}}
QPushButton:hover {{ background: {p['well']}; }}
QPushButton:pressed {{ background: {p['line']}; }}
QPushButton:disabled {{ color: {p['muted']}; }}
QPushButton[kind="primary"] {{
    background: {p['accent']}; color: {p['on_accent']}; border: 1px solid {p['accent']}; font-weight: 600;
}}
QPushButton[kind="primary"]:hover {{ background: {p['accent_hover']}; border-color: {p['accent_hover']}; }}
QPushButton[kind="primary"]:disabled {{ background: {p['well']}; border-color: {p['card_line']}; color: {p['muted']}; }}
QPushButton[kind="quiet"] {{ background: transparent; border: none; color: {p['accent_text']}; padding: 4px 6px; }}
QPushButton[kind="quiet"]:hover {{ text-decoration: underline; }}
QPushButton[kind="side"] {{ text-align: left; padding: 7px 10px; background: transparent; border: none; border-radius: 6px; }}
QPushButton[kind="side"]:hover {{ background: {p['well']}; }}
QPushButton[kind="choice"] {{ text-align: left; padding: 10px 14px; border-radius: 8px; }}
QPushButton[kind="choice"]:checked {{ border: 1px solid {p['accent']}; background: {p['card']}; }}
QPushButton[state="right"], QPushButton[state="right"]:disabled {{ border: 1px solid {p['ok']}; color: {p['ok']}; }}
QPushButton[state="wrong"], QPushButton[state="wrong"]:disabled {{ border: 1px solid {p['bad']}; color: {p['bad']}; }}

#Segments {{ background: {p['well']}; border-radius: 8px; }}
#Segments QPushButton {{ background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 5px 12px; }}
#Segments QPushButton:hover {{ background: {p['line']}; }}
#Segments QPushButton:checked {{ background: {p['card']}; border: 1px solid {p['card_line']}; }}

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {{
    background: {p['card']}; border: 1px solid {p['card_line']}; border-radius: 7px; padding: 6px 8px;
    selection-background-color: {p['accent']}; selection-color: {p['on_accent']};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{ border: 1px solid {p['accent']}; }}
QTextBrowser {{ background: transparent; border: none; }}

QProgressBar {{ background: {p['well']}; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }}
QProgressBar::chunk {{ background: {p['accent']}; border-radius: 3px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p['card_line']}; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ height: 0; }}

QToolTip {{ background: {p['card']}; color: {p['text']}; border: 1px solid {p['card_line']}; padding: 4px 6px; }}
QMenu {{ background: {p['card']}; border: 1px solid {p['card_line']}; padding: 4px; }}
QMenu::item {{ padding: 5px 18px; border-radius: 5px; }}
QMenu::item:selected {{ background: {p['well']}; color: {p['text']}; }}
"""


def apply(app) -> None:
    """Style the whole app now and again whenever macOS switches between light and dark."""
    app.setStyleSheet(stylesheet(palette()))
    app.styleHints().colorSchemeChanged.connect(lambda *_: app.setStyleSheet(stylesheet(palette())))


def restyle(widget) -> None:
    """Re-read the stylesheet after a widget's property (kind / role / state) changed."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
