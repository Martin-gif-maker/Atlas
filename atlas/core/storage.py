"""Where the app keeps its files, and the Groq API key.

Files go to the usual place for app data (on a Mac: ~/Library/Application Support/<App>). Set the
environment variable <APP>_DATA_DIR (for example FITBRAIN_DATA_DIR) to use another folder.

The API key is looked for in this order: the GROQ_API_KEY environment variable, a .env file next to the
app, then the system keychain (where the Settings window saves it). If the keychain cannot be used, the
key is kept in a file only you can read inside the data folder.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from . import APP_NAME

log = logging.getLogger(__name__)
PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
KEY_ACCOUNT = "groq_api_key"


def data_dir() -> Path:
    override = os.environ.get(f"{APP_NAME.upper()}_DATA_DIR")
    if override:
        base = Path(override)
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_NAME
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


# ── small JSON files ─────────────────────────────────────────────────────────────────────────────
def load_json(name: str, default):
    path = data_dir() / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, ValueError):
        log.warning("could not read %s - starting fresh", path)
        return default


def save_json(name: str, data) -> None:
    path = data_dir() / name
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)                             # never leaves a half-written file behind


# ── the API key ──────────────────────────────────────────────────────────────────────────────────
def _dotenv_key() -> str:
    env_file = PROJECT_DIR / ".env"
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "GROQ_API_KEY":
                value = value.strip().strip('"').strip("'")
                if value and value != "your_groq_api_key_here":
                    return value
    except OSError:
        pass
    return ""


def _key_file() -> Path:
    return data_dir() / ".groq_key"


def _keyring():
    if os.environ.get(f"{APP_NAME.upper()}_NO_KEYCHAIN"):
        return None
    try:
        import keyring
        return keyring
    except Exception:
        return None


def get_api_key() -> str:
    key = os.environ.get("GROQ_API_KEY", "").strip() or _dotenv_key()
    if key:
        return key
    kr = _keyring()
    if kr is not None:
        try:
            key = kr.get_password(APP_NAME, KEY_ACCOUNT) or ""
        except Exception as exc:
            log.warning("keychain not available: %s", exc)
    if not key:
        try:
            key = _key_file().read_text(encoding="utf-8").strip()
        except OSError:
            key = ""
    return key


def set_api_key(key: str) -> None:
    key = key.strip()
    kr = _keyring()
    if kr is not None:
        try:
            if key:
                kr.set_password(APP_NAME, KEY_ACCOUNT, key)
            else:
                try:
                    kr.delete_password(APP_NAME, KEY_ACCOUNT)
                except Exception:
                    pass
            _key_file().unlink(missing_ok=True)
            return
        except Exception as exc:
            log.warning("keychain not available, using a private file: %s", exc)
    path = _key_file()
    if key:
        path.write_text(key, encoding="utf-8")
        os.chmod(path, 0o600)
    else:
        path.unlink(missing_ok=True)


def key_source() -> str:
    """Where the key in use comes from - shown in Settings so it is clear what 'Remove' does."""
    if os.environ.get("GROQ_API_KEY", "").strip():
        return "env"
    if _dotenv_key():
        return "dotenv"
    return "saved" if get_api_key() else ""
