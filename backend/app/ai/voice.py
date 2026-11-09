"""
SHEM AI Live — voice session over WebSocket /api/ai/voice/live

Browser ──PCM16 16 kHz──▶ backend ──▶ Sarvam realtime STT (VAD endpointing)
                                          │ transcript.final
                                          ▼
                              chat_events() (same Gemini/Groq agent + tools)
                                │ text deltas            │ components / tool events
                                ▼                        ▼
                        sentence chunker ──▶ Sarvam TTS ──▶ browser (audio + UI)

Rules
* Utterances are answered one at a time, in order (a queue).
* Barge-in: when the user starts speaking while audio is playing, the
  remaining speech of the current turn is dropped and the browser is told
  to stop playback. The agent's text/UI/tool work for that turn still
  completes (actions are never half-done).
* Every agent event is forwarded verbatim as {"type":"agent","event",...},
  so the frontend renders UI components exactly as in chat.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from fastapi import WebSocket, WebSocketDisconnect

from app.ai.agent import chat_events
from app.ai.sarvam import SarvamError, get_sarvam, tts_language
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

STT_RECONNECT_ATTEMPTS = 3
TURN_DRAIN_SECONDS = 30


# ── Text → speakable sentences ─────────────────────────────────────────────────

_BOUNDARY = re.compile(r"(?<=[.!?।॥])\s+|\n+")
MIN_SENTENCE = 24          # merge very short fragments ("Sure.") with the next sentence
MAX_SENTENCE = 260         # force a cut at a comma/space when nobody ends the sentence


def clean_for_speech(text: str) -> str:
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)          # [label](url) → label
    t = re.sub(r"`{1,3}[^`]*`{1,3}", " ", t)                     # inline code
    t = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", t, flags=re.M)   # list markers
    t = re.sub(r"^\s*#+\s*", "", t, flags=re.M)                  # headings
    t = re.sub(r"[*_~>|]+", "", t)                               # emphasis, quotes, table pipes
    t = re.sub(r"\bkWh\b", "units", t)                           # what Indian households call kWh
    t = re.sub(r"\s+", " ", t)
    return t.strip()


class SentenceChunker:
    def __init__(self) -> None:
        self.buf = ""

    def feed(self, delta: str) -> List[str]:
        self.buf += delta
        out: List[str] = []
        while True:
            m = None
            for cand in _BOUNDARY.finditer(self.buf):
                if cand.start() >= MIN_SENTENCE:
                    m = cand
                    break
            if m is None:
                if len(self.buf) > MAX_SENTENCE:
                    cut = max(self.buf.rfind(", ", 0, MAX_SENTENCE), self.buf.rfind(" ", 0, MAX_SENTENCE))
                    cut = cut if cut > MIN_SENTENCE else MAX_SENTENCE
                    out.append(self.buf[:cut + 1])
                    self.buf = self.buf[cut + 1:]
                    continue
                break
            out.append(self.buf[:m.start()])
            self.buf = self.buf[m.end():]
        return [s for s in (clean_for_speech(x) for x in out) if s]

    def flush(self) -> List[str]:
        rest, self.buf = clean_for_speech(self.buf), ""
        return [rest] if rest else []

    def reset(self) -> None:
        self.buf = ""


# ── Session ────────────────────────────────────────────────────────────────────

@dataclass
class Turn:
    id: str
    text: str
    language: Optional[str]
    speech_cancelled: bool = False
    speaking: bool = False


@dataclass
class LiveSession:
    ws: WebSocket
    mqtt_client: Any
    conversation_id: Optional[str] = None
    language: Optional[str] = None               # last detected language
    muted: bool = False
    closing: bool = False
    current: Optional[Turn] = None
    queue: "asyncio.Queue[tuple]" = field(default_factory=asyncio.Queue)
    _send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _stt: Any = None

    async def send(self, payload: Dict[str, Any]) -> None:
        if self.closing:
            return
        async with self._send_lock:
            try:
                await self.ws.send_text(json.dumps(payload, default=str, ensure_ascii=False))
            except Exception:
                self.closing = True

    async def state(self, value: str) -> None:
        await self.send({"type": "state", "state": value})

    # ── barge-in ──
    async def interrupt(self) -> None:
        turn = self.current
        if turn is not None and not turn.speech_cancelled:
            turn.speech_cancelled = True
            await self.send({"type": "interrupt_playback", "turnId": turn.id})
            if self.queue.empty():
                await self.state("listening")

    # ── browser → backend ──
    async def browser_loop(self) -> None:
        while not self.closing:
            try:
                msg = await self.ws.receive()
            except (WebSocketDisconnect, RuntimeError):
                break
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("bytes") is not None:
                if not self.muted and self._stt is not None:
                    try:
                        await self._stt.send_audio(msg["bytes"])
                    except Exception:
                        pass                      # stt_loop handles reconnects
                continue
            try:
                data = json.loads(msg.get("text") or "{}")
            except json.JSONDecodeError:
                continue
            kind = data.get("type")
            if kind == "text" and str(data.get("message", "")).strip():
                await self.enqueue(str(data["message"]).strip()[:4000], self.language)
            elif kind == "mute":
                self.muted = bool(data.get("muted"))
            elif kind == "interrupt":
                await self.interrupt()
            elif kind == "playback_done":
                if self.current is None and self.queue.empty():
                    await self.state("listening")
            elif kind == "stop":
                break
        self.closing = True

    async def enqueue(self, text: str, language: Optional[str]) -> None:
        if self.current is not None and settings.ai_voice_barge_in:
            await self.interrupt()
        await self.queue.put((text, language))

    # ── Sarvam STT → backend ──
    async def stt_loop(self) -> None:
        sarvam = get_sarvam()
        attempts = 0
        while not self.closing:
            try:
                self._stt = await sarvam.open_realtime()
                attempts = 0
                async for ev in self._stt.events():
                    await self._on_stt_event(ev)
                    if self.closing:
                        break
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Sarvam realtime STT error: %s", exc)
            finally:
                if self._stt is not None:
                    await self._stt.close()
                    self._stt = None
            if self.closing:
                break
            attempts += 1
            if attempts > STT_RECONNECT_ATTEMPTS:
                await self.send({"type": "error", "fatal": True,
                                 "message": "Lost the speech-recognition connection. Please restart Live."})
                self.closing = True
                break
            await asyncio.sleep(0.5 * attempts)

    async def _on_stt_event(self, ev: Dict[str, Any]) -> None:
        kind = ev.get("event")
        if kind == "vad.speech_start":
            await self.send({"type": "vad", "speaking": True})
            if settings.ai_voice_barge_in and self.current is not None and self.current.speaking:
                await self.interrupt()
        elif kind == "vad.speech_end":
            await self.send({"type": "vad", "speaking": False})
        elif kind == "transcript.partial":
            await self.send({"type": "transcript", "final": False, "text": ev.get("text", ""),
                             "language": ev.get("language")})
        elif kind == "transcript.final":
            text = (ev.get("text") or "").strip()
            if ev.get("language"):
                self.language = ev["language"]
            await self.send({"type": "transcript", "final": True, "text": text, "language": self.language})
            if text:
                await self.enqueue(text, self.language)
        elif kind == "error":
            logger.warning("Sarvam STT reported: %s", ev)
            if ev.get("is_fatal"):
                raise SarvamError(ev.get("message") or "STT error")

    # ── turns ──
    async def turn_loop(self) -> None:
        while not self.closing:
            text, language = await self.queue.get()
            try:
                await self.run_turn(text, language)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Live turn failed")
                await self.send({"type": "error", "fatal": False, "message": "That turn failed — please try again."})
            finally:
                self.current = None
            if self.queue.empty():
                await self.state("listening")

    async def run_turn(self, text: str, language: Optional[str]) -> None:
        turn = Turn(id=f"turn-{uuid.uuid4().hex[:10]}", text=text, language=language)
        self.current = turn
        await self.send({"type": "turn_start", "turnId": turn.id, "text": text})
        await self.state("thinking")

        sentences: "asyncio.Queue[Optional[str]]" = asyncio.Queue()
        speaker = asyncio.create_task(self._speak(turn, sentences))
        chunker = SentenceChunker()
        try:
            async for e in chat_events(text, self.conversation_id, self.mqtt_client,
                                       voice_language=language or "auto-detected"):
                name, data = e["event"], e["data"]
                if name == "conversation":
                    self.conversation_id = data.get("conversationId")
                await self.send({"type": "agent", "turnId": turn.id, "event": name, "data": data})
                if name == "text":
                    for s in chunker.feed(data.get("delta", "")):
                        await sentences.put(s)
                elif name == "reset":
                    chunker.reset()
                elif name == "error":
                    await sentences.put(clean_for_speech(data.get("message", "")))
            for s in chunker.flush():
                await sentences.put(s)
        finally:
            await sentences.put(None)
            await speaker
        await self.send({"type": "audio_end", "turnId": turn.id})
        await self.send({"type": "turn_end", "turnId": turn.id})

    async def _speak(self, turn: Turn, sentences: "asyncio.Queue[Optional[str]]") -> None:
        sarvam = get_sarvam()
        lang = tts_language(turn.language)
        seq = 0
        while True:
            sentence = await sentences.get()
            if sentence is None:
                return
            if turn.speech_cancelled or self.closing or not sentence:
                continue
            try:
                wav = await sarvam.synthesize(sentence, lang)
            except Exception as exc:
                logger.warning("Sarvam TTS failed: %s", exc)
                await self.send({"type": "error", "fatal": False, "message": "Couldn't speak that sentence."})
                continue
            if turn.speech_cancelled:
                continue
            if not turn.speaking:
                turn.speaking = True
                await self.state("speaking")
            await self.send({"type": "audio", "turnId": turn.id, "seq": seq, "format": "wav",
                             "audio": base64.b64encode(wav).decode(), "text": sentence})
            seq += 1

    async def run(self) -> None:
        tasks = [asyncio.create_task(self.browser_loop(), name="live-browser"),
                 asyncio.create_task(self.stt_loop(), name="live-stt"),
                 asyncio.create_task(self.turn_loop(), name="live-turns")]
        await self.send({"type": "ready", "conversationId": self.conversation_id,
                         "language": settings.sarvam_stt_language})
        await self.state("listening")
        try:
            # The session lasts as long as the browser side (or until a fatal STT failure).
            await asyncio.wait(tasks[:2], return_when=asyncio.FIRST_COMPLETED)
            self.closing = True              # no more sends / speech; no new turns start
            # An in-flight turn may have run tools — let it finish so it's persisted.
            if self.current is not None:
                await asyncio.wait([tasks[2]], timeout=TURN_DRAIN_SECONDS)
        finally:
            self.closing = True
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if self._stt is not None:
                await self._stt.close()


async def handle_live(ws: WebSocket, mqtt_client: Any) -> None:
    """Entry point used by the /api/ai/voice/live route (after auth + accept)."""
    start: Dict[str, Any] = {}

    async def wait_for_start() -> None:
        # Mic audio may arrive before the client's "start" message — skip binary frames until it does.
        nonlocal start
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect()
            if msg.get("text"):
                try:
                    data = json.loads(msg["text"])
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict) and data.get("type") == "start":
                    start = data
                    return

    try:
        await asyncio.wait_for(wait_for_start(), timeout=15)
    except WebSocketDisconnect:
        return
    except asyncio.TimeoutError:
        pass
    session = LiveSession(ws=ws, mqtt_client=mqtt_client,
                          conversation_id=(start.get("conversationId") or None) if isinstance(start, dict) else None)
    await session.run()
    try:
        await ws.close()
    except Exception:
        pass
