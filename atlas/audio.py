"""Recording your voice (microphone -> WAV) and reading answers aloud (the system's voices)."""
from __future__ import annotations

import io
import logging
import time
import wave
from array import array

log = logging.getLogger(__name__)

RATE = 16_000                  # 16 kHz mono is what speech recognition expects
MIN_SECONDS = 0.5
MAX_SECONDS = 120


class AudioError(Exception):
    pass


def to_wav(pcm: bytes, rate: int = RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def loudness(pcm: bytes) -> float:
    """0..1, how loud the latest sound was (for the level bar)."""
    samples = array("h", pcm[: len(pcm) // 2 * 2])
    if not samples:
        return 0.0
    peak = max(abs(s) for s in samples[-1600:])
    return min(1.0, peak / 12_000)


class Recorder:
    """Microphone recording with sounddevice: start(), then stop() gives the recording as WAV bytes."""

    def __init__(self):
        self._stream = None
        self._chunks: list[bytes] = []
        self.started = 0.0

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def seconds(self) -> float:
        return time.monotonic() - self.started if self.recording else 0.0

    def level(self) -> float:
        return loudness(self._chunks[-1]) if self._chunks else 0.0

    def start(self) -> None:
        try:
            import sounddevice as sd
            self._chunks = []
            self._stream = sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=1600,
                                             callback=self._on_audio)
            self._stream.start()
            self.started = time.monotonic()
        except Exception as exc:
            self._stream = None
            log.warning("microphone failed: %s", exc)
            raise AudioError("The microphone could not be used. Check that one is connected and that this app "
                             "may use it (System Settings → Privacy & Security → Microphone).") from exc

    def _on_audio(self, data, frames, time_info, status) -> None:
        self._chunks.append(bytes(data))

    def stop(self) -> bytes:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                log.warning("closing the microphone failed", exc_info=True)
        pcm = b"".join(self._chunks)
        self._chunks = []
        if len(pcm) < RATE * 2 * MIN_SECONDS:
            raise AudioError("That was very short - hold the recording a little longer.")
        return to_wav(pcm)

    def cancel(self) -> None:
        try:
            self.stop()
        except AudioError:
            pass


class Speaker:
    """Reads text aloud with the system's voices (Qt's text-to-speech)."""

    def __init__(self, engine: str | None = None):
        self._tts = None
        self._engine = engine

    def _get(self):
        if self._tts is None:
            from PySide6.QtTextToSpeech import QTextToSpeech
            self._tts = QTextToSpeech(self._engine) if self._engine else QTextToSpeech()
        return self._tts

    def say(self, text: str) -> None:
        try:
            tts = self._get()
            tts.stop()
            tts.say(_speakable(text))
        except Exception:
            log.warning("text to speech failed", exc_info=True)

    def stop(self) -> None:
        if self._tts is not None:
            self._tts.stop()

    def speaking(self) -> bool:
        if self._tts is None:
            return False
        from PySide6.QtTextToSpeech import QTextToSpeech
        return self._tts.state() == QTextToSpeech.State.Speaking


def _speakable(text: str) -> str:
    """Drop markdown symbols so they are not read out."""
    import re
    text = re.sub(r"[*_`#>]+", "", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.M)
    return text.strip()
