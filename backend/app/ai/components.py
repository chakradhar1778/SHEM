"""
SHEM AI — UI components embedded in assistant replies

The model writes normal Markdown and drops components in as fenced blocks:

    ```shem-ui
    {"type": "metric_cards", "items": [{"label": "Today", "value": 2.4, "unit": "kWh"}]}
    ```
    ```shem-followups
    ["Show this week's trend", "Turn off the bulb"]
    ```

StreamSegmenter consumes the token stream, emits plain text deltas
immediately, hides the fenced blocks and emits each validated component as
its own event. The final reply is an ordered list of segments:

    [{"type": "text", "content": "..."}, {"type": "component", "component": {...}}, ...]

Invalid component JSON is dropped (logged), never shown as raw text.
"""

from __future__ import annotations

import copy
import json
import logging
import re
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import Field, TypeAdapter, ValidationError, field_validator

from app.models.schemas import ApiModel

logger = logging.getLogger(__name__)

Tone = Literal["good", "warn", "bad", "neutral", "info"]
Scalar = Union[float, int, str, None]


# ── Component models ───────────────────────────────────────────────────────────

class MetricItem(ApiModel):
    label: str = Field(max_length=60)
    value: Union[float, int, str]
    unit: Optional[str] = Field(None, max_length=16)
    delta: Optional[str] = Field(None, max_length=40)        # e.g. "+12% vs last week"
    trend: Optional[Literal["up", "down", "flat"]] = None
    tone: Optional[Tone] = None


class MetricCards(ApiModel):
    type: Literal["metric_cards"]
    title: Optional[str] = None
    items: List[MetricItem] = Field(min_length=1, max_length=6)


class ChartPoint(ApiModel):
    x: Union[str, float, int]
    y: Optional[float] = None


class ChartSeries(ApiModel):
    name: str = Field(max_length=60)
    points: List[ChartPoint] = Field(min_length=1, max_length=500)


class Chart(ApiModel):
    type: Literal["chart"]
    chart_type: Literal["line", "bar", "area"] = "line"
    title: Optional[str] = None
    x_label: Optional[str] = None
    y_label: Optional[str] = None
    unit: Optional[str] = None
    series: List[ChartSeries] = Field(min_length=1, max_length=4)


class BreakdownItem(ApiModel):
    label: str = Field(max_length=60)
    value: float
    unit: Optional[str] = None


class Breakdown(ApiModel):
    """Share of a whole (donut / stacked bar)."""
    type: Literal["breakdown"]
    title: Optional[str] = None
    unit: Optional[str] = None
    items: List[BreakdownItem] = Field(min_length=1, max_length=12)


class Progress(ApiModel):
    type: Literal["progress"]
    label: str
    current: float
    target: float
    unit: Optional[str] = None
    caption: Optional[str] = None
    tone: Optional[Tone] = None


class Table(ApiModel):
    type: Literal["table"]
    title: Optional[str] = None
    columns: List[str] = Field(min_length=1, max_length=8)
    rows: List[List[Scalar]] = Field(default_factory=list, max_length=50)

    @field_validator("rows")
    @classmethod
    def _fit_rows(cls, rows, info):
        cols = len(info.data.get("columns") or [])
        return [(r + [None] * cols)[:cols] for r in rows] if cols else rows


class ApplianceCard(ApiModel):
    """The frontend loads the appliance live and shows an on/off toggle if it is relay-linked."""
    type: Literal["appliance_card"]
    appliance_id: str
    name: Optional[str] = None


class RelayControl(ApiModel):
    """Live relay widget (state from the WebSocket, toggle sends a relay command)."""
    type: Literal["relay_control"]
    channel: int = 1
    label: Optional[str] = None


class Alert(ApiModel):
    type: Literal["alert"]
    severity: Literal["info", "warning", "critical", "success"] = "info"
    title: str = Field(max_length=120)
    message: str = Field(max_length=600)
    conflict_id: Optional[str] = None


class RecommendationItem(ApiModel):
    title: str = Field(max_length=120)
    description: str = Field(max_length=400)
    impact: Optional[str] = Field(None, max_length=60)    # e.g. "Save ~₹120/month"
    priority: Optional[Literal["high", "medium", "low"]] = None


class Recommendations(ApiModel):
    type: Literal["recommendations"]
    title: Optional[str] = None
    items: List[RecommendationItem] = Field(min_length=1, max_length=6)


class ActionButton(ApiModel):
    label: str = Field(max_length=40)
    prompt: str = Field(max_length=300)        # sent to SHEM AI as the user's next message


class ActionButtons(ApiModel):
    type: Literal["action_buttons"]
    buttons: List[ActionButton] = Field(min_length=1, max_length=4)


class BillCard(ApiModel):
    type: Literal["bill_card"]
    bill_id: str


class TimelineItem(ApiModel):
    time: str = Field(max_length=40)
    title: str = Field(max_length=120)
    description: Optional[str] = Field(None, max_length=300)


class Timeline(ApiModel):
    type: Literal["timeline"]
    title: Optional[str] = None
    items: List[TimelineItem] = Field(min_length=1, max_length=20)


