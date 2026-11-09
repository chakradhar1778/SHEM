"""SHEM AI Live voice: sentence chunking, WebSocket session with fake Sarvam STT/TTS, REST voice endpoints."""

from __future__ import annotations

import asyncio
import json
import time

import pytest
from starlette.websockets import WebSocketDisconnect

from app.ai import providers, sarvam
from app.ai.providers import LLMRouter
from app.ai.voice import SentenceChunker, clean_for_speech
from tests.conftest import AUTH
from tests.test_ai import ScriptedProvider, _add_appliance


class FakeSTT:
    def __init__(self, script):
        self.script = list(script)            # events emitted after the first audio chunk
        self.q: asyncio.Queue = asyncio.Queue()
        self.audio = []
        self.closed = False

    async def send_audio(self, pcm):
        self.audio.append(pcm)
        if len(self.audio) == 1:
            for ev in self.script:
                await self.q.put(ev)

    async def events(self):
        while True:
            ev = await self.q.get()
            if ev is None:
                return
            yield ev

    async def close(self):
        self.closed = True
        await self.q.put(None)


class FakeSarvam:
    configured = True

    def __init__(self, script=()):
        self.script = script
        self.spoken = []
        self.stt = None

    async def open_realtime(self, language=None):
        self.stt = FakeSTT(self.script)
        return self.stt

    async def synthesize(self, text, language):
        self.spoken.append((text, language))
        return b"RIFF" + text.encode()

    async def transcribe(self, audio, filename, content_type, language=None):
        return {"transcript": "hello", "language": "en-IN", "languageProbability": 0.9}


UTTERANCE = [
    {"event": "vad.speech_start", "utterance_idx": 0},
    {"event": "transcript.partial", "utterance_idx": 0, "text": "how much", "language": "hi-IN"},
    {"event": "vad.speech_end", "utterance_idx": 0},
    {"event": "transcript.final", "utterance_idx": 0, "text": "आज कितनी बिजली लगी?", "language": "hi-IN"},
]


@pytest.fixture
def fakes():
    def _set(script=(), turns=()):
        fs = FakeSarvam(script)
        sarvam.set_sarvam(fs)
        prov = ScriptedProvider("gemini", list(turns))
        providers.set_router(LLMRouter([prov]))
        return fs, prov
    yield _set
    sarvam.set_sarvam(None)
    providers.set_router(None)


def _recv_until(ws, pred, timeout=5.0):
    got = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = ws.receive_json()
        got.append(msg)
        if pred(msg):
            return got
    raise AssertionError(f"condition not met; got {[m.get('type') for m in got]}")


# ── units ──────────────────────────────────────────────────────────────────────

def test_clean_for_speech_strips_markdown():
    assert clean_for_speech("**2.4 kWh** today — see [chart](http://x)\n- item") == "2.4 units today — see chart item"


def test_sentence_chunker_keeps_decimals_and_merges_short_bits():
    c = SentenceChunker()
    out = []
    for piece in ["Sure. You used 2.4 kWh to", "day, which is fine. Your ", "peak was at 7 PM! Bye"]:
        out += c.feed(piece)
    out += c.flush()
    # "2.4" is not a boundary; "Sure." (too short) merges forward; the short tail is flushed together.
    assert out == ["Sure. You used 2.4 units today, which is fine.", "Your peak was at 7 PM! Bye"]


# ── live session ───────────────────────────────────────────────────────────────

