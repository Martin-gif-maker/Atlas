"""Atlas's SQLite database: conversations and their messages, documents, and flashcard decks.

Tables
------
conversations : one chat, in one mode ('voice', 'doc' or 'interview')
messages      : the messages of a conversation
documents     : PDFs added for document chat (their text is kept, the file itself is not needed again)
decks         : flashcard decks for Study mode
flashcards    : the cards of a deck

Deleting a parent row removes its children (ON DELETE CASCADE).
"""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Iterator

from .core import storage

_lock = threading.Lock()        # one writer at a time: the window and background jobs share the file
_ready: set[str] = set()

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    filename     TEXT,
    text_content TEXT NOT NULL,
    page_count   INTEGER DEFAULT 0,
    char_count   INTEGER DEFAULT 0,
    created_at   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    mode        TEXT NOT NULL CHECK (mode IN ('voice', 'doc', 'interview')),
    title       TEXT NOT NULL DEFAULT 'New conversation',
    document_id INTEGER,
    role_name   TEXT,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    created_at      REAL NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS decks (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    title          TEXT NOT NULL,
    source_preview TEXT,
    created_at     REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS flashcards (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    deck_id  INTEGER NOT NULL,
    question TEXT NOT NULL,
    answer   TEXT NOT NULL,
    position INTEGER DEFAULT 0,
    FOREIGN KEY (deck_id) REFERENCES decks(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_conv_mode     ON conversations(mode, updated_at);
CREATE INDEX IF NOT EXISTS idx_conv_doc      ON conversations(document_id);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_cards_deck    ON flashcards(deck_id);
"""


@contextmanager
def cursor() -> Iterator[sqlite3.Cursor]:
    """A cursor that commits on success, rolls back on error and always closes."""
    with _lock:
        path = str(storage.data_dir() / "atlas.db")
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            cur = conn.cursor()
            if path not in _ready:                  # create the tables once per database file
                cur.executescript(SCHEMA)
                _ready.add(path)
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


# ── conversations ────────────────────────────────────────────────────────────────────────────────
def new_conversation(mode: str, title: str = "New conversation", document_id: int | None = None,
                     role_name: str | None = None) -> int:
    with cursor() as cur:
        now = time.time()
        cur.execute("INSERT INTO conversations (mode, title, document_id, role_name, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)", (mode, title, document_id, role_name, now, now))
        return cur.lastrowid


def conversation(conv_id: int) -> dict | None:
    with cursor() as cur:
        cur.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def conversations(mode: str, document_id: int | None = None) -> list[dict]:
    with cursor() as cur:
        if document_id is None:
            cur.execute("SELECT * FROM conversations WHERE mode = ? ORDER BY updated_at DESC", (mode,))
        else:
            cur.execute("SELECT * FROM conversations WHERE mode = ? AND document_id = ? ORDER BY updated_at DESC",
                        (mode, document_id))
        return _rows(cur)


def messages(conv_id: int) -> list[dict]:
    with cursor() as cur:
        cur.execute("SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id", (conv_id,))
        return _rows(cur)


def add_message(conv_id: int, role: str, content: str) -> None:
    with cursor() as cur:
        now = time.time()
        cur.execute("INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                    (conv_id, role, content, now))
        cur.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conv_id))


def set_title(conv_id: int, title: str) -> None:
    with cursor() as cur:
        cur.execute("UPDATE conversations SET title = ? WHERE id = ?", (title, conv_id))


def delete_conversation(conv_id: int) -> None:
    with cursor() as cur:
        cur.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))


# ── documents ────────────────────────────────────────────────────────────────────────────────────
def add_document(title: str, filename: str, text: str, pages: int) -> int:
    with cursor() as cur:
        cur.execute("INSERT INTO documents (title, filename, text_content, page_count, char_count, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)", (title, filename, text, pages, len(text), time.time()))
        return cur.lastrowid


def documents() -> list[dict]:
    with cursor() as cur:
        cur.execute("SELECT id, title, filename, page_count, char_count, created_at FROM documents "
                    "ORDER BY created_at DESC")
        return _rows(cur)


def document(doc_id: int) -> dict | None:
    with cursor() as cur:
        cur.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def delete_document(doc_id: int) -> None:
    with cursor() as cur:
        cur.execute("DELETE FROM documents WHERE id = ?", (doc_id,))


# ── decks ────────────────────────────────────────────────────────────────────────────────────────
def add_deck(title: str, preview: str, cards: list[dict]) -> int:
    with cursor() as cur:
        cur.execute("INSERT INTO decks (title, source_preview, created_at) VALUES (?, ?, ?)",
                    (title, preview, time.time()))
        deck_id = cur.lastrowid
        cur.executemany("INSERT INTO flashcards (deck_id, question, answer, position) VALUES (?, ?, ?, ?)",
                        [(deck_id, c["question"], c["answer"], i) for i, c in enumerate(cards)])
        return deck_id


def decks() -> list[dict]:
    with cursor() as cur:
        cur.execute("SELECT d.id, d.title, d.created_at, (SELECT COUNT(*) FROM flashcards WHERE deck_id = d.id) "
                    "AS card_count FROM decks d ORDER BY d.created_at DESC")
        return _rows(cur)


def deck(deck_id: int) -> dict | None:
    with cursor() as cur:
        cur.execute("SELECT * FROM decks WHERE id = ?", (deck_id,))
        row = cur.fetchone()
        if not row:
            return None
        cur.execute("SELECT question, answer FROM flashcards WHERE deck_id = ? ORDER BY position, id", (deck_id,))
        return {**dict(row), "cards": _rows(cur)}


def delete_deck(deck_id: int) -> None:
    with cursor() as cur:
        cur.execute("DELETE FROM decks WHERE id = ?", (deck_id,))
