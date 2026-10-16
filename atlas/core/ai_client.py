"""Talking to Groq: one place for the client, the model choice and readable error messages.

    ask_json(prompt, system="...")          -> dict   (the model is told to answer in JSON)
    ask_text(messages, system="...")        -> str
    transcribe(wav_bytes)                   -> str    (speech to text with Whisper on Groq)

Every failure is raised as AIError with a message that can be shown to the user as it is.
"""
from __future__ import annotations

import json
import logging
import re

from . import storage
from .texts import T

log = logging.getLogger(__name__)

# Tried in order: if Groq retires the first model, the app carries on with the next one.
MODELS = ["llama-3.3-70b-versatile", "openai/gpt-oss-120b"]
SPEECH_MODEL = "whisper-large-v3-turbo"
KEY_URL = "https://console.groq.com/keys"


class AIError(Exception):
    pass


class NoKeyError(AIError):
    pass


_client = None
_client_key = None
_model_index = 0


def client():
    global _client, _client_key
    key = storage.get_api_key()
    if not key:
        raise NoKeyError(T["err_no_key"])
    if _client is None or key != _client_key:
        from groq import Groq
        _client = Groq(api_key=key, timeout=60, max_retries=1)
        _client_key = key
    return _client


def reset() -> None:
    """Forget the client, e.g. after the key was changed in Settings."""
    global _client, _client_key
    _client = _client_key = None


def _friendly(exc: Exception) -> AIError:
    import groq
    if isinstance(exc, AIError):
        return exc
    if isinstance(exc, groq.AuthenticationError):
        return AIError(T["err_auth"])
    if isinstance(exc, groq.RateLimitError):
        return AIError(T["err_rate"])
    if isinstance(exc, groq.APITimeoutError):
        return AIError(T["err_timeout"])
    if isinstance(exc, groq.APIConnectionError):
        return AIError(T["err_connection"])
    if isinstance(exc, groq.APIStatusError):
        return AIError(T["err_status"].format(code=exc.status_code))
    return AIError(T["err_other"].format(error=exc))


def _is_model_gone(exc: Exception) -> bool:
    import groq
    if not isinstance(exc, (groq.NotFoundError, groq.BadRequestError)):
        return False
    text = str(exc).lower()
    return "model" in text and ("decommission" in text or "not found" in text or "does not exist" in text)


def _complete(messages: list[dict], **kw) -> str:
    global _model_index
    while True:
        model = MODELS[_model_index]
        try:
            resp = client().chat.completions.create(model=model, messages=messages, **kw)
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:
            if _is_model_gone(exc) and _model_index + 1 < len(MODELS):
                log.warning("model %s is not available any more - switching to %s", model, MODELS[_model_index + 1])
                _model_index += 1
                continue
            raise _friendly(exc) from exc


def parse_json(raw: str):
    """Read the model's JSON, also when it wrapped it in ``` fences or added a sentence around it."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except ValueError:
        start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
        end = max(text.rfind("}"), text.rfind("]"))
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except ValueError:
                pass
    raise AIError(T["err_unreadable"])


def ask_json(prompt: str, system: str | None = None, temperature: float = 0.7, max_tokens: int = 3000) -> dict:
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    raw = _complete(messages, temperature=temperature, max_tokens=max_tokens, response_format={"type": "json_object"})
    data = parse_json(raw)
    if not isinstance(data, dict):
        data = {"items": data}
    return data


def ask_text(messages: list[dict], system: str | None = None, temperature: float = 0.7, max_tokens: int = 1024) -> str:
    full = ([{"role": "system", "content": system}] if system else []) + list(messages)
    text = _complete(full, temperature=temperature, max_tokens=max_tokens)
    if not text:
        raise AIError(T["err_empty"])
    return text


def transcribe(wav_bytes: bytes, language: str | None = None) -> str:
    try:
        kw = {"language": language} if language else {}
        result = client().audio.transcriptions.create(model=SPEECH_MODEL, file=("speech.wav", wav_bytes), **kw)
        return (getattr(result, "text", "") or "").strip()
    except Exception as exc:
        raise _friendly(exc) from exc


def check_key(key: str) -> None:
    """Make one tiny request with `key`; raises AIError if it does not work."""
    from groq import Groq
    try:
        Groq(api_key=key.strip(), timeout=20, max_retries=0).models.list()
    except Exception as exc:
        raise _friendly(exc) from exc
