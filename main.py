"""Atlas — FastAPI application entrypoint.

Route layout
------------
/                       Landing page (public)
/login  /register       Auth pages (public)
/logout                 POST — clears session
/app                    Dashboard (requires login)
/app/voice              Voice chat page
/app/doc                Document chat page
/app/study              Flashcard study page
/app/interview          Interview practice page
/api/...                JSON API consumed by the frontend JS
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF — imported at module level so a missing install fails fast
from dotenv import load_dotenv
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

import ai_services
import auth
from config import settings
from database import db_cursor, init_db

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

load_dotenv()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent

# All valid chat modes — kept in one place so there are no magic string duplicates.
VALID_MODES = frozenset({"voice", "doc", "interview"})


# ---------------------------------------------------------------------------
# Application lifespan (startup / shutdown)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise resources on startup; clean up on shutdown."""
    logger.info("Atlas starting up — initialising database…")
    init_db()
    logger.info("Database ready.")
    yield
    logger.info("Atlas shutting down.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Atlas", lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    same_site="lax",
    https_only=False,
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


# ---------------------------------------------------------------------------
# Template helper
# ---------------------------------------------------------------------------
def render(
    request: Request,
    template: str,
    ctx: dict | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Render a Jinja2 template and return an HTMLResponse."""
    return templates.TemplateResponse(request, template, ctx or {}, status_code=status_code)


# ===========================================================================
# Marketing + auth pages
# ===========================================================================
@app.get("/", response_class=HTMLResponse)
async def landing(request: Request) -> HTMLResponse:
    """Public landing page — visible to logged-in and anonymous users."""
    user = auth.current_user(request)
    return render(request, "landing.html", {"user": user})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    """Show the login form. Redirects to /app if the user is already logged in."""
    if auth.current_user(request):
        return RedirectResponse("/app", 302)
    return render(request, "login.html", {"error": None})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request) -> HTMLResponse:
    """Show the registration form. Redirects to /app if the user is already logged in."""
    if auth.current_user(request):
        return RedirectResponse("/app", 302)
    return render(request, "register.html", {"error": None})


@app.post("/register")
async def register_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    display_name: str = Form(""),
) -> RedirectResponse:
    """Handle new-account creation.

    Validates username length (>=3 chars) and password length (>=6 chars),
    checks for duplicate usernames, then creates the account and logs in.
    """
    username = username.strip().lower()
    display_name = display_name.strip() or username

    if len(username) < 3 or len(password) < 6:
        return render(
            request,
            "register.html",
            {"error": "Username must be 3+ chars, password 6+ chars."},
            status_code=400,
        )
    if auth.get_user_by_username(username):
        return render(
            request,
            "register.html",
            {"error": "Username is already taken."},
            status_code=400,
        )

    user_id = auth.create_user(username, password, display_name)
    request.session["user_id"] = user_id
    logger.info("New user registered: %s (id=%d)", username, user_id)
    return RedirectResponse("/app", 302)


@app.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
) -> RedirectResponse:
    """Validate credentials and create a session on success."""
    username = username.strip().lower()
    user = auth.get_user_by_username(username)
    if not user or not auth.verify_password(password, user["password_hash"]):
        return render(
            request,
            "login.html",
            {"error": "Wrong username or password."},
            status_code=401,
        )
    request.session["user_id"] = user["id"]
    logger.info("User logged in: %s (id=%d)", username, user["id"])
    return RedirectResponse("/app", 302)


@app.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    """Clear the session and redirect to the landing page."""
    request.session.clear()
    return RedirectResponse("/", 302)


# ===========================================================================
# App shell + mode pages (all require an authenticated session)
# ===========================================================================
@app.get("/app", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    """Main dashboard — mode picker shown after login."""
    user = auth.current_user(request)
    if not user:
        return RedirectResponse("/login", 302)
    return render(request, "dashboard.html", {"user": user})


@app.get("/app/voice", response_class=HTMLResponse)
async def voice_page(request: Request) -> HTMLResponse:
    """Voice chat interface."""
    user = auth.current_user(request)
    if not user:
        return RedirectResponse("/login", 302)
    return render(request, "voice.html", {"user": user})


@app.get("/app/doc", response_class=HTMLResponse)
async def doc_page(request: Request) -> HTMLResponse:
    """Document chat interface."""
    user = auth.current_user(request)
    if not user:
        return RedirectResponse("/login", 302)
    return render(request, "doc.html", {"user": user})


@app.get("/app/study", response_class=HTMLResponse)
async def study_page(request: Request) -> HTMLResponse:
    """Flashcard study interface."""
    user = auth.current_user(request)
    if not user:
        return RedirectResponse("/login", 302)
    return render(request, "study.html", {"user": user})


@app.get("/app/interview", response_class=HTMLResponse)
async def interview_page(request: Request) -> HTMLResponse:
    """AI interview practice interface."""
    user = auth.current_user(request)
    if not user:
        return RedirectResponse("/login", 302)
    return render(request, "interview.html", {"user": user})


# ===========================================================================
# Conversation helpers (shared by voice / doc / interview)
# ===========================================================================
def _get_conv(conv_id: int, user_id: int) -> dict | None:
    """Fetch a single conversation row, or None if it doesn't exist."""
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM conversations WHERE id = ? AND user_id = ?",
            (conv_id, user_id),
        )
        return cur.fetchone()


def _ensure_conv(
    conv_id: Optional[int],
    user_id: int,
    mode: str,
    document_id: Optional[int] = None,
    role_name: Optional[str] = None,
) -> int:
    """Return an existing conversation ID or create a new one.

    If ``conv_id`` is provided and belongs to the user with the same mode,
    it is reused. Otherwise a new conversation row is inserted.
    """
    if conv_id:
        existing = _get_conv(conv_id, user_id)
        if existing and existing["mode"] == mode:
            return conv_id

    with db_cursor() as cur:
        cur.execute(
            """INSERT INTO conversations (user_id, mode, document_id, role_name)
               VALUES (?, ?, ?, ?)""",
            (user_id, mode, document_id, role_name),
        )
        new_id: int = cur.lastrowid
        logger.debug("Created conversation id=%d mode=%s user=%d", new_id, mode, user_id)
        return new_id


def _load_history(conv_id: int) -> list[dict]:
    """Return all messages for a conversation as a list of role/content dicts."""
    with db_cursor() as cur:
        cur.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id ASC",
            (conv_id,),
        )
        return [{"role": row["role"], "content": row["content"]} for row in cur.fetchall()]


