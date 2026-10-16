"""Atlas: the database, choosing document passages, audio helpers, and all four modes in the window.

The AI, the microphone and the speaker are fakes: no key, no internet, no sound.
"""
import wave
import io

import pymupdf
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QPushButton

from atlas import ai, audio, db
from atlas.core import ai_client
from conftest import wait_jobs


class FakeSpeaker:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)

    def stop(self):
        pass


class FakeRecorder:
    def __init__(self, wav=b"RIFF-fake"):
        self.recording, self.wav = False, wav

    def start(self):
        self.recording = True

    def stop(self):
        self.recording = False
        return self.wav

    def cancel(self):
        self.recording = False

    def seconds(self):
        return 1.0

    def level(self):
        return 0.3


@pytest.fixture
def fake_ai(monkeypatch):
    calls = {"reply": [], "titles": 0}

    def reply(history, system, max_tokens=700):
        calls["reply"].append({"history": history, "system": system})
        return f"Answer {len(calls['reply'])}"

    def title(text):
        calls["titles"] += 1
        return "A short title"

    monkeypatch.setattr(ai, "reply", reply)
    monkeypatch.setattr(ai, "make_title", title)
    monkeypatch.setattr(ai, "flashcards", lambda notes: [{"question": f"Q{i}", "answer": f"A{i}"} for i in range(1, 9)])
    monkeypatch.setattr(ai, "transcribe", lambda wav: "What is the weather like on Mars?")
    return calls


@pytest.fixture
def window(app, with_key, fake_ai):
    from atlas.window import MainWindow
    w = MainWindow(speaker=FakeSpeaker())
    w.show()
    yield w
    wait_jobs()
    w.close()


def texts(widget):
    return [lab.text() for lab in widget.findChildren(QLabel)]


def make_pdf(path, pages):
    doc = pymupdf.open()
    for text in pages:
        doc.new_page().insert_textbox(pymupdf.Rect(50, 50, 550, 800), text, fontsize=11)
    doc.save(str(path))
    return str(path)


# ── database ─────────────────────────────────────────────────────────────────────────────────────
def test_deleting_a_document_removes_its_chats():
    doc_id = db.add_document("Notes", "notes.pdf", "text", 1)
    conv = db.new_conversation("doc", "Notes", document_id=doc_id)
    db.add_message(conv, "user", "hi")
    db.delete_document(doc_id)
    assert db.conversation(conv) is None and db.messages(conv) == []


def test_decks_keep_card_order_and_delete_cleanly():
    deck = db.add_deck("Bio", "preview", [{"question": f"q{i}", "answer": f"a{i}"} for i in range(5)])
    assert [c["question"] for c in db.deck(deck)["cards"]] == ["q0", "q1", "q2", "q3", "q4"]
    assert db.decks()[0]["card_count"] == 5
    db.delete_deck(deck)
    assert db.deck(deck) is None and db.decks() == []


def test_conversation_list_is_newest_activity_first():
    old = db.new_conversation("voice", "old")
    new = db.new_conversation("voice", "new")
    db.add_message(old, "user", "back to the old one")
    assert [c["id"] for c in db.conversations("voice")] == [old, new]


# ── AI helpers ───────────────────────────────────────────────────────────────────────────────────
def test_short_documents_are_sent_whole():
    assert ai.pick_context("short text", "q", []) == "short text"


def test_long_documents_send_the_matching_passages():
    filler = "\n\n".join(f"Paragraph {i} talks about general things and nothing in particular." for i in range(600))
    text = "Annual report 2026.\n\n" + filler + "\n\nThe warranty lasts exactly 36 months from delivery.\n\n" + filler
    context = ai.pick_context(text, "How long is the warranty?", [])
    assert len(context) <= ai.DOC_BUDGET + 200
    assert "36 months" in context and context.startswith("Annual report 2026.")


def test_flashcards_in_any_shape():
    assert ai.parse_flashcards({"cards": [{"q": "Q", "a": "A"}, {"question": "no answer"}]}) == \
        [{"question": "Q", "answer": "A"}]
    assert ai.parse_flashcards([{"question": "Q", "answer": "A"}]) == [{"question": "Q", "answer": "A"}]
    assert ai.parse_flashcards({"question": "Q", "answer": "A"}) == [{"question": "Q", "answer": "A"}]


def test_title_falls_back_when_the_ai_fails(monkeypatch):
    def fail(*a, **k):
        raise ai_client.AIError("down")
    monkeypatch.setattr(ai_client, "ask_text", fail)
    assert ai.make_title("Tell me about the history of the Roman Empire please") == "Tell me about the history of the Roman…"


# ── audio helpers (no microphone, no sound) ──────────────────────────────────────────────────────
def test_wav_is_16khz_mono():
    with wave.open(io.BytesIO(audio.to_wav(b"\x00\x01" * 16000))) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()) == (16000, 1, 2, 16000)


def test_too_short_recording_is_refused():
    rec = audio.Recorder()
    rec._chunks = [b"\x00\x00" * 100]
    with pytest.raises(audio.AudioError, match="short"):
        rec.stop()


def test_markdown_is_not_read_out():
    assert audio._speakable("**Hello** _there_\n- one\n- two") == "Hello there\none\ntwo"