def test_live_voice_turn_streams_ui_and_audio(client, fakes):
    _add_appliance(rated_watts=9)
    fs, prov = fakes(UTTERANCE, [
        ([], [("get_today_insights", {})]),
        (["आज आपने **2.4 kWh** बिजली इस्तेमाल की। ", "मैंने विवरण स्क्रीन पर दिखाया है।\n",
          '```shem-ui\n{"type":"metric_cards","items":[{"label":"Today","value":2.4,"unit":"kWh"}]}\n```\n',
          '```shem-followups\n["Show this week"]\n```'], []),
    ])
    with client.websocket_connect("/api/ai/voice/live?api_key=test-key") as ws:
        ws.send_json({"type": "start"})
        assert ws.receive_json()["type"] == "ready"
        ws.send_bytes(b"\x00\x00" * 1600)
        msgs = _recv_until(ws, lambda m: m["type"] == "turn_end")
        ws.send_json({"type": "stop"})

    types = [m["type"] for m in msgs]
    finals = [m for m in msgs if m["type"] == "transcript" and m["final"]]
    assert finals[0]["text"] == "आज कितनी बिजली लगी?" and finals[0]["language"] == "hi-IN"
    assert {"vad", "turn_start", "agent", "audio", "audio_end"} <= set(types)
    agent = [(m["event"], m["data"]) for m in msgs if m["type"] == "agent"]
    names = [n for n, _ in agent]
    assert "tool_start" in names and "component" in names and names[-1] == "done"
    audio = [m for m in msgs if m["type"] == "audio"]
    assert [a["seq"] for a in audio] == list(range(len(audio)))
    spoken = " ".join(t for t, _ in fs.spoken)
    assert "units" in spoken and "**" not in spoken and "shem" not in spoken.lower()
    assert all(lang == "hi-IN" for _, lang in fs.spoken)
    # voice-mode instructions reached the LLM, in the detected language
    assert "VOICE MODE" in prov.calls[0][0]["content"] and "hi-IN" in prov.calls[0][0]["content"]
    # the exchange is saved to the conversation (visible in Chat mode)
    cid = dict(agent)["done"]["conversationId"]
    conv = client.get(f"/api/ai/conversations/{cid}", headers=AUTH).json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]


def test_live_typed_message_and_interrupt(client, fakes):
    fs, _ = fakes((), [(["First sentence that is long enough to speak. Second sentence also long enough."], [])])
    with client.websocket_connect("/api/ai/voice/live?api_key=test-key") as ws:
        ws.send_json({"type": "start"})
        ws.receive_json()
        ws.send_json({"type": "text", "message": "hi"})
        _recv_until(ws, lambda m: m["type"] == "audio")
        ws.send_json({"type": "interrupt"})
        msgs = _recv_until(ws, lambda m: m["type"] == "turn_end")
        ws.send_json({"type": "stop"})
    assert any(m["type"] == "interrupt_playback" for m in msgs)


def test_live_rejects_bad_key_and_unconfigured(client, fakes):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/ai/voice/live?api_key=wrong") as ws:
            ws.receive_json()
    assert exc.value.code == 1008

    sarvam.set_sarvam(type("NoKey", (), {"configured": False})())
    with client.websocket_connect("/api/ai/voice/live?api_key=test-key") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error" and msg["fatal"] and "SARVAM_API_KEY" in msg["message"]


# ── REST ───────────────────────────────────────────────────────────────────────

def test_voice_rest_endpoints(client, fakes):
    fakes()
    st = client.get("/api/ai/voice/status", headers=AUTH).json()
    assert st["configured"] and st["ttsModel"] == "bulbul:v3"
    r = client.post("/api/ai/voice/speak", json={"text": "**Hello** there", "language": "te-IN"}, headers=AUTH)
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav" and r.content == b"RIFFHello there"
    r = client.post("/api/ai/voice/transcribe", content=b"\x1a\x45", headers={**AUTH, "Content-Type": "audio/webm"})
    assert r.json()["transcript"] == "hello"


def test_voice_unconfigured_rest(client):
    sarvam.set_sarvam(None)
    assert client.get("/api/ai/voice/status", headers=AUTH).json()["configured"] is False
    assert client.post("/api/ai/voice/speak", json={"text": "x"}, headers=AUTH).status_code == 503


# ── Real client against the Sarvam wire format (local mocks, no network) ──────

