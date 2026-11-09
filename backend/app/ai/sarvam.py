"""
SHEM AI — Sarvam speech client

* Text-to-speech  POST {base}/text-to-speech        (Bulbul) → base64 WAV
* Speech-to-text  POST {base}/speech-to-text        (Saaras, one-shot ≤30 s upload)
* Realtime STT    {ws}/speech-to-text-realtime/ws   (Saaras, streaming PCM16 16 kHz with VAD)

Auth: `api-subscription-key` header. The key never leaves the backend.
`get_sarvam()` returns the shared client; tests swap it via `set_sarvam()`.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any, AsyncIterator, Dict, Optional, Protocol
from urllib.parse import urlencode

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

# Bulbul voices exist for these languages; anything else is spoken in the default language.
TTS_LANGUAGES = {"bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "od-IN", "pa-IN", "ta-IN", "te-IN"}
TTS_MAX_CHARS = 2500


class SarvamError(RuntimeError):
    pass


def tts_language(code: Optional[str]) -> str:
    """Map an STT language code to one Bulbul can speak."""
    s = get_settings()
    if not code:
        return s.sarvam_tts_default_language
    code = "od-IN" if code == "or-IN" else code          # realtime STT says or-IN, TTS wants od-IN
    return code if code in TTS_LANGUAGES else s.sarvam_tts_default_language


def _error_message(resp: httpx.Response) -> str:
    try:
        err = resp.json().get("error") or {}
        return f"{resp.status_code} {err.get('code', '')}: {err.get('message', resp.text[:200])}"
    except Exception:
        return f"{resp.status_code}: {resp.text[:200]}"


class RealtimeSTT(Protocol):
    async def send_audio(self, pcm16: bytes) -> None: ...
    def events(self) -> AsyncIterator[Dict[str, Any]]: ...
    async def close(self) -> None: ...


class SarvamRealtimeSTT:
    """One realtime STT session. events() yields Sarvam's JSON messages (vad.*, transcript.*, error …)."""

    def __init__(self, ws):
        self.ws = ws
        self._closed = False
        self._ping_task = asyncio.create_task(self._keepalive())

    async def _keepalive(self) -> None:
        try:
            while True:
                await asyncio.sleep(20)                     # server closes after ~60 s idle
                await self.ws.send(json.dumps({"event": "ping"}))
        except (asyncio.CancelledError, Exception):
            pass

    async def send_audio(self, pcm16: bytes) -> None:
        if self._closed or not pcm16:
            return
        await self.ws.send(json.dumps({"event": "audio_input", "audio": base64.b64encode(pcm16).decode()}))

    async def events(self) -> AsyncIterator[Dict[str, Any]]:
        async for raw in self.ws:
            if isinstance(raw, bytes):
                continue
            try:
                yield json.loads(raw)
            except json.JSONDecodeError:
                continue

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._ping_task.cancel()
        try:
            await self.ws.send(json.dumps({"event": "end"}))
        except Exception:
            pass
        try:
            await self.ws.close()
        except Exception:
            pass


class SarvamClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        s = get_settings()
        self.http = httpx.AsyncClient(base_url=s.sarvam_base_url, timeout=httpx.Timeout(30.0, connect=10.0),
                                      headers={"api-subscription-key": api_key})

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def synthesize(self, text: str, language: str) -> bytes:
        """Text → WAV bytes."""
        s = get_settings()
        body = {"text": text[:TTS_MAX_CHARS], "language_code": tts_language(language),
                "model": s.sarvam_tts_model, "speaker": s.sarvam_tts_speaker, "pace": s.sarvam_tts_pace,
                "speech_sample_rate": s.sarvam_tts_sample_rate}
        resp = await self.http.post("/text-to-speech", json=body)
        if resp.status_code != 200:
            raise SarvamError(f"TTS failed: {_error_message(resp)}")
        audios = resp.json().get("audios") or []
        if not audios:
            raise SarvamError("TTS returned no audio")
        return base64.b64decode(audios[0])

    async def transcribe(self, audio: bytes, filename: str, content_type: str,
                         language: Optional[str] = None) -> Dict[str, Any]:
        s = get_settings()
        lang = language or s.sarvam_stt_language
        data = {"model": s.sarvam_stt_rest_model, "mode": "transcribe",
                "language_code": "unknown" if lang == "auto" else lang}
        resp = await self.http.post("/speech-to-text", data=data,
                                    files={"file": (filename, audio, content_type or "application/octet-stream")})
        if resp.status_code != 200:
            raise SarvamError(f"STT failed: {_error_message(resp)}")
        j = resp.json()
        return {"transcript": j.get("transcript", ""), "language": j.get("language_code"),
                "languageProbability": j.get("language_probability")}

    async def open_realtime(self, language: Optional[str] = None) -> RealtimeSTT:
        from websockets.asyncio.client import connect

        s = get_settings()
        params = {"language_code": language or s.sarvam_stt_language, "model": s.sarvam_stt_model,
                  "mode": "transcribe", "endpointing": "vad", "encoding": "linear16", "sample_rate": "16000",
                  "silence_duration_ms": str(s.sarvam_stt_silence_ms)}
        url = f"{s.sarvam_ws_url}/speech-to-text-realtime/ws?{urlencode(params)}"
        try:
            ws = await connect(url, additional_headers={"api-subscription-key": self.api_key},
                               open_timeout=10, max_size=2 ** 22)
        except Exception as exc:
            raise SarvamError(f"Could not open Sarvam realtime STT: {exc}") from exc
        return SarvamRealtimeSTT(ws)

    async def aclose(self) -> None:
        await self.http.aclose()


_client: Optional[Any] = None


def get_sarvam():
    global _client
    if _client is None:
        _client = SarvamClient(get_settings().sarvam_api_key.strip())
    return _client


def set_sarvam(client: Optional[Any]) -> None:
    """Override (tests) or reset (None → rebuilt from settings)."""
    global _client
    _client = client