def _save_message(conv_id: int, role: str, content: str) -> None:
    """Persist a single message and bump the conversation's updated_at timestamp."""
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
            (conv_id, role, content),
        )
        cur.execute(
            "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (conv_id,),
        )


def _maybe_set_title(conv_id: int, first_message: str) -> None:
    """Auto-generate a conversation title from the first user message.

    Does nothing if the title has already been set (i.e. is no longer
    the default "New conversation" placeholder).
    """
    with db_cursor() as cur:
        cur.execute("SELECT title FROM conversations WHERE id = ?", (conv_id,))
        row = cur.fetchone()
        if not row or row["title"] != "New conversation":
            return

    title = ai_services.generate_title(first_message)
    with db_cursor() as cur:
        cur.execute("UPDATE conversations SET title = ? WHERE id = ?", (title, conv_id))


def _build_system_prompt(conv: dict) -> str:
    """Return the appropriate system prompt for a given conversation row."""
    mode = conv["mode"]

    if mode == "voice":
        return ai_services.VOICE_SYSTEM

    if mode == "interview":
        return ai_services.interview_system(conv["role_name"] or "general")

    if mode == "doc":
        if conv["document_id"]:
            with db_cursor() as cur:
                cur.execute(
                    "SELECT title, text_content FROM documents WHERE id = ?",
                    (conv["document_id"],),
                )
                doc = cur.fetchone()
            if doc:
                # Truncate to fit comfortably within Groq's 128k context window.
                content = (doc["text_content"] or "")[:60_000]
                return ai_services.DOC_SYSTEM_TEMPLATE.format(
                    title=doc["title"], content=content
                )
        return "You are Atlas. Help the user understand documents."

    # Fallback — should never be reached with validated mode values.
    return ai_services.VOICE_SYSTEM


