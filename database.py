"""SQLite database layer for Atlas.

Tables
------
users          : registered accounts
conversations  : a single chat session, scoped to a mode and a user
messages       : individual messages inside a conversation
documents      : PDFs uploaded for Doc Chat mode
decks          : flashcard decks for Study mode
flashcards     : individual flashcards inside a deck

All tables use ``ON DELETE CASCADE`` so that deleting a parent row (e.g. a
user or a conversation) automatically removes all child rows without needing
application-level cleanup.

Usage
-----
Use the ``db_cursor`` context manager for every database operation::

    from database import db_cursor

    with db_cursor() as cur:
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()  # returns sqlite3.Row — access fields by name
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from config import settings


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------
def get_connection() -> sqlite3.Connection:
    """Open and configure a SQLite connection.

    ``row_factory`` is set to ``sqlite3.Row`` so columns can be accessed
    by name (``row["username"]``) as well as by index.
    Foreign-key enforcement is enabled for every connection.
    """
    conn = sqlite3.connect(settings.atlas_db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_cursor() -> Iterator[sqlite3.Cursor]:
    """Context manager that yields a cursor, commits on success, and always closes.

    Example::

        with db_cursor() as cur:
            cur.execute("INSERT INTO users ...")
            new_id = cur.lastrowid
        # Connection is committed and closed here.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name  TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    mode        TEXT NOT NULL CHECK (mode IN ('voice', 'doc', 'interview')),
    title       TEXT NOT NULL DEFAULT 'New conversation',
    document_id INTEGER,
    role_name   TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id)     REFERENCES users(id)     ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content         TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS documents (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    title        TEXT NOT NULL,
    filename     TEXT,
    text_content TEXT NOT NULL,
    page_count   INTEGER DEFAULT 0,
    char_count   INTEGER DEFAULT 0,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS decks (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,
    title          TEXT NOT NULL,
    source_preview TEXT,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS flashcards (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    deck_id  INTEGER NOT NULL,
    question TEXT NOT NULL,
    answer   TEXT NOT NULL,
    position INTEGER DEFAULT 0,
    FOREIGN KEY (deck_id) REFERENCES decks(id) ON DELETE CASCADE
);

-- Indexes to speed up the most common lookups.
CREATE INDEX IF NOT EXISTS idx_conv_user     ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conv_mode     ON conversations(user_id, mode);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_docs_user     ON documents(user_id);
CREATE INDEX IF NOT EXISTS idx_decks_user    ON decks(user_id);
CREATE INDEX IF NOT EXISTS idx_cards_deck    ON flashcards(deck_id);
"""


def init_db() -> None:
    """Create all tables and indexes if they do not already exist.

    Safe to call on every startup — uses ``CREATE ... IF NOT EXISTS`` throughout.
    """
    with db_cursor() as cur:
        cur.executescript(_SCHEMA_SQL)
