# Atlas

> **One app. Four ways to think faster.**
> Voice chat, document chat, AI flashcards, and interview practice — together at last.

Atlas is a polished, multi-mode AI web app with an Apple-grade landing page,
a unified user account system, and four distinct AI experiences sharing a
single backend.

![status](https://img.shields.io/badge/status-feature--complete-brightgreen)
![stack](https://img.shields.io/badge/stack-FastAPI%20%C2%B7%20Groq%20%C2%B7%20Whisper%20%C2%B7%20SQLite-blueviolet)

## What's inside

| Mode          | What it does                                                                |
|---------------|-----------------------------------------------------------------------------|
| **Voice**     | Hold the mic, speak, hear the answer. Whisper transcribes, Groq replies, Web Speech reads it back. |
| **Documents** | Upload a PDF, then chat with its content. Answers grounded in the file.     |
| **Study**     | Paste notes. The AI generates 8–15 high-quality flashcards. Review with smooth flips. |
| **Interview** | Pick a role. Atlas plays the interviewer — voice questions, voice answers, honest feedback. |

All four modes live behind a unified login and share the same conversation
history, sidebar, and design language.

## Stack

- **FastAPI** + Uvicorn (Python web framework)
- **OpenAI Whisper** (`whisper-1`) — speech-to-text
- **Groq** (`llama-3.3-70b-versatile`) — fast LLM for chat, flashcards, interview, titles
- **PyMuPDF** — PDF text extraction
- **SQLite** — persistent storage (users, conversations, messages, documents, decks, flashcards)
- **bcrypt** — password hashing
- **Web Speech API** — text-to-speech in the browser (free, instant)
- **Vanilla JS + Jinja2** — frontend, no build step

## Project layout

```
Atlas/
├── main.py                 FastAPI entrypoint — all routes, all 4 modes
├── database.py             SQLite schema + connection helpers
├── auth.py                 bcrypt password hashing + session helpers
├── ai_services.py          Whisper, Groq, system prompts, flashcard generator
├── requirements.txt
├── Procfile                For Render / Railway / Fly.io deploy
├── .env.example            Template for API keys
├── .gitignore
├── README.md               (this file)
├── templates/
│   ├── base.html
│   ├── _appnav.html        Reusable nav bar
│   ├── landing.html        Apple-style hero + showcase
│   ├── login.html / register.html
│   ├── dashboard.html      Mode picker
│   ├── voice.html
│   ├── doc.html
│   ├── study.html
│   └── interview.html
└── static/
    ├── css/atlas.css       Whole design system (~1,300 lines)
    └── js/
        ├── landing.js      Reveal-on-scroll animations
        └── chat-core.js    Shared chat/recording logic for voice/doc/interview
```

## Quick start

### 1. Get API keys
- **OpenAI** for Whisper STT — https://platform.openai.com/api-keys
- **Groq** for the LLM (free tier!) — https://console.groq.com/keys

### 2. Install
```bash
cd Atlas
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env       # Windows
# cp .env.example .env       # macOS / Linux
```

Open `.env` and paste your keys. Generate a session secret:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Run
```bash
uvicorn main:app --reload
```
Open http://127.0.0.1:8000 — register, hit "Open Atlas", and start exploring.

> **Mic permission:** browsers only allow microphone access on `localhost` or
> over HTTPS. Make sure you're on https:// once you deploy, or the mic button
> will silently fail.

## Architecture

```
                         ┌──────────────┐
                         │   Browser    │
                         │ ┌──────────┐ │
                         │ │ Web Speech│ │  (TTS playback)
                         │ │ MediaRec │ │  (mic record)
                         │ └──────────┘ │
                         └──────┬───────┘
                  audio / text  │  reply
                                ▼
                         ┌──────────────┐
                         │  FastAPI     │
                         │   (main.py)  │
                         └──┬───────┬───┘
                            │       │
              ┌─────────────┘       └────────────┐
              ▼                                  ▼
       ┌────────────┐                       ┌────────────┐
       │  Whisper   │  speech → text       │   Groq     │
       │  (OpenAI)  │                       │ (Llama 3.3)│
       └────────────┘                       └────────────┘
                            │
                            ▼
                     ┌─────────────┐
                     │  SQLite     │  users · conversations · messages
                     │  atlas.db   │  documents · decks · flashcards
                     └─────────────┘
```

### Database schema (high-level)

- **users** — `id`, `username`, `password_hash`, `display_name`, `created_at`
- **conversations** — `id`, `user_id`, `mode` (voice/doc/interview), `title`, `document_id?`, `role_name?`, timestamps
- **messages** — `id`, `conversation_id`, `role`, `content`, `created_at`
- **documents** — `id`, `user_id`, `title`, `text_content`, `page_count`, `char_count`
- **decks** + **flashcards** — for Study mode

Everything is foreign-keyed with `ON DELETE CASCADE`, and every API endpoint
uses `Depends(auth.require_user)` so cross-user access is blocked at the
framework level.

### Why no vector database?

For Doc Chat, Atlas just embeds the entire document text into the system
prompt rather than chunking + embeddings + ChromaDB. The reason: Groq's
Llama 3.3 has a 128k-token context window, which fits a typical book chapter
or research paper directly. This trades the ~10 lines of code for ChromaDB
for an architecture that's much simpler to reason about, deploy, and debug.
For docs >60k chars, the code transparently truncates. If you ever want true
RAG with retrieval, swap `_system_prompt_for_conv` in `main.py` for a
chunked-search version.

## Deployment

The included `Procfile` works out of the box on Render, Railway, and
Fly.io. Set these environment variables in the host's dashboard:

- `OPENAI_API_KEY`
- `GROQ_API_KEY`
- `SESSION_SECRET`

For production, swap SQLite for Postgres (only `database.py` needs to change),
and set `https_only=True` on `SessionMiddleware` in `main.py`.

## Roadmap

The bones are done; here are obvious upgrades:

- **Streaming replies** with Server-Sent Events so the assistant text appears word-by-word
- **Real-time voice mode** with WebRTC — no need to click record/stop
- **Premium TTS** — swap the Web Speech API for OpenAI's TTS or ElevenLabs
- **Tool use** in voice mode — let Atlas call functions (web search, calendar, calculator)
- **Spaced repetition** for Study mode — surface cards on a forgetting curve
- **Resume upload** in Interview mode so the AI can ask you about *your* projects
- **Export decks** to Anki / CSV
- **Dark/light toggle** (it's all-dark now; the design system already supports light sections)
- **Mobile PWA** wrapper

## License

MIT — built by Martin Genov. Use it, fork it, ship it.
