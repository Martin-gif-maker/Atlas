"""Test setup: no window on screen, a fresh data folder per test, never the real keychain or the internet."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["ATLAS_NO_KEYCHAIN"] = "1"
os.environ.pop("GROQ_API_KEY", None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from atlas.core import ai_client, appbase, storage, workers  # noqa: E402

REAL_CLIENT = ai_client.client


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(storage, "_dotenv_key", lambda: "")
    monkeypatch.setattr(ai_client, "client", _no_network)
    ai_client.reset()
    yield


def _no_network():
    raise AssertionError("a test tried to reach Groq - replace the AI call with a fake")


@pytest.fixture
def app():
    return appbase.make_app(["test"])


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")


def wait_jobs(timeout_ms: int = 5000) -> None:
    """Let background jobs finish and deliver their results to the window."""
    import time
    from PySide6.QtTest import QTest
    end = time.monotonic() + timeout_ms / 1000
    while workers.busy():
        assert time.monotonic() < end, "background job did not finish"
        QTest.qWait(10)
    QTest.qWait(10)