def _run_turn(conv_id: int, user_id: int, user_text: str) -> dict:
    """Process one user turn: save the message, call the LLM, save the reply.

    Returns a dict with ``reply`` and ``conversation_id`` keys.
    Raises HTTP 404 if the conversation doesn't exist, 502 on LLM failure.
    """
    conv = _get_conv(conv_id, user_id)
    if not conv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    is_first_turn = not _load_history(conv_id)
    _save_message(conv_id, "user", user_text)

    history = _load_history(conv_id)
    system_prompt = _build_system_prompt(conv)

    try:
        reply = ai_services.chat_completion(history, system_prompt)
    except Exception as exc:
        logger.exception("LLM request failed for conv=%d", conv_id)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"LLM request failed: {exc}") from exc

    _save_message(conv_id, "assistant", reply)

    if is_first_turn:
        _maybe_set_title(conv_id, user_text)

    return {"reply": reply, "conversation_id": conv_id}


# ===========================================================================
# Conversation API (shared across modes)
# ===========================================================================
@app.get("/api/conversations")
async def list_conversations(
    mode: Optional[str] = None,
    user=Depends(auth.require_user),
) -> dict:
    """List all conversations for the current user, newest first.

    Optionally filter by ``mode`` query param (voice / doc / interview).
    """
    sql = (
        "SELECT id, title, mode, document_id, role_name, created_at, updated_at "
        "FROM conversations WHERE user_id = ?"
    )
    params: list = [user["id"]]
    if mode:
        sql += " AND mode = ?"
        params.append(mode)
    sql += " ORDER BY updated_at DESC"

    with db_cursor() as cur:
        cur.execute(sql, params)
        rows = [dict(row) for row in cur.fetchall()]
    return {"conversations": rows}


@app.get("/api/conversations/{conv_id}")
async def get_conversation(conv_id: int, user=Depends(auth.require_user)) -> dict:
    """Return a conversation with its full message history."""
    conv = _get_conv(conv_id, user["id"])
    if not conv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    with db_cursor() as cur:
        cur.execute(
            "SELECT role, content, created_at FROM messages "
            "WHERE conversation_id = ? ORDER BY id ASC",
            (conv_id,),
        )
        messages = [dict(row) for row in cur.fetchall()]

    return {
        "id": conv["id"],
        "title": conv["title"],
        "mode": conv["mode"],
        "document_id": conv["document_id"],
        "role_name": conv["role_name"],
        "messages": messages,
    }


@app.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: int, user=Depends(auth.require_user)) -> dict:
    """Delete a conversation and all its messages (cascaded by the DB)."""
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ?",
            (conv_id, user["id"]),
        )
        if cur.rowcount == 0:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return {"ok": True}


# ===========================================================================
# Chat endpoints (voice / doc / interview share the same shape)
# ===========================================================================
class TextChatBody(BaseModel):
    """Request body for text-based chat turns."""

    conversation_id: Optional[int] = None
    text: str
    mode: str = "voice"
    document_id: Optional[int] = None
    role_name: Optional[str] = None


@app.post("/api/chat/text")
async def chat_text(body: TextChatBody, user=Depends(auth.require_user)) -> dict:
    """Accept a plain-text user message and return the assistant's reply."""
    text = body.text.strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty message")
    if body.mode not in VALID_MODES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid mode: {body.mode!r}")

    conv_id = _ensure_conv(
        body.conversation_id,
        user["id"],
        body.mode,
        document_id=body.document_id,
        role_name=body.role_name,
    )
    return _run_turn(conv_id, user["id"], text)


