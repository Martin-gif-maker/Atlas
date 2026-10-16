"""The shared pieces: reading the AI's JSON, the API key, saved files, background jobs, the look."""
import os

import pytest

from conftest import wait_jobs
from atlas.core import ai_client, storage, theme, workers


def test_parse_json_plain_fenced_and_wrapped():
    assert ai_client.parse_json('{"a": 1}') == {"a": 1}
    assert ai_client.parse_json('```json\n{"a": 2}\n```') == {"a": 2}
    assert ai_client.parse_json('Here you go: {"a": 3} hope it helps') == {"a": 3}
    assert ai_client.parse_json('[1, 2]') == [1, 2]
    with pytest.raises(ai_client.AIError):
        ai_client.parse_json("no json here")


def test_key_from_environment_wins(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "from-env")
    assert storage.get_api_key() == "from-env"
    assert storage.key_source() == "env"


def test_key_saved_privately_without_keychain():
    assert storage.get_api_key() == ""
    storage.set_api_key("  gsk_saved  ")
    assert storage.get_api_key() == "gsk_saved"
    assert storage.key_source() == "saved"
    path = storage.data_dir() / ".groq_key"
    assert oct(os.stat(path).st_mode)[-3:] == "600"        # only the user can read it
    storage.set_api_key("")
    assert storage.get_api_key() == "" and not path.exists()


def test_missing_key_gives_a_clear_message(monkeypatch):
    from conftest import REAL_CLIENT
    monkeypatch.setattr(ai_client, "client", REAL_CLIENT)  # the real client() this time, still no key
    ai_client.reset()
    with pytest.raises(ai_client.NoKeyError, match="API key"):
        ai_client.client()


def test_json_files_survive_a_round_trip_and_bad_files():
    storage.save_json("x.json", {"hello": "свят"})
    assert storage.load_json("x.json", None) == {"hello": "свят"}
    (storage.data_dir() / "x.json").write_text("{broken")
    assert storage.load_json("x.json", "fallback") == "fallback"


def test_background_job_reports_result_and_error(app):
    got = []
    workers.run(lambda a, b: a + b, 2, 3, on_done=got.append)
    workers.run(lambda: 1 / 0, on_error=lambda msg: got.append(("error", msg)))
    wait_jobs()
    assert 5 in got and any(isinstance(g, tuple) and g[0] == "error" for g in got)


def test_friendly_errors():
    import groq
    import httpx
    req = httpx.Request("POST", "https://api.groq.com")
    auth = groq.AuthenticationError("bad", response=httpx.Response(401, request=req), body=None)
    assert "did not accept" in str(ai_client._friendly(auth))
    limit = groq.RateLimitError("slow down", response=httpx.Response(429, request=req), body=None)
    assert "limit" in str(ai_client._friendly(limit))
    assert "internet" in str(ai_client._friendly(groq.APIConnectionError(request=req)))


def test_retired_model_falls_back_to_the_next(monkeypatch):
    import groq
    import httpx
    req = httpx.Request("POST", "https://api.groq.com")
    calls = []

    class FakeCompletions:
        def create(self, model, **kw):
            calls.append(model)
            if model == ai_client.MODELS[0]:
                raise groq.BadRequestError("The model has been decommissioned",
                                           response=httpx.Response(400, request=req), body=None)
            msg = type("M", (), {"content": '{"ok": true}'})
            return type("R", (), {"choices": [type("C", (), {"message": msg})]})

    fake = type("Client", (), {"chat": type("Chat", (), {"completions": FakeCompletions()})})
    monkeypatch.setattr(ai_client, "client", lambda: fake)
    monkeypatch.setattr(ai_client, "_model_index", 0)
    assert ai_client.ask_json("hi") == {"ok": True}
    assert calls == ai_client.MODELS[:2]


def test_text_is_readable_in_both_palettes():
    def lum(h):
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
        f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)

    def contrast(a, b):
        hi, lo = sorted((lum(a), lum(b)), reverse=True)
        return (hi + 0.05) / (lo + 0.05)

    for p in (theme.PAPER, theme.GRAPHITE):
        for surface in ("window", "side", "card", "well"):
            assert contrast(p["text"], p[surface]) >= 7, surface
            assert contrast(p["muted"], p[surface]) >= 4.5, surface
        assert contrast(p["on_accent"], p["accent"]) >= 4.5
        for colour in ("accent_text", "bad", "ok"):
            assert contrast(p[colour], p["card"]) >= 4.5, colour