class ActionResult(ApiModel):
    """Produced by the backend (not the model) after a state-changing tool call."""
    type: Literal["action_result"]
    tool: str
    status: Literal["success", "pending", "error"]
    title: str
    detail: Optional[str] = None
    entity_type: Optional[str] = None          # appliance | relay | bill | target | room | household
    entity_id: Optional[str] = None
    command_id: Optional[str] = None           # relay commands: track via relay_update WS events


Component = Annotated[
    Union[MetricCards, Chart, Breakdown, Progress, Table, ApplianceCard, RelayControl, Alert,
          Recommendations, ActionButtons, BillCard, Timeline, ActionResult],
    Field(discriminator="type"),
]
_ADAPTER: TypeAdapter = TypeAdapter(Component)


def validate_component(raw: Any) -> Optional[Dict[str, Any]]:
    try:
        return _ADAPTER.validate_python(raw).model_dump(mode="json", by_alias=True, exclude_none=True)
    except ValidationError as exc:
        logger.info("Dropped invalid AI component (%s): %s", raw.get("type") if isinstance(raw, dict) else "?",
                    exc.errors()[:3])
        return None


# Description given to the model (kept short; examples are the spec).
CATALOGUE = """\
UI COMPONENTS — make answers visual. Put a component on its own lines as a fenced block:
```shem-ui
{ ...one JSON object (or a JSON array of objects)... }
```
Available types (camelCase keys, valid JSON only, no comments):
- metric_cards: {"type":"metric_cards","title?":"","items":[{"label":"Today","value":2.41,"unit":"kWh","delta?":"+8% vs avg","trend?":"up|down|flat","tone?":"good|warn|bad|neutral|info"}]}  (1-6 items)
- chart: {"type":"chart","chartType":"line|bar|area","title":"","unit":"kWh","xLabel?":"","yLabel?":"","series":[{"name":"Usage","points":[{"x":"6 AM","y":0.12}]}]}  (1-4 series)
- breakdown: {"type":"breakdown","title":"","unit":"kWh","items":[{"label":"Lights","value":1.2}]}  (shares of a whole)
- progress: {"type":"progress","label":"Monthly budget","current":820,"target":1500,"unit":"₹","caption?":"","tone?":"good"}
- table: {"type":"table","title?":"","columns":["Appliance","Watts"],"rows":[["Fan",75]]}
- appliance_card: {"type":"appliance_card","applianceId":"app-1a2b3c4d"}  (live card with on/off toggle; use real ids)
- relay_control: {"type":"relay_control","channel":1}  (live relay switch)
- alert: {"type":"alert","severity":"info|warning|critical|success","title":"","message":"","conflictId?":""}
- recommendations: {"type":"recommendations","items":[{"title":"","description":"","impact?":"Save ~₹90/month","priority?":"high|medium|low"}]}
- action_buttons: {"type":"action_buttons","buttons":[{"label":"Turn it off","prompt":"Turn off the living room bulb"}]}  (1-4)
- bill_card: {"type":"bill_card","billId":"bill-1a2b3c4d"}
- timeline: {"type":"timeline","items":[{"time":"09:40","title":"Relay ON","description?":""}]}
Use only numbers you got from tools or the snapshot. One or two components per answer is usually right;
don't repeat in text what a component already shows.

FOLLOW-UPS — end EVERY reply with 2-4 short suggested next questions the user might tap, using exactly this
lowercase fence (three backticks + shem-followups), never as plain text:
```shem-followups
["Show this week's trend", "How can I cut my evening usage?"]
```"""


# ── Streaming segmenter ────────────────────────────────────────────────────────

FENCE_OPEN = "```shem-"
FENCE_CLOSE = "```"


def _partial_prefix_len(buf: str, token: str) -> int:
    """Length of the longest suffix of buf that is a proper prefix of token."""
    for k in range(min(len(buf), len(token) - 1), 0, -1):
        if buf.endswith(token[:k]):
            return k
    return 0


