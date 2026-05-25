"""AI service wrappers for Atlas.

Provides:
- ``transcribe_audio``  — Whisper speech-to-text via OpenAI
- ``chat_completion``   — LLM chat via Groq (Llama 3.3 70B)
- ``generate_title``    — Short title from a user message
- ``generate_flashcards`` — Flashcard list from study notes

Clients are initialised lazily on first use so that the module can be
imported without requiring API keys to be present at import time (useful
for testing and tooling).
"""
from __future__ import annotations

import io
import json
import logging
from typing import Iterable

from groq import Groq
from openai import OpenAI

from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM configuration
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "llama-3.3-70b-versatile"

# ---------------------------------------------------------------------------
# Lazy client singletons
# ---------------------------------------------------------------------------
_openai_client: OpenAI | None = None
_groq_client: Groq | None = None


def _get_openai() -> OpenAI:
    """Return the shared OpenAI client, creating it on first call."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=settings.openai_api_key)
    return _openai_client


def _get_groq() -> Groq:
    """Return the shared Groq client, creating it on first call."""
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=settings.groq_api_key)
    return _groq_client


# ---------------------------------------------------------------------------
# Speech-to-text
# ---------------------------------------------------------------------------
def transcribe_audio(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    """Transcribe raw audio bytes to text using OpenAI Whisper.

    Args:
        audio_bytes: Raw audio data (webm, mp4, wav, etc.).
        filename:    Original filename, used to hint the audio format to Whisper.

    Returns:
        The transcribed text, stripped of leading/trailing whitespace.
    """
    buf = io.BytesIO(audio_bytes)
    buf.name = filename  # Whisper uses the extension to detect the codec.
    result = _get_openai().audio.transcriptions.create(model="whisper-1", file=buf)
    return (result.text or "").strip()


# ---------------------------------------------------------------------------
# LLM chat
# ---------------------------------------------------------------------------
def chat_completion(
    history: Iterable[dict],
    system_prompt: str,
    *,
    temperature: float = 0.7,
    max_tokens: int = 700,
) -> str:
    """Send a conversation to the Groq LLM and return the assistant's reply.

    Args:
        history:       List of ``{"role": ..., "content": ...}`` dicts.
        system_prompt: System message prepended to the conversation.
        temperature:   Sampling temperature (0 = deterministic, 1 = creative).
        max_tokens:    Maximum tokens in the reply.

    Returns:
        The assistant message content as a plain string.
    """
    messages = [{"role": "system", "content": system_prompt}, *history]
    response = _get_groq().chat.completions.create(
        model=DEFAULT_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return (response.choices[0].message.content or "").strip()


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------
VOICE_SYSTEM = (
    "You are Atlas, a friendly voice assistant. Replies will be read aloud, so "
    "stay conversational and concise (1-4 sentences). Avoid markdown, bullet "
    "lists, or anything that won't sound natural when spoken."
)

DOC_SYSTEM_TEMPLATE = (
    "You are Atlas, helping the user understand a specific document. Use ONLY "
    "the document below to answer. If the answer is not in the document, say "
    "you don't see it in the document. Quote the document where helpful, but "
    "keep answers focused.\n\n"
    "DOCUMENT: {title}\n"
    "----- BEGIN DOCUMENT -----\n{content}\n----- END DOCUMENT -----"
)


def interview_system(role_name: str) -> str:
    """Build the system prompt for an AI mock-interview session.

    Args:
        role_name: The job role being practised (e.g. "Python Backend Developer").

    Returns:
        A system prompt that instructs the LLM to act as an interviewer.
    """
    return (
        f"You are an experienced hiring manager interviewing a candidate for a "
        f"{role_name} role. Conduct a realistic interview: ask one question at "
        f"a time, listen to the answer, then ask a relevant follow-up or move "
        f"to the next question. Mix behavioural and technical questions. After "
        f"the user has answered ~5 questions or asks for feedback, give a "
        f"short, honest assessment of how they did and one concrete tip. Keep "
        f"each message short — this is spoken out loud."
    )


# ---------------------------------------------------------------------------
# Title generation
# ---------------------------------------------------------------------------
def generate_title(first_user_message: str) -> str:
    """Generate a short (3-5 word) conversation title from the first user message.

    Falls back to a truncated version of the message if the LLM call fails.
    """
    try:
        response = _get_groq().chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Create a 3-5 word title for the following user message. "
                        "Reply with ONLY the title — no quotes, no trailing punctuation."
                    ),
                },
                {"role": "user", "content": first_user_message},
            ],
            temperature=0.3,
            max_tokens=20,
        )
        title = (response.choices[0].message.content or "").strip().strip("\"'")
        return title[:60] or "New conversation"
    except Exception:
        logger.warning("Title generation failed — using message excerpt instead.")
        return first_user_message[:40] or "New conversation"


# ---------------------------------------------------------------------------
# Flashcard generation
# ---------------------------------------------------------------------------
FLASHCARD_SYSTEM = (
    "You are a study coach. Given study notes from the user, generate "
    "high-quality flashcards. Aim for 8-15 cards. Each card has a clear, "
    "specific question and a concise answer (1-3 sentences). Cover the key "
    "concepts, definitions, and relationships from the notes — not trivia.\n\n"
    "Reply with ONLY a valid JSON array of objects with keys 'question' and "
    "'answer'. No markdown, no commentary, no code fences."
)


def generate_flashcards(notes: str) -> list[dict]:
    """Generate a list of flashcards from study notes using the LLM.

    Args:
        notes: Raw study notes supplied by the user.

    Returns:
        A list of ``{"question": str, "answer": str}`` dicts.
        Returns an empty list if parsing fails entirely.
    """
    response = _get_groq().chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {"role": "system", "content": FLASHCARD_SYSTEM},
            {"role": "user", "content": notes[:8_000]},
        ],
        temperature=0.4,
        max_tokens=2_000,
        response_format={"type": "json_object"},
    )
    raw = (response.choices[0].message.content or "").strip()
    return _parse_flashcards(raw)


def _parse_flashcards(raw: str) -> list[dict]:
    """Parse the LLM's JSON output into a validated list of flashcard dicts.

    Handles common variations the model sometimes produces despite instructions:
    - Wrapping the array in a ``{"flashcards": [...]}`` envelope
    - Adding code fences around the JSON
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Strip accidental code fences (```json ... ```)
        cleaned = raw.strip().strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
        data = json.loads(cleaned)

    # Unwrap common envelope shapes: {"flashcards": [...]} or {"cards": [...]}
    if isinstance(data, dict):
        for key in ("flashcards", "cards", "items", "data"):
            if key in data and isinstance(data[key], list):
                data = data[key]
                break
        else:
            data = [data]  # single card returned as an object

    out: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        question = (item.get("question") or item.get("q") or "").strip()
        answer = (item.get("answer") or item.get("a") or "").strip()
        if question and answer:
            out.append({"question": question[:400], "answer": answer[:1_000]})

    return out
