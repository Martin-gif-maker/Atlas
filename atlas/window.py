"""Atlas's window: the four modes on the left with their history; the chosen mode on the right."""
from __future__ import annotations

import random
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
                               QMenu, QPlainTextEdit, QStackedWidget, QVBoxLayout, QWidget)

from . import ai, audio, db
from .chatview import ChatView
from .core import storage, workers
from .core.widgets import (AppWindow, Busy, KeyPrompt, Notice, add_shortcut, add_two_line, button, card, clear,
                           hairline, icon, label, scroll_page, two_line_list)

MODES = [("voice", "Voice", "mic"), ("doc", "Documents", "file"), ("study", "Study", "cards"),
         ("interview", "Interview", "person")]


def _when(ts: float) -> str:
    return time.strftime("%-d %b", time.localtime(ts or time.time()))


def read_aloud() -> bool:
    return bool(storage.load_json("settings.json", {}).get("read_aloud", True))


def set_read_aloud(on: bool) -> None:
    data = storage.load_json("settings.json", {})
    data["read_aloud"] = on
    storage.save_json("settings.json", data)


def _header(title_role: str = "title") -> tuple:
    """A page header: title and a small line under it on the left, room for buttons on the right."""
    head = QWidget()
    lay = QHBoxLayout(head)
    lay.setContentsMargins(32, 22, 32, 10)
    titles = QVBoxLayout()
    titles.setSpacing(3)
    title = label("", title_role, wrap=True)
    sub = label("", "small", wrap=True)
    titles.addWidget(title)
    titles.addWidget(sub)
    lay.addLayout(titles, 1)
    return head, title, sub, lay


# ── a conversation with the AI (Voice, Documents and Interview build on this) ──────────────────────────
class ConversationPage(QWidget):
    mode = "voice"
    placeholder = "Type a message…"
    empty_text = ""
    speaks = False

    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.window = window
        self.conv_id: int | None = None
        self.messages: list[dict] = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.head, self.title, self.sub, self.head_lay = _header()
        if self.speaks:
            self.aloud = QCheckBox("Read answers aloud")
            self.aloud.setChecked(read_aloud())
            self.aloud.toggled.connect(self._aloud_changed)
            self.head_lay.addWidget(self.aloud, 0, Qt.AlignmentFlag.AlignTop)
        self.delete_btn = button("Delete", icon_name="trash", on_click=self.delete)
        self.head_lay.addWidget(self.delete_btn, 0, Qt.AlignmentFlag.AlignTop)
        if self.speaks:
            self.aloud.setMinimumHeight(self.delete_btn.sizeHint().height())   # lines up with the buttons
        outer.addWidget(self.head)
        self.chat = ChatView(self.placeholder, self.empty_text)
        self.chat.submitted.connect(self.send)
        outer.addWidget(self.chat, 1)
        self.key_prompt = KeyPrompt("Atlas")
        self.key_prompt.open_settings.connect(window.open_settings)

    def _aloud_changed(self, on: bool) -> None:
        set_read_aloud(on)
        if not on:
            self.window.speaker.stop()

    def open(self, conv_id: int | None) -> None:
        self.conv_id = conv_id
        conv = db.conversation(conv_id) if conv_id else None
        self.messages = db.messages(conv_id) if conv_id else []
        self.delete_btn.setVisible(conv is not None)
        self.set_titles(conv)
        self.chat.set_messages(self.messages, None if storage.get_api_key() else self.key_prompt)
        self.chat.composer.setFocus()

    def set_titles(self, conv: dict | None) -> None:
        raise NotImplementedError

    def system(self, question: str) -> str:
        raise NotImplementedError

    def new_conversation(self, first_text: str) -> int:
        return db.new_conversation(self.mode, ai.fallback_title(first_text))

    def history_for_ai(self) -> list[dict]:
        return list(self.messages)

    def send(self, text: str) -> None:
        if not storage.get_api_key():
            self.window.open_settings()
            if not storage.get_api_key():
                return
        first = self.conv_id is None
        if first:
            self.conv_id = self.new_conversation(text)
            self.delete_btn.show()
        conv_id = self.conv_id
        db.add_message(conv_id, "user", text)
        self.messages.append({"role": "user", "content": text})
        self.chat.add_message("user", text)
        self.window.reload_list(select=conv_id)
        self.ask(conv_id, text, first)

    def ask(self, conv_id: int, text: str, first: bool = False) -> None:
        self.chat.thinking("Thinking…")
        history = self.history_for_ai()
        workers.run(lambda: ai.reply(history, self.system(text), max_tokens=self.max_tokens()),
                    on_done=lambda answer: self._answered(conv_id, answer, first),
                    on_error=lambda msg: self._failed(conv_id, text, msg))

    def max_tokens(self) -> int:
        return 700

    def _answered(self, conv_id: int, answer: str, first: bool) -> None:
        if db.conversation(conv_id) is None:
            return                                         # deleted meanwhile
        db.add_message(conv_id, "assistant", answer)
        if self.conv_id == conv_id:
            self.messages.append({"role": "assistant", "content": answer})
            self.chat.add_message("assistant", answer)
            if self.speaks and self.aloud.isChecked():
                self.window.speaker.say(answer)
        self.window.reload_list(select=self.conv_id if self.window.current_mode() == self.mode else None)
        if first and self.mode == "voice":
            question = next((m["content"] for m in db.messages(conv_id) if m["role"] == "user"), "")
            workers.run(ai.make_title, question, on_done=lambda title: self._titled(conv_id, title))

    def _titled(self, conv_id: int, title: str) -> None:
        if db.conversation(conv_id):
            db.set_title(conv_id, title)
            self.window.reload_list(select=self.conv_id if self.window.current_mode() == self.mode else None)
            if self.conv_id == conv_id:
                self.set_titles(db.conversation(conv_id))

    def _failed(self, conv_id: int, text: str, message: str) -> None:
        if self.conv_id == conv_id:
            self.chat.show_error(message, retry=lambda: self.ask(conv_id, text))

    def delete(self) -> None:
        conv = db.conversation(self.conv_id) if self.conv_id else None
        if conv and self.window.confirm(f"Delete “{conv['title']}”?", "This cannot be undone."):
            db.delete_conversation(conv["id"])
            self.window.speaker.stop()
            self.window.reload_list()
            self.open(None)