def test_sarvam_rest_wire_format(monkeypatch):
    import base64
    import httpx
    from app.ai.sarvam import SarvamClient
    seen = {}

    def handler(request):
        seen[request.url.path] = request
        if request.url.path == "/text-to-speech":
            return httpx.Response(200, json={"request_id": "r", "audios": [base64.b64encode(b"WAVDATA").decode()]})
        return httpx.Response(200, json={"transcript": "namaste", "language_code": "hi-IN",
                                         "language_probability": 0.97})

    c = SarvamClient("sk-test")
    c.http = httpx.AsyncClient(base_url="https://api.sarvam.ai", headers={"api-subscription-key": "sk-test"},
                               transport=httpx.MockTransport(handler))

    async def run():
        wav = await c.synthesize("Hello", "or-IN")
        stt = await c.transcribe(b"abc", "speech.webm", "audio/webm")
        return wav, stt
    wav, stt = asyncio.run(run())
    assert wav == b"WAVDATA" and stt == {"transcript": "namaste", "language": "hi-IN", "languageProbability": 0.97}
    tts_req = seen["/text-to-speech"]
    body = json.loads(tts_req.content)
    assert tts_req.headers["api-subscription-key"] == "sk-test"
    assert body["language_code"] == "od-IN" and body["model"] == "bulbul:v3" and body["speaker"] == "shubh"
    stt_req = seen["/speech-to-text"]
    assert b'name="language_code"' in stt_req.content and b"unknown" in stt_req.content
    assert b'name="file"; filename="speech.webm"' in stt_req.content


def test_sarvam_realtime_ws_wire_format(monkeypatch):
    import base64
    from urllib.parse import parse_qs, urlparse
    from websockets.asyncio.server import serve
    from app.ai.sarvam import SarvamClient
    from app.config import get_settings

    received = {}

    async def server_handler(ws):
        received["path"] = ws.request.path
        received["key"] = ws.request.headers.get("api-subscription-key")
        msg = json.loads(await ws.recv())
        received["audio"] = msg
        await ws.send(json.dumps({"event": "transcript.final", "utterance_idx": 0, "text": "hi", "language": "en-IN"}))
        received["end"] = json.loads(await ws.recv())

    async def run():
        async with serve(server_handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            monkeypatch.setattr(get_settings(), "sarvam_ws_url", f"ws://127.0.0.1:{port}")
            stt = await SarvamClient("sk-rt").open_realtime()
            await stt.send_audio(b"\x01\x02")
            async for ev in stt.events():
                received["event"] = ev
                break
            await stt.close()
            await asyncio.sleep(0.05)
    asyncio.run(run())
    url = urlparse(received["path"])
    q = parse_qs(url.query)
    assert url.path == "/speech-to-text-realtime/ws" and received["key"] == "sk-rt"
    assert q["language_code"] == ["auto"] and q["model"] == ["saaras:v3-realtime"] and q["sample_rate"] == ["16000"]
    assert q["endpointing"] == ["vad"] and q["encoding"] == ["linear16"]
    assert received["audio"] == {"event": "audio_input", "audio": base64.b64encode(b"\x01\x02").decode()}
    assert received["event"]["event"] == "transcript.final" and received["end"] == {"event": "end"}


def test_audio_before_start_keeps_conversation_id(client, fakes):
    """The browser may send mic frames before its start message; the conversationId must still be honoured."""
    fakes((), [(["Continuing our chat, this sentence is long enough."], [])])
    with client.websocket_connect("/api/ai/voice/live?api_key=test-key") as ws:
        ws.send_bytes(b"\x00\x00" * 1600)
        ws.send_json({"type": "start", "conversationId": "conv-existing"})
        assert ws.receive_json() == {"type": "ready", "conversationId": "conv-existing", "language": "auto"}
        ws.send_json({"type": "text", "message": "hi"})
        msgs = _recv_until(ws, lambda m: m["type"] == "turn_end")
        ws.send_json({"type": "stop"})
    done = next(m for m in msgs if m["type"] == "agent" and m["event"] == "done")
    assert done["data"]["conversationId"] == "conv-existing"
