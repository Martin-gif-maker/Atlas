"""Atlas's AI: the four modes' prompts, titles, flashcards, choosing document passages, and speech to text."""
from __future__ import annotations

import logging
import math
import re
from collections import Counter

from .core import ai_client

log = logging.getLogger(__name__)

VOICE_SYSTEM = (
    "You are Atlas, a friendly voice assistant. Replies will be read aloud, so "
    "stay conversational and concise (1-4 sentences). Avoid markdown, bullet "
    "lists, or anything that won't sound natural when spoken."
)

DOC_SYSTEM = (
    "You are Atlas, helping the user understand a specific document. Use ONLY "
    "the document below to answer. If the answer is not in the document, say "
    "you don't see it in the document. Quote the document where helpful, but "
    "keep answers focused.\n\n"
    "DOCUMENT: {title}\n"
    "----- BEGIN DOCUMENT -----\n{content}\n----- END DOCUMENT -----"
)

ROLES = ["Junior AI Engineer", "Frontend Developer (React)", "Data Scientist", "Product Manager",
         "Backend Engineer (Python)"]
INTERVIEW_OPENER = "Please begin the interview with your first question."


def interview_system(role_name: str) -> str:
    return (
        f"You are an experienced hiring manager interviewing a candidate for a "
        f"{role_name} role. Conduct a realistic interview: ask one question at "
        f"a time, listen to the answer, then ask a relevant follow-up or move "
        f"to the next question. Mix behavioural and technical questions. After "
        f"the user has answered ~5 questions or asks for feedback, give a "
        f"short, honest assessment of how they did and one concrete tip. Keep "
        f"each message short — this is spoken out loud."
    )


def reply(history: list[dict], system: str, max_tokens: int = 700) -> str:
    return ai_client.ask_text(history[-20:], system=system, temperature=0.7, max_tokens=max_tokens)


def make_title(first_message: str) -> str:
    """A 3-5 word title for a conversation; falls back to the start of the message."""
    try:
        title = ai_client.ask_text(
            [{"role": "user", "content": first_message[:500]}],
            system="Create a 3-5 word title for the following user message. "
                   "Reply with ONLY the title — no quotes, no trailing punctuation.",
            temperature=0.3, max_tokens=20)
        title = title.strip().strip("\"'").rstrip(".")
        return title[:60] or fallback_title(first_message)
    except ai_client.AIError:
        return fallback_title(first_message)


def fallback_title(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= 40:
        return text or "New conversation"
    cut = text[:40].rsplit(" ", 1)[0] if " " in text[:40] else text[:40]
    return cut.rstrip(",.;:") + "…"


# ── documents: send the whole text when it is short, otherwise the passages that match best ─────────
DOC_BUDGET = 14_000           # characters of document per question (about 3,500 tokens)
PASSAGE = 1_200


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"\w+", text.lower()) if len(w) > 2]


def pick_context(text: str, question: str, history: list[dict], budget: int = DOC_BUDGET) -> str:
    if len(text) <= budget:
        return text
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    passages, current = [], ""
    for para in paragraphs:                               # glue paragraphs into ~1,200 character passages
        if current and len(current) + len(para) > PASSAGE:
            passages.append(current)
            current = ""
        current = f"{current}\n\n{para}".strip()
        while len(current) > PASSAGE * 2:
            passages.append(current[:PASSAGE])
            current = current[PASSAGE:]
    if current:
        passages.append(current)
    recent = " ".join(m["content"] for m in history[-2:] if m["role"] == "user")
    query = Counter(_words(question) * 2 + _words(recent))
    docs = [Counter(_words(p)) for p in passages]
    n = len(docs)
    df = Counter(w for d in docs for w in set(d))
    avg = sum(sum(d.values()) for d in docs) / max(n, 1)

    def bm25(d: Counter) -> float:                        # the classic keyword-search score
        length = sum(d.values()) or 1
        score = 0.0
        for word in query:
            if word in d:
                idf = math.log(1 + (n - df[word] + 0.5) / (df[word] + 0.5))
                tf = d[word]
                score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / avg))
        return score

    ranked = sorted(range(n), key=lambda i: bm25(docs[i]), reverse=True)
    chosen, used = [0], len(passages[0])                  # the start usually says what the document is
    for i in ranked:
        if i not in chosen and used + len(passages[i]) <= budget:
            chosen.append(i)
            used += len(passages[i])
    return "\n\n[…]\n\n".join(passages[i] for i in sorted(chosen))


def doc_system(title: str, text: str, question: str, history: list[dict]) -> str:
    return DOC_SYSTEM.format(title=title, content=pick_context(text, question, history))


def read_pdf(path: str) -> tuple[str, int]:
    """(text, page count) of a PDF; raises AIError with a readable message when it can't be used."""
    import pymupdf
    try:
        pdf = pymupdf.open(path)
    except Exception as exc:
        raise ai_client.AIError("This file could not be opened as a PDF.") from exc
    try:
        if pdf.needs_pass:
            raise ai_client.AIError("This PDF is protected with a password.")
        text = "\n\n".join(page.get_text() for page in pdf).strip()
        pages = pdf.page_count
    finally:
        pdf.close()
    if not text:
        raise ai_client.AIError("No text found in this PDF. It may be a scanned image - try a PDF with real text.")
    return text, pages


# ── flashcards ───────────────────────────────────────────────────────────────────────────────────
FLASHCARD_SYSTEM = (
    "You are a study coach. Given study notes from the user, generate "
    "high-quality flashcards. Aim for 8-15 cards. Each card has a clear, "
    "specific question and a concise answer (1-3 sentences). Cover the key "
    "concepts, definitions, and relationships from the notes — not trivia.\n\n"
    'Reply with ONLY a valid JSON object: {"flashcards": [{"question": "...", "answer": "..."}]}. '
    "No markdown, no commentary, no code fences."
)


def flashcards(notes: str) -> list[dict]:
    raw = ai_client.ask_json(notes[:8_000], system=FLASHCARD_SYSTEM, temperature=0.4, max_tokens=2_000)
    cards = parse_flashcards(raw)
    if not cards:
        raise ai_client.AIError("The AI didn't return any usable flashcards. Try again with more notes.")
    return cards


def parse_flashcards(data) -> list[dict]:
    """Accepts {"flashcards": [...]}, {"cards": [...]}, a bare list, or one card; keeps only complete cards."""
    if isinstance(data, dict):
        for key in ("flashcards", "cards", "items", "data"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            data = [data]
    out = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        q = str(item.get("question") or item.get("q") or "").strip()
        a = str(item.get("answer") or item.get("a") or "").strip()
        if q and a:
            out.append({"question": q[:400], "answer": a[:1_000]})
    return out


def transcribe(wav: bytes) -> str:
    return ai_client.transcribe(wav)