class VoicePage(ConversationPage):
    mode = "voice"
    placeholder = "Say something with the microphone, or type here…"
    empty_text = ("Click the microphone, speak, and click it again when you are done - or just type. "
                  "Atlas answers in a few sentences and reads them aloud.")
    speaks = True

    def set_titles(self, conv):
        self.title.setText(conv["title"] if conv else "Voice")
        self.sub.setText(f"Started {_when(conv['created_at'])}" if conv else "Talk or type - Atlas answers out loud.")

    def system(self, question):
        return ai.VOICE_SYSTEM

    def max_tokens(self):
        return 300


class InterviewChat(ConversationPage):
    mode = "interview"
    placeholder = "Answer out loud with the microphone, or type your answer…"
    speaks = True

    def __init__(self, window):
        super().__init__(window)
        self.role = ""
        self.feedback = button("Ask for feedback", on_click=lambda: self.send("How did I do? Please give me "
                                                                              "honest feedback and one tip."))
        self.head_lay.insertWidget(1, self.feedback, 0, Qt.AlignmentFlag.AlignTop)

    def set_titles(self, conv):
        self.role = (conv or {}).get("role_name") or ""
        self.title.setText(f"Interview: {self.role}")
        self.sub.setText(f"Started {_when(conv['created_at'])}" if conv else "")

    def system(self, question):
        return ai.interview_system(self.role)

    def history_for_ai(self):
        return [{"role": "user", "content": ai.INTERVIEW_OPENER}] + list(self.messages)

    def start(self, role: str) -> None:
        self.conv_id = db.new_conversation("interview", f"Interview: {role}", role_name=role)
        self.open(self.conv_id)
        self.window.reload_list(select=self.conv_id)
        self.ask(self.conv_id, ai.INTERVIEW_OPENER)