class StreamSegmenter:
    def __init__(self) -> None:
        self.buf = ""
        self.inside: Optional[str] = None       # tag of the open block ("ui" / "followups")
        self.segments: List[Dict[str, Any]] = []
        self.followups: List[str] = []
        self._checkpoint: Optional[tuple] = None

    # checkpoint/rollback lets a failed provider attempt be discarded on fallback
    def checkpoint(self) -> None:
        self._checkpoint = (self.buf, self.inside, copy.deepcopy(self.segments), list(self.followups))

    def rollback(self) -> None:
        if self._checkpoint is not None:
            self.buf, self.inside, segs, fups = self._checkpoint
            self.segments, self.followups = copy.deepcopy(segs), list(fups)

    @property
    def has_text(self) -> bool:
        return any(s["type"] == "text" and s["content"].strip() for s in self.segments) or bool(self.buf.strip())

    def _text(self, text: str, events: List[Dict[str, Any]]) -> None:
        if not text:
            return
        if self.segments and self.segments[-1]["type"] == "text":
            self.segments[-1]["content"] += text
        else:
            self.segments.append({"type": "text", "content": text})
        events.append({"event": "text", "data": {"delta": text}})

    def _block(self, tag: str, body: str, events: List[Dict[str, Any]]) -> None:
        body = body.strip()
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            logger.info("Dropped AI %s block with invalid JSON", tag)
            return
        if tag == "followups":
            items = parsed if isinstance(parsed, list) else []
            self.followups = [str(x).strip()[:120] for x in items if str(x).strip()][:4]
            events.append({"event": "followups", "data": {"followups": self.followups}})
            return
        if tag != "ui":
            return
        for raw in parsed if isinstance(parsed, list) else [parsed]:
            comp = validate_component(raw)
            if comp is not None:
                self.segments.append({"type": "component", "component": comp})
                events.append({"event": "component", "data": {"component": comp}})

    def feed(self, delta: str) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        self.buf += delta
        while True:
            if self.inside is None:
                idx = self.buf.lower().find(FENCE_OPEN)
                if idx == -1:
                    keep = _partial_prefix_len(self.buf.lower(), FENCE_OPEN)
                    self._text(self.buf[: len(self.buf) - keep], events)
                    self.buf = self.buf[len(self.buf) - keep:]
                    break
                self._text(self.buf[:idx], events)
                rest = self.buf[idx + len(FENCE_OPEN):]
                nl = rest.find("\n")
                if nl == -1:                        # tag line not complete yet
                    self.buf = self.buf[idx:]
                    break
                self.inside = rest[:nl].strip().lower()
                self.buf = rest[nl + 1:]
            else:
                end = self.buf.find(FENCE_CLOSE)
                if end == -1:
                    break
                body, self.buf = self.buf[:end], self.buf[end + len(FENCE_CLOSE):]
                tag, self.inside = self.inside, None
                self._block(tag, body, events)
        return events

    def add_component(self, component: Dict[str, Any]) -> Dict[str, Any]:
        self.segments.append({"type": "component", "component": component})
        return {"event": "component", "data": {"component": component}}

    def flush(self) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        if self.inside is not None:
            tag, self.inside = self.inside, None
            self._block(tag, self.buf, events)     # unterminated block at the very end
        else:
            self._text(self.buf, events)
        self.buf = ""
        return events

    def final_segments(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for seg in self.segments:
            if seg["type"] != "text":
                out.append(seg)
                continue
            pieces, followups = extract_bare_blocks(seg["content"])
            if followups and not self.followups:
                self.followups = followups
            for piece in pieces:
                if piece["type"] == "text":
                    content = piece["content"].strip()
                    if content:
                        out.append({"type": "text", "content": content})
                else:
                    out.append(piece)
        return out


# A block the model wrote without the exact ```shem- fence, e.g. "SHEM-followups" + newline + [...],
# "```SHEM-ui", "~~~shem-ui" or "**shem-followups**". The JSON is read with raw_decode.
_BARE_TAG = re.compile(r"(?im)^[ \t]*(?:```|~~~)?[ \t*_`]*shem[-_ ](ui|followups)[ \t*_`:]*\r?\n")
_BARE_CLOSE = re.compile(r"[ \t]*\r?\n?[ \t]*(?:```|~~~)?")
_DECODER = json.JSONDecoder()


def extract_bare_blocks(text: str) -> tuple[List[Dict[str, Any]], List[str]]:
    """Split text into text/component pieces, pulling out unfenced shem-ui / shem-followups blocks."""
    pieces: List[Dict[str, Any]] = []
    followups: List[str] = []
    pos = 0
    for m in _BARE_TAG.finditer(text):
        if m.start() < pos:
            continue
        j = m.end()
        while j < len(text) and text[j] in " \t\r\n":
            j += 1
        try:
            parsed, end = _DECODER.raw_decode(text, j)
        except json.JSONDecodeError:
            continue
        pieces.append({"type": "text", "content": text[pos:m.start()]})
        end = _BARE_CLOSE.match(text, end).end()
        if m.group(1).lower() == "followups":
            if isinstance(parsed, list):
                followups = [str(x).strip()[:120] for x in parsed if str(x).strip()][:4]
        else:
            for raw in parsed if isinstance(parsed, list) else [parsed]:
                comp = validate_component(raw)
                if comp is not None:
                    pieces.append({"type": "component", "component": comp})
        pos = end
    pieces.append({"type": "text", "content": text[pos:]})
    return pieces, followups


def parse_text(text: str) -> tuple[List[Dict[str, Any]], List[str]]:
    """Parse a complete reply (non-streaming)."""
    seg = StreamSegmenter()
    seg.feed(text)
    seg.flush()
    return seg.final_segments(), seg.followups


def segments_to_plain(segments: List[Dict[str, Any]]) -> str:
    """Text-only rendering used as LLM history (components summarised by type)."""
    parts = []
    for s in segments:
        if s["type"] == "text":
            parts.append(s["content"])
        else:
            parts.append(f"[shown: {s['component'].get('type')} component]")
    return "\n\n".join(parts)