@app.post("/api/chat/voice")
async def chat_voice(
    audio: UploadFile = File(...),
    conversation_id: Optional[int] = Form(None),
    mode: str = Form("voice"),
    document_id: Optional[int] = Form(None),
    role_name: Optional[str] = Form(None),
    user=Depends(auth.require_user),
) -> dict:
    """Transcribe an audio recording with Whisper, then run a chat turn."""
    if mode not in VALID_MODES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid mode: {mode!r}")

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty audio")

    try:
        transcript = ai_services.transcribe_audio(audio_bytes, audio.filename or "audio.webm")
    except Exception as exc:
        logger.exception("Transcription failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Transcription failed: {exc}") from exc

    if not transcript:
        return JSONResponse({"transcript": "", "reply": "I didn't catch that — try again?"})

    conv_id = _ensure_conv(
        conversation_id,
        user["id"],
        mode,
        document_id=document_id,
        role_name=role_name,
    )
    result = _run_turn(conv_id, user["id"], transcript)
    return {"transcript": transcript, **result}


# ===========================================================================
# Documents (Doc Chat mode)
# ===========================================================================
@app.get("/api/documents")
async def list_documents(user=Depends(auth.require_user)) -> dict:
    """List all PDFs uploaded by the current user, newest first."""
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, title, page_count, char_count, created_at "
            "FROM documents WHERE user_id = ? ORDER BY created_at DESC",
            (user["id"],),
        )
        return {"documents": [dict(row) for row in cur.fetchall()]}


@app.post("/api/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    user=Depends(auth.require_user),
) -> dict:
    """Upload a PDF, extract its text with PyMuPDF, and store it.

    Limits: PDF only, max 25 MB, must contain extractable text (not image-only).
    Returns the new document's metadata.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only PDF files are supported.")

    raw = await file.read()
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file.")
    if len(raw) > 25 * 1024 * 1024:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "PDF is too large (max 25 MB).")

    # Extract text page-by-page.
    try:
        pdf = fitz.open(stream=raw, filetype="pdf")
        pages = [page.get_text() for page in pdf]
        text_content = "\n\n".join(pages).strip()
        page_count = pdf.page_count
        pdf.close()
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Could not read PDF: {exc}") from exc

    if not text_content:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No text could be extracted. Image-only PDFs require OCR — please use a text-based PDF.",
        )

    title = file.filename.rsplit(".", 1)[0][:80] or "Untitled document"
    with db_cursor() as cur:
        cur.execute(
            """INSERT INTO documents
               (user_id, title, filename, text_content, page_count, char_count)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user["id"], title, file.filename, text_content, page_count, len(text_content)),
        )
        doc_id: int = cur.lastrowid

    logger.info("Document uploaded: id=%d title=%r pages=%d", doc_id, title, page_count)
    return {"id": doc_id, "title": title, "page_count": page_count, "char_count": len(text_content)}


@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: int, user=Depends(auth.require_user)) -> dict:
    """Delete a document and any conversations linked to it."""
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM documents WHERE id = ? AND user_id = ?",
            (doc_id, user["id"]),
        )
        if cur.rowcount == 0:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return {"ok": True}


# ===========================================================================
# Decks + Flashcards (Study mode)
# ===========================================================================
class GenerateDeckBody(BaseModel):
    """Request body for AI flashcard deck generation."""

    title: str = ""
    notes: str


@app.get("/api/decks")
async def list_decks(user=Depends(auth.require_user)) -> dict:
    """List all flashcard decks for the current user, newest first."""
    with db_cursor() as cur:
        cur.execute(
            """SELECT d.id, d.title, d.created_at,
                      (SELECT COUNT(*) FROM flashcards WHERE deck_id = d.id) AS card_count
               FROM decks d WHERE d.user_id = ? ORDER BY d.created_at DESC""",
            (user["id"],),
        )
        return {"decks": [dict(row) for row in cur.fetchall()]}