# ── Voice ────────────────────────────────────────────────────────────────────────────────────────
def test_voice_typed_message(window, fake_ai):
    page = window.voice
    page.chat.composer.setPlainText("Hello Atlas")
    QTest.keyClick(page.chat.composer, Qt.Key.Key_Return)
    wait_jobs()
    conv = db.conversations("voice")[0]
    assert [m["content"] for m in db.messages(conv["id"])] == ["Hello Atlas", "Answer 1"]
    assert conv["title"] == "A short title" and window.list.count() == 1
    assert window.speaker.said == ["Answer 1"]
    assert fake_ai["reply"][0]["system"] == ai.VOICE_SYSTEM


def test_voice_with_the_microphone(window, fake_ai):
    chat = window.voice.chat
    chat.recorder = FakeRecorder()
    chat.toggle_mic()
    assert chat.recorder.recording and chat.listening.isVisibleTo(window)
    chat.toggle_mic()
    wait_jobs()
    msgs = db.messages(db.conversations("voice")[0]["id"])
    assert msgs[0]["content"] == "What is the weather like on Mars?" and msgs[1]["role"] == "assistant"


def test_escape_cancels_recording(window, fake_ai):
    chat = window.voice.chat
    chat.recorder = FakeRecorder()
    chat.toggle_mic()
    window.activateWindow()
    QTest.qWaitForWindowActive(window)
    chat.composer.setFocus()
    QTest.keyClick(chat.composer, Qt.Key.Key_Escape)
    assert not chat.recorder.recording and db.conversations("voice") == []


def test_read_aloud_can_be_switched_off(window):
    window.voice.aloud.setChecked(False)
    window.voice.send("Quiet please")
    wait_jobs()
    assert window.speaker.said == []


def test_error_then_try_again(window, fake_ai, monkeypatch):
    def fail(history, system, max_tokens=700):
        raise ai_client.AIError("Groq's free limit was reached for the moment.")
    monkeypatch.setattr(ai, "reply", fail)
    window.voice.send("Hi")
    wait_jobs()
    assert any("free limit" in t for t in texts(window.voice))
    monkeypatch.setattr(ai, "reply", lambda history, system, max_tokens=700: "Back again")
    retry = [b for b in window.voice.findChildren(QPushButton) if b.text() == "Try again"][0]
    retry.click()
    wait_jobs()
    assert [m["content"] for m in db.messages(window.voice.conv_id)] == ["Hi", "Back again"]


# ── Documents ────────────────────────────────────────────────────────────────────────────────────
def test_add_a_pdf_and_ask(window, fake_ai, tmp_path):
    path = make_pdf(tmp_path / "Rental contract.pdf", ["The rent is 900 euros a month.", "Pets are allowed."])
    window.add_pdf(path)
    wait_jobs()
    assert window.current_mode() == "doc" and window.docs.currentWidget() is window.docs.chat
    assert window.docs.chat.title.text() == "Rental contract" and "2 pages" in window.docs.chat.sub.text()
    window.docs.chat.send("How much is the rent?")
    wait_jobs()
    assert "900 euros" in fake_ai["reply"][-1]["system"] and "Rental contract" in fake_ai["reply"][-1]["system"]
    assert window.list.count() == 1


def test_broken_pdf(window, tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"nope")
    window.add_pdf(str(bad))
    wait_jobs()
    assert "could not be opened" in window.docs.notice.text()


# ── Study ────────────────────────────────────────────────────────────────────────────────────────
def test_make_and_review_a_deck(window, monkeypatch):
    window.nav.setCurrentRow(2)
    page = window.study
    page.notes.setPlainText("Mitochondria are the powerhouse of the cell. They make ATP from glucose and oxygen.")
    page.go.click()
    wait_jobs()
    assert page.currentWidget() is page.review and page.counter.text() == "Card 1 of 8"
    assert page.r_title.text() == "A short title" and window.list.count() == 1
    QTest.keyClick(page.review, Qt.Key.Key_Space)
    assert page.flipped and page.flip_btn.text() == "Hide answer"
    QTest.keyClick(page.review, Qt.Key.Key_Right)
    assert page.counter.text() == "Card 2 of 8" and not page.flipped
    monkeypatch.setattr(window, "confirm", lambda *a, **k: True)
    page.delete()
    assert db.decks() == [] and page.currentWidget() is page.start_page


def test_too_short_notes(window):
    window.nav.setCurrentRow(2)
    window.study.notes.setPlainText("tiny")
    window.study.go.click()
    assert "a bit more" in window.study.notice.text()


# ── Interview ────────────────────────────────────────────────────────────────────────────────────
def test_interview_starts_with_a_question(window, fake_ai):
    window.nav.setCurrentRow(3)
    page = window.interview
    page.role.setText("Data Scientist")
    page.go.click()
    wait_jobs()
    conv = db.conversations("interview")[0]
    assert conv["role_name"] == "Data Scientist" and page.chat.title.text() == "Interview: Data Scientist"
    assert [m["role"] for m in db.messages(conv["id"])] == ["assistant"]          # the opener is not stored
    first = fake_ai["reply"][0]
    assert first["history"] == [{"role": "user", "content": ai.INTERVIEW_OPENER}]
    assert "Data Scientist" in first["system"]
    assert window.speaker.said == ["Answer 1"]
    page.chat.feedback.click()
    wait_jobs()
    assert fake_ai["reply"][-1]["history"][0]["content"] == ai.INTERVIEW_OPENER
    assert "feedback" in db.messages(conv["id"])[-2]["content"]


def test_switching_modes_keeps_each_ones_list(window, fake_ai):
    window.voice.send("One")
    wait_jobs()
    window.nav.setCurrentRow(2)
    assert window.list.count() == 0 and window.list_title.text() == "Decks"
    window.nav.setCurrentRow(0)
    assert window.list.count() == 1 and window.voice.conv_id is not None