class DocChat(ConversationPage):
    mode = "doc"
    placeholder = "Ask anything about this document…"
    empty_text = "Ask a question about this document. Atlas answers only from what it says."

    def __init__(self, window):
        super().__init__(window)
        self.doc: dict | None = None
        self.delete_btn.setText("Delete document")
        self.clear_btn = button("Clear chat", icon_name="refresh", on_click=self.clear_chat)
        self.head_lay.insertWidget(1, self.clear_btn, 0, Qt.AlignmentFlag.AlignTop)

    def open_doc(self, doc_id: int) -> None:
        self.doc = db.document(doc_id)
        convs = db.conversations("doc", doc_id)
        self.open(convs[0]["id"] if convs else None)
        self.delete_btn.show()

    def set_titles(self, conv):
        d = self.doc
        self.title.setText(d["title"])
        self.sub.setText(f"{d['page_count']} pages · {d['char_count']:,} characters · added {_when(d['created_at'])}")
        self.clear_btn.setEnabled(conv is not None)

    def new_conversation(self, first_text):
        self.clear_btn.setEnabled(True)
        return db.new_conversation("doc", self.doc["title"], document_id=self.doc["id"])

    def system(self, question):
        return ai.doc_system(self.doc["title"], self.doc["text_content"], question, self.messages)

    def clear_chat(self) -> None:
        if self.conv_id and self.window.confirm("Clear this chat?", "The document stays; only the messages go.",
                                                action="Clear"):
            db.delete_conversation(self.conv_id)
            self.open(None)
            self.delete_btn.show()

    def delete(self) -> None:
        if self.doc and self.window.confirm(f"Delete “{self.doc['title']}”?",
                                            "Its chat goes too. The PDF file itself is not touched."):
            db.delete_document(self.doc["id"])
            self.doc = None
            self.window.reload_list()
            self.window.docs.show_start()