@app.get("/api/decks/{deck_id}")
async def get_deck(deck_id: int, user=Depends(auth.require_user)) -> dict:
    """Return a deck with all its flashcards."""
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM decks WHERE id = ? AND user_id = ?",
            (deck_id, user["id"]),
        )
        deck = cur.fetchone()
        if not deck:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Deck not found")

        cur.execute(
            "SELECT id, question, answer, position FROM flashcards "
            "WHERE deck_id = ? ORDER BY position, id",
            (deck_id,),
        )
        cards = [dict(row) for row in cur.fetchall()]

    return {
        "id": deck["id"],
        "title": deck["title"],
        "created_at": deck["created_at"],
        "cards": cards,
    }


@app.post("/api/decks/generate")
async def generate_deck(body: GenerateDeckBody, user=Depends(auth.require_user)) -> dict:
    """Generate AI flashcards from study notes and save them as a new deck."""
    notes = body.notes.strip()
    if len(notes) < 30:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Notes are too short (need at least 30 chars).")

    try:
        cards = ai_services.generate_flashcards(notes)
    except Exception as exc:
        logger.exception("Flashcard generation failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Flashcard generation failed: {exc}") from exc

    if not cards:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The AI didn't return any usable flashcards.")

    title = body.title.strip()[:80] or ai_services.generate_title(notes[:200])
    preview = notes[:240]

    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO decks (user_id, title, source_preview) VALUES (?, ?, ?)",
            (user["id"], title, preview),
        )
        deck_id: int = cur.lastrowid
        for position, card in enumerate(cards):
            cur.execute(
                "INSERT INTO flashcards (deck_id, question, answer, position) VALUES (?, ?, ?, ?)",
                (deck_id, card["question"], card["answer"], position),
            )

    logger.info("Deck generated: id=%d title=%r cards=%d", deck_id, title, len(cards))
    return {"id": deck_id, "title": title, "card_count": len(cards)}


@app.delete("/api/decks/{deck_id}")
async def delete_deck(deck_id: int, user=Depends(auth.require_user)) -> dict:
    """Delete a deck and all its flashcards (cascaded by the DB)."""
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM decks WHERE id = ? AND user_id = ?",
            (deck_id, user["id"]),
        )
        if cur.rowcount == 0:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Deck not found")
    return {"ok": True}


# ===========================================================================
# Interview — starts a conversation and gets the AI's opening question
# ===========================================================================
class StartInterviewBody(BaseModel):
    """Request body for starting a new interview session."""

    role_name: str


@app.post("/api/interview/start")
async def start_interview(body: StartInterviewBody, user=Depends(auth.require_user)) -> dict:
    """Create an interview conversation and return the AI's opening question.

    Unlike normal chat turns, the interview opener is AI-initiated, so we
    send a bootstrapping message to get the first question before the user
    has said anything.
    """
    role = body.role_name.strip()[:80]
    if not role:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Role name is required.")

    conv_id = _ensure_conv(None, user["id"], "interview", role_name=role)

    # Set a descriptive title up front (no user message to derive it from yet).
    interview_title = f"Interview: {role}"
    with db_cursor() as cur:
        cur.execute(
            "UPDATE conversations SET title = ? WHERE id = ?",
            (interview_title, conv_id),
        )

    # Ask the AI to open with its first question.
    system_prompt = ai_services.interview_system(role)
    try:
        opener = ai_services.chat_completion(
            [{"role": "user", "content": "Please begin the interview with your first question."}],
            system_prompt,
            temperature=0.6,
            max_tokens=200,
        )
    except Exception as exc:
        logger.exception("Failed to generate interview opener for role=%r", role)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Failed to start interview: {exc}") from exc

    _save_message(conv_id, "assistant", opener)
    logger.info("Interview started: conv=%d role=%r", conv_id, role)
    return {"conversation_id": conv_id, "title": interview_title, "opener": opener}


# ===========================================================================
# Local dev runner
# ===========================================================================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )
