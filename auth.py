"""Authentication helpers for Atlas.

Covers three concerns:
- Password hashing and verification (bcrypt, no passlib dependency)
- User creation and lookup in the database
- Session-based current-user resolution and FastAPI dependency injection
"""
from __future__ import annotations

import bcrypt
from fastapi import HTTPException, Request, status

from database import db_cursor


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
def _encode(plain: str) -> bytes:
    """Encode a plain-text password to UTF-8, capped at bcrypt's 72-byte limit."""
    return plain.encode("utf-8")[:72]


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of ``plain``.

    The resulting string is safe to store directly in the database.
    """
    return bcrypt.hashpw(_encode(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return ``True`` if ``plain`` matches the stored ``hashed`` password.

    Never raises — returns ``False`` on any error so login simply fails.
    """
    try:
        return bcrypt.checkpw(_encode(plain), hashed.encode("utf-8"))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------
def create_user(username: str, password: str, display_name: str | None = None) -> int:
    """Insert a new user row and return the new user's ID.

    Args:
        username:     Unique, lowercased username.
        password:     Plain-text password (will be hashed before storage).
        display_name: Optional human-readable name; defaults to ``username``.

    Returns:
        The ``id`` of the newly created user row.
    """
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO users (username, password_hash, display_name) VALUES (?, ?, ?)",
            (username, hash_password(password), display_name or username),
        )
        return cur.lastrowid


def get_user_by_username(username: str) -> dict | None:
    """Fetch a user row by username, or ``None`` if not found."""
    with db_cursor() as cur:
        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
        return cur.fetchone()


def get_user_by_id(user_id: int) -> dict | None:
    """Fetch a user row by primary key, or ``None`` if not found."""
    with db_cursor() as cur:
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return cur.fetchone()


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------
def current_user(request: Request) -> dict | None:
    """Return the logged-in user for this request, or ``None`` if not authenticated.

    Reads ``user_id`` from the signed session cookie and looks up the user.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return get_user_by_id(user_id)


def require_user(request: Request) -> dict:
    """FastAPI dependency that enforces authentication.

    Use with ``Depends(require_user)`` on any route that requires a login.
    Raises HTTP 401 if there is no valid session.
    """
    user = current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user