# ── Documents ────────────────────────────────────────────────────────────────────────────────────
class DocsPage(QStackedWidget):
    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.window = window
        start = QWidget()
        outer = QVBoxLayout(start)
        outer.setContentsMargins(0, 0, 0, 0)
        area, col = scroll_page(640)
        outer.addWidget(area)
        col.addSpacing(20)
        col.addWidget(label("Documents", "title"))
        col.addWidget(label("Add a PDF and chat with it. Atlas answers only from what the document says.",
                            "muted", wrap=True))
        drop, lay = card((24, 30, 24, 30), 10)
        drop.setStyleSheet("QFrame[card=\"true\"] { border-style: dashed; }")
        lay.addWidget(label("Drop a PDF here", "heading"), 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(label("or", "small"), 0, Qt.AlignmentFlag.AlignHCenter)
        self.choose = button("Choose a PDF…", "primary", "file", on_click=window.choose_pdf)
        lay.addWidget(self.choose, 0, Qt.AlignmentFlag.AlignHCenter)
        col.addWidget(drop)
        self.busy = Busy("Reading the PDF…")
        col.addWidget(self.busy)
        self.notice = Notice()
        col.addWidget(self.notice)
        col.addStretch(1)
        self.chat = DocChat(window)
        self.addWidget(start)
        self.addWidget(self.chat)
        self.start_page = start

    def show_start(self) -> None:
        self.setCurrentWidget(self.start_page)

    def open_doc(self, doc_id: int) -> None:
        self.chat.open_doc(doc_id)
        self.setCurrentWidget(self.chat)


# ── Interview ────────────────────────────────────────────────────────────────────────────────────
class InterviewPage(QStackedWidget):
    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.window = window
        start = QWidget()
        outer = QVBoxLayout(start)
        outer.setContentsMargins(0, 0, 0, 0)
        area, col = scroll_page(640)
        outer.addWidget(area)
        col.addSpacing(20)
        col.addWidget(label("Interview practice", "title"))
        col.addWidget(label("Atlas plays the hiring manager: one question at a time, follow-ups on your answers, "
                            "and honest feedback at the end. Answer by speaking or typing.", "muted", wrap=True))
        self.key_prompt = KeyPrompt("Atlas")
        self.key_prompt.open_settings.connect(window.open_settings)
        col.addWidget(self.key_prompt)
        box, lay = card()
        lay.addWidget(label("What role are you preparing for?", "heading"))
        self.role = QLineEdit()
        self.role.setPlaceholderText("e.g. Junior AI Engineer")
        self.role.returnPressed.connect(self.begin)
        lay.addWidget(self.role)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        for r in ai.ROLES:
            chip = button(r.split(" (")[0], on_click=lambda r=r: self.role.setText(r))
            chips.addWidget(chip)
        chips.addStretch(1)
        lay.addLayout(chips)
        col.addWidget(box)
        row = QHBoxLayout()
        self.go = button("Start interview", "primary", on_click=self.begin)
        row.addWidget(self.go)
        row.addStretch(1)
        col.addLayout(row)
        self.notice = Notice()
        col.addWidget(self.notice)
        col.addStretch(1)
        self.chat = InterviewChat(window)
        self.addWidget(start)
        self.addWidget(self.chat)
        self.start_page = start

    def show_start(self) -> None:
        self.key_prompt.setVisible(not storage.get_api_key())
        self.setCurrentWidget(self.start_page)
        self.role.setFocus()

    def begin(self) -> None:
        role = " ".join(self.role.text().split())[:80]
        if not role:
            self.notice.show_error("Type a role or pick one first.")
            return
        if not storage.get_api_key():
            self.window.open_settings()
            if not storage.get_api_key():
                return
        self.notice.clear_text()
        self.role.clear()
        self.setCurrentWidget(self.chat)
        self.chat.start(role)

    def open_conv(self, conv_id: int) -> None:
        self.chat.open(conv_id)
        self.setCurrentWidget(self.chat)


# ── Study ────────────────────────────────────────────────────────────────────────────────────────
class StudyPage(QStackedWidget):
    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.window = window
        self.deck: dict | None = None
        self.cards: list[dict] = []
        self.index = 0
        self.flipped = False

        start = QWidget()
        outer = QVBoxLayout(start)
        outer.setContentsMargins(0, 0, 0, 0)
        area, col = scroll_page(700)
        outer.addWidget(area)
        col.addWidget(label("New flashcard deck", "title"))
        col.addWidget(label("Paste your notes. Atlas makes 8-15 flashcards on the key ideas, and keeps the deck "
                            "so you can review it again.", "muted", wrap=True))
        self.key_prompt = KeyPrompt("Atlas")
        self.key_prompt.open_settings.connect(window.open_settings)
        col.addWidget(self.key_prompt)
        self.form, lay = card()
        lay.addWidget(label("Deck title (optional)", "section"))
        self.deck_title = QLineEdit()
        self.deck_title.setPlaceholderText("Made from your notes if you leave it empty")
        lay.addWidget(self.deck_title)
        lay.addSpacing(4)
        lay.addWidget(label("Your notes", "section"))
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Paste a lesson, a chapter or your own notes…")
        self.notes.setMinimumHeight(220)
        lay.addWidget(self.notes)
        col.addWidget(self.form)
        row = QHBoxLayout()
        self.go = button("Make flashcards", "primary", on_click=self.make)
        row.addWidget(self.go)
        row.addStretch(1)
        col.addLayout(row)
        self.busy = Busy("Writing your flashcards…")
        col.addWidget(self.busy)
        self.notice = Notice()
        col.addWidget(self.notice)
        col.addStretch(1)

        review = QWidget()
        review.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        review.keyPressEvent = self._keys
        rv = QVBoxLayout(review)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        head, self.r_title, self.r_sub, head_lay = _header()
        head_lay.addWidget(button("Shuffle", icon_name="refresh", on_click=self.shuffle), 0, Qt.AlignmentFlag.AlignTop)
        head_lay.addWidget(button("Delete", icon_name="trash", on_click=self.delete), 0, Qt.AlignmentFlag.AlignTop)
        rv.addWidget(head)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(32, 10, 32, 28)
        bl.setSpacing(12)
        self.counter = label("", "small")
        bl.addWidget(self.counter)
        self.face = QFrame()
        self.face.setProperty("card", True)
        self.face.setMinimumHeight(260)
        self.face.setCursor(Qt.CursorShape.PointingHandCursor)
        self.face.mousePressEvent = lambda _e: (review.setFocus(), self.flip())
        self.face_lay = QVBoxLayout(self.face)
        self.face_lay.setContentsMargins(34, 28, 34, 28)
        self.face_lay.setSpacing(12)
        bl.addWidget(self.face, 1)
        nav = QHBoxLayout()
        self.prev_btn = button("Previous", icon_name="left", on_click=lambda: self.move(-1))
        self.flip_btn = button("Show answer", "primary", on_click=self.flip)
        self.next_btn = button("Next", on_click=lambda: self.move(1))
        self.next_btn.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.next_btn.setIcon(icon("right"))
        for b in (self.prev_btn, self.flip_btn, self.next_btn):
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        nav.addWidget(self.prev_btn)
        nav.addStretch(1)
        nav.addWidget(self.flip_btn)
        nav.addStretch(1)
        nav.addWidget(self.next_btn)
        bl.addLayout(nav)
        bl.addWidget(label("Space shows the answer · arrow keys move between cards", "small"), 0,
                     Qt.AlignmentFlag.AlignHCenter)
        rv.addWidget(body, 1)
        self.addWidget(start)
        self.addWidget(review)
        self.start_page, self.review = start, review

    def show_start(self) -> None:
        has_key = bool(storage.get_api_key())
        self.key_prompt.setVisible(not has_key)
        self.form.setEnabled(has_key)
        self.go.setEnabled(has_key)
        self.deck = None
        self.setCurrentWidget(self.start_page)

    def make(self) -> None:
        notes = self.notes.toPlainText().strip()
        if len(notes) < 30:
            self.notice.show_error("Paste a bit more - at least a few sentences of notes.")
            return
        title = self.deck_title.text().strip()[:80]
        self.notice.clear_text()
        self.go.setEnabled(False)
        self.busy.start()
        workers.run(self._make_deck, title, notes, on_done=self._made, on_error=self._failed)

    @staticmethod
    def _make_deck(title: str, notes: str) -> int:
        cards = ai.flashcards(notes)
        title = title or ai.make_title(notes[:200])
        return db.add_deck(title, notes[:240], cards)

    def _made(self, deck_id: int) -> None:
        self.busy.stop()
        self.go.setEnabled(True)
        self.notes.clear()
        self.deck_title.clear()
        self.window.reload_list(select=deck_id)
        self.open_deck(deck_id)

    def _failed(self, message: str) -> None:
        self.busy.stop()
        self.go.setEnabled(True)
        self.notice.show_error(message)

    def open_deck(self, deck_id: int) -> None:
        self.deck = db.deck(deck_id)
        if not self.deck:
            return
        self.cards = list(self.deck["cards"])
        self.index, self.flipped = 0, False
        self.r_title.setText(self.deck["title"])
        self.r_sub.setText(f"{len(self.cards)} cards · made {_when(self.deck['created_at'])}")
        self.setCurrentWidget(self.review)
        self.review.setFocus()
        self.draw()

    def draw(self) -> None:
        c = self.cards[self.index]
        self.counter.setText(f"Card {self.index + 1} of {len(self.cards)}")
        clear(self.face_lay)
        self.face_lay.addStretch(1)
        q = label(c["question"], "heading", wrap=True)
        q.setAlignment(Qt.AlignmentFlag.AlignCenter)
        q.setStyleSheet("font-size: 18px;")
        self.face_lay.addWidget(q)
        if self.flipped:
            self.face_lay.addWidget(hairline())
            a = label(c["answer"], wrap=True, selectable=True)
            a.setAlignment(Qt.AlignmentFlag.AlignCenter)
            a.setStyleSheet("font-size: 15px;")
            self.face_lay.addWidget(a)
        self.face_lay.addStretch(1)
        self.flip_btn.setText("Hide answer" if self.flipped else "Show answer")
        self.prev_btn.setEnabled(self.index > 0)
        self.next_btn.setEnabled(self.index < len(self.cards) - 1)

    def flip(self) -> None:
        self.flipped = not self.flipped
        self.draw()

    def move(self, step: int) -> None:
        if 0 <= self.index + step < len(self.cards):
            self.index += step
            self.flipped = False
            self.draw()

    def shuffle(self) -> None:
        random.shuffle(self.cards)
        self.index, self.flipped = 0, False
        self.draw()

    def _keys(self, event) -> None:
        actions = {Qt.Key.Key_Space: self.flip, Qt.Key.Key_Left: lambda: self.move(-1),
                   Qt.Key.Key_Right: lambda: self.move(1)}
        if self.cards and event.key() in actions:
            actions[event.key()]()

    def delete(self) -> None:
        if self.deck and self.window.confirm(f"Delete the deck “{self.deck['title']}”?", "This cannot be undone."):
            db.delete_deck(self.deck["id"])
            self.window.reload_list()
            self.show_start()


# ── the window ───────────────────────────────────────────────────────────────────────────────────
class MainWindow(AppWindow):
    LIST_TITLES = {"voice": ("Conversations", "New conversation"), "doc": ("Documents", "Add PDF…"),
                   "study": ("Decks", "New deck"), "interview": ("Interviews", "New interview")}

    def __init__(self, speaker: audio.Speaker | None = None):
        super().__init__("Atlas")
        self.speaker = speaker or audio.Speaker()
        self.nav = QListWidget()
        for key, text, icon_name in MODES:
            item = QListWidgetItem(icon(icon_name), text, self.nav)
            item.setData(Qt.ItemDataRole.UserRole, key)
        self.nav.setFixedHeight(len(MODES) * 38)
        self.sidebar.lay.addWidget(self.nav)
        self.sidebar.lay.addSpacing(14)
        self.list_title = label("", "section")
        self.list_title.setContentsMargins(10, 0, 0, 2)
        self.sidebar.lay.addWidget(self.list_title)
        self.new_btn = button("", "side", "plus", on_click=self.new_item)
        self.sidebar.lay.addWidget(self.new_btn)
        self.list = two_line_list()
        self.list.currentItemChanged.connect(lambda item, _old: item and self._open_item(item))
        self.list.itemClicked.connect(self._open_item)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._list_menu)
        self.sidebar.lay.addWidget(self.list, 1)
        self.sidebar.finish()

        self.voice = VoicePage(self)
        self.docs = DocsPage(self)
        self.study = StudyPage(self)
        self.interview = InterviewPage(self)
        self.mode_pages = {"voice": self.voice, "doc": self.docs, "study": self.study, "interview": self.interview}
        for page in self.mode_pages.values():
            self.pages.addWidget(page)
        self.nav.currentRowChanged.connect(self._mode_changed)
        self.setAcceptDrops(True)
        add_shortcut(self, "Ctrl+N", self.new_item)
        self.nav.setCurrentRow(0)

    def current_mode(self) -> str:
        item = self.nav.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else "voice"

    def _mode_changed(self, _row: int) -> None:
        mode = self.current_mode()
        title, new_text = self.LIST_TITLES[mode]
        self.list_title.setText(title)
        self.new_btn.setText(new_text)
        self.pages.setCurrentWidget(self.mode_pages[mode])
        self.reload_list()
        self.new_item(from_mode_change=True)

    def key_changed(self) -> None:
        self._mode_changed(self.nav.currentRow())

    # -- the list for the current mode --
    def _items(self, mode: str) -> list[tuple[int, str, str]]:
        if mode == "doc":
            return [(d["id"], d["title"], f"{d['page_count']} pages · {_when(d['created_at'])}") for d in db.documents()]
        if mode == "study":
            return [(d["id"], d["title"], f"{d['card_count']} cards · {_when(d['created_at'])}") for d in db.decks()]
        return [(c["id"], c["title"].removeprefix("Interview: "), _when(c["updated_at"]))
                for c in db.conversations(mode)]

    def reload_list(self, select: int | None = None) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for item_id, title, sub in self._items(self.current_mode()):
            item = add_two_line(self.list, title, sub, item_id)
            if item_id == select:
                self.list.setCurrentItem(item)
        self.list.blockSignals(False)

    def _open_item(self, item) -> None:
        item_id = item.data(Qt.ItemDataRole.UserRole)
        mode = self.current_mode()
        if mode == "voice":
            if self.voice.conv_id != item_id:
                self.voice.open(item_id)
        elif mode == "doc":
            if self.docs.currentWidget() is not self.docs.chat or not self.docs.chat.doc \
                    or self.docs.chat.doc["id"] != item_id:
                self.docs.open_doc(item_id)
        elif mode == "study":
            if not self.study.deck or self.study.deck["id"] != item_id:
                self.study.open_deck(item_id)
        else:
            if self.interview.currentWidget() is not self.interview.chat or self.interview.chat.conv_id != item_id:
                self.interview.open_conv(item_id)

    def new_item(self, from_mode_change: bool = False) -> None:
        mode = self.current_mode()
        self.list.blockSignals(True)
        self.list.setCurrentRow(-1)
        self.list.blockSignals(False)
        if mode == "voice":
            if not from_mode_change or self.voice.conv_id is None:
                self.voice.open(None)
                self.reload_list()
            else:
                self.reload_list(select=self.voice.conv_id)
        elif mode == "doc":
            if from_mode_change and self.docs.currentWidget() is self.docs.chat and self.docs.chat.doc:
                self.reload_list(select=self.docs.chat.doc["id"])
            elif from_mode_change:
                self.docs.show_start()
            else:
                self.choose_pdf()
        elif mode == "study":
            if from_mode_change and self.study.deck:
                self.reload_list(select=self.study.deck["id"])
            else:
                self.study.show_start()
        else:
            if from_mode_change and self.interview.currentWidget() is self.interview.chat:
                self.reload_list(select=self.interview.chat.conv_id)
            else:
                self.interview.show_start()

    def _list_menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if not item:
            return
        self.list.setCurrentItem(item)
        page = {"voice": self.voice, "doc": self.docs.chat, "study": self.study,
                "interview": self.interview.chat}[self.current_mode()]
        menu = QMenu(self)
        menu.addAction("Delete…", page.delete)
        menu.exec(self.list.viewport().mapToGlobal(pos))

    # -- adding PDFs (Documents mode) --
    def choose_pdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a PDF", str(Path.home()), "PDF files (*.pdf)")
        if path:
            self.add_pdf(path)

    def dragEnterEvent(self, event) -> None:
        if any(u.toLocalFile().lower().endswith(".pdf") for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        pdfs = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile().lower().endswith(".pdf")]
        if pdfs:
            self.add_pdf(pdfs[0])

    def add_pdf(self, path: str) -> None:
        if self.current_mode() != "doc":
            self.nav.setCurrentRow(1)
        self.docs.show_start()
        self.docs.notice.clear_text()
        self.docs.choose.setEnabled(False)
        self.docs.busy.start(f"Reading “{Path(path).name}”…")
        workers.run(self._read_pdf, path, on_done=self._pdf_added, on_error=self._pdf_failed)

    @staticmethod
    def _read_pdf(path: str) -> int:
        text, pages = ai.read_pdf(path)
        return db.add_document(Path(path).stem[:80] or "Untitled document", Path(path).name, text, pages)

    def _pdf_added(self, doc_id: int) -> None:
        self.docs.busy.stop()
        self.docs.choose.setEnabled(True)
        if self.current_mode() == "doc":
            self.reload_list(select=doc_id)
        self.docs.open_doc(doc_id)

    def _pdf_failed(self, message: str) -> None:
        self.docs.busy.stop()
        self.docs.choose.setEnabled(True)
        self.docs.notice.show_error(message)

    def closeEvent(self, event) -> None:
        self.speaker.stop()
        for page in (self.voice, self.docs.chat, self.interview.chat):
            if page.chat.recorder.recording:
                page.chat.recorder.cancel()
        super().closeEvent(event)
