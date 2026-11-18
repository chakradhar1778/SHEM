"""
SHEM AI — Electricity bill document scanner.

Sends an uploaded bill image (JPG, PNG, WebP) or PDF to Gemini's multimodal
endpoint via the shared LLMRouter (inheriting multi-key round-robin & back-off).
Always returns a well-typed BillScanResult with a defined BillScanError format
when extraction cannot proceed so the UI can guide the user clearly.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from datetime import date
from typing import Any, Dict, List, Optional

from app.ai.providers import AllProvidersFailed, get_router
from app.models.schemas import BillScanError, BillScanResult
from app.services import document_store

logger = logging.getLogger(__name__)

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ALLOWED_AI_ERROR_CODES = {"not_a_bill", "unreadable_image", "incomplete_bill"}

BILL_SCAN_PROMPT = """You are an expert Indian electricity utility bill reader for a smart home energy monitor (SHEM).
Inspect the uploaded document (image or PDF) and extract the electricity bill details.

You MUST respond with ONLY a single valid JSON object (no markdown fences, no commentary).

If the document IS an electricity bill and at least some bill fields can be read, return:
{
  "ok": true,
  "provider": "<utility provider short name, e.g. BESCOM, TSSPDCL, APSPDCL, MSEDCL, Tata Power, Adani, TNEB, KSEB, BSES, or null>",
  "account_id": "<consumer / account / RR / CA / USC number, or null>",
  "units_kwh": <positive number for billed units consumed in kWh, or null>,
  "amount_inr": <positive number for total payable bill amount in INR (₹), or null>,
  "billing_month": <integer 1-12 for the billing month, or null>,
  "billing_year": <4-digit integer year e.g. 2026, or null>,
  "period_start": "<billing period start date YYYY-MM-DD, or null>",
  "period_end": "<billing period end date YYYY-MM-DD, or null>",
  "due_date": "<payment due date YYYY-MM-DD, or null>",
  "confidence": "<high | medium | low>",
  "warnings": ["<optional short user-facing notes about uncertain or missing fields>"],
  "scan_note": "<optional one-sentence summary or caveat, or null>"
}

If the document CANNOT be read as an electricity bill, return this exact error format:
{
  "ok": false,
  "error": {
    "code": "<one of: not_a_bill | unreadable_image | incomplete_bill>",
    "title": "<short clear headline, max 8 words>",
    "detail": "<1-2 sentences explaining clearly what went wrong so the user understands>",
    "hint": "<short actionable next step, e.g. upload a clearer photo or enter details manually>"
  }
}

Rules:
- Use "not_a_bill" if the file is not an electricity bill (e.g. a receipt, random photo, water/gas bill, blank page).
- Use "unreadable_image" if text is too blurry, dark, rotated, or low-resolution to read numbers reliably.
- Use "incomplete_bill" ONLY if it is an electricity bill but BOTH units consumed (kWh) AND bill amount (₹) are completely cropped out or missing.
- Never guess or fabricate numbers. If a single field (like due_date or account_id) is unclear, set it to null and add a short item in "warnings".
- Convert all dates to YYYY-MM-DD format. Strip currency symbols (₹, Rs.) and commas from numbers."""


def _error_result(
    code: str,
    title: str,
    detail: str,
    hint: Optional[str] = None,
    ai_provider: Optional[str] = None,
) -> BillScanResult:
    return BillScanResult(
        ok=False,
        ai_provider=ai_provider,
        error=BillScanError(code=code, title=title, detail=detail, hint=hint),  # type: ignore[arg-type]
    )


def _extract_json(raw: str) -> Dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
            if text.lstrip().lower().startswith("json"):
                text = text.lstrip()[4:]
    text = text.strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    # Fallback: locate outermost JSON object in case the model added brief prose.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        obj = json.loads(text[start : end + 1])
        if isinstance(obj, dict):
            return obj
    raise ValueError("AI response did not contain a valid JSON object.")


def _clean_float(val: Any, min_val: float = 0.0, max_val: float = 10_000_000.0) -> Optional[float]:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, str):
        cleaned = re.sub(r"[₹,\s]|rs\.?", "", val, flags=re.IGNORECASE).strip()
        if not cleaned:
            return None
        val = cleaned
    try:
        num = float(val)
    except (TypeError, ValueError):
        return None
    if not (min_val < num <= max_val):
        return None
    return round(num, 2)


def _clean_int(val: Any, lo: int, hi: int) -> Optional[int]:
    if val is None or isinstance(val, bool):
        return None
    try:
        n = int(val)
    except (TypeError, ValueError):
        return None
    return n if lo <= n <= hi else None


def _clean_date(val: Any) -> Optional[str]:
    if not isinstance(val, str):
        return None
    s = val.strip()
    if not _ISO_DATE_RE.match(s):
        return None
    try:
        date.fromisoformat(s)
        return s
    except ValueError:
        return None


def _clean_text(val: Any, max_len: int = 128) -> Optional[str]:
    if not isinstance(val, str):
        return None
    s = val.strip()
    return s[:max_len] if s else None


async def scan_bill_bytes(data: bytes, content_type: str) -> BillScanResult:
    """Validate uploaded bill bytes, call Gemini vision/PDF, and return a typed BillScanResult."""
    try:
        verified_type = document_store.validate(data, content_type)
    except document_store.DocumentError as exc:
        if exc.status == 413:
            return _error_result(
                code="file_too_large",
                title="File is too large",
                detail=str(exc),
                hint="Compress the bill image/PDF or upload a smaller file, or enter the bill manually.",
            )
        return _error_result(
            code="invalid_file",
            title="Unsupported bill file",
            detail=str(exc),
            hint="Upload a JPG, PNG, WebP image or a PDF of your electricity bill.",
        )

    router = get_router()
    if not router.available:
        return _error_result(
            code="ai_unavailable",
            title="AI bill scanning is not configured",
            detail="No AI API key is configured on the SHEM backend.",
            hint="Add GEMINI_API_KEY (or GEMINI_API_KEYS) in backend/.env and restart, or enter the bill manually below.",
        )

    gemini = router.get_provider("gemini")
    if gemini is None:
        return _error_result(
            code="vision_unsupported",
            title="Gemini API key required for bill scanning",
            detail="Your backend currently has Groq configured, which does not support reading bill images or PDFs.",
            hint="Add a GEMINI_API_KEY (or GEMINI_API_KEYS) in backend/.env to enable AI bill scanning, or enter the bill manually below.",
        )

    b64 = base64.b64encode(data).decode("ascii")
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": BILL_SCAN_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:{verified_type};base64,{b64}"}},
            ],
        }
    ]

    try:
        turn = await router.complete(messages, temperature=0.1, provider_name="gemini")
    except AllProvidersFailed as exc:
        msg = str(exc).lower()
        if any(tok in msg for tok in ("429", "quota", "rate", "resource_exhausted", "back-off")):
            return _error_result(
                code="rate_limited",
                title="AI scan temporarily rate-limited",
                detail="All configured Gemini API keys have hit their rate or quota limit right now.",
                hint="Wait a minute and tap Retry scan, add extra keys to GEMINI_API_KEYS, or enter the details manually below.",
                ai_provider="gemini",
            )
        logger.warning("Bill scan provider failure: %s", exc)
        return _error_result(
            code="scan_failed",
            title="AI service could not process the bill",
            detail="SHEM could not get a response from the AI service while reading your bill.",
            hint="Check your internet connection and Gemini API key, tap Retry scan, or enter the bill manually.",
            ai_provider="gemini",
        )
    except Exception as exc:
        logger.warning("Unexpected bill scan failure: %s", exc)
        return _error_result(
            code="scan_failed",
            title="Could not scan the bill",
            detail="An unexpected error occurred while reading your bill document.",
            hint="Tap Retry scan or enter the bill details manually below.",
            ai_provider="gemini",
        )

    try:
        parsed = _extract_json(turn.text)
    except Exception as exc:
        logger.warning("Bill scan JSON parse failed: %s (raw=%r)", exc, turn.text[:300])
        return _error_result(
            code="parse_failed",
            title="Could not interpret AI response",
            detail="The AI responded, but its output could not be parsed into bill fields.",
            hint="Tap Retry scan with a clearer image or enter the bill details manually below.",
            ai_provider=turn.provider,
        )

    # Handle defined AI-reported errors (e.g., not_a_bill, unreadable_image, incomplete_bill)
    if parsed.get("ok") is False or parsed.get("error"):
        err = parsed.get("error") if isinstance(parsed.get("error"), dict) else {}
        code = err.get("code") if err.get("code") in _ALLOWED_AI_ERROR_CODES else "unreadable_image"
        title = _clean_text(err.get("title"), 100) or "Could not read this bill"
        detail = _clean_text(err.get("detail"), 400) or (
            "The uploaded document does not look like a readable electricity bill."
        )
        hint = _clean_text(err.get("hint"), 240) or (
            "Upload a clearer photo/PDF of your electricity bill, or enter the details manually below."
        )
        return _error_result(code=code, title=title, detail=detail, hint=hint, ai_provider=turn.provider)

    units = _clean_float(parsed.get("units_kwh"), min_val=0.0, max_val=1_000_000.0)
    amount = _clean_float(parsed.get("amount_inr"), min_val=0.0, max_val=10_000_000.0)
    period_start = _clean_date(parsed.get("period_start"))
    period_end = _clean_date(parsed.get("period_end"))
    due_date = _clean_date(parsed.get("due_date"))
    billing_month = _clean_int(parsed.get("billing_month"), 1, 12)
    billing_year = _clean_int(parsed.get("billing_year"), 2000, 2100)

    # Derive month/year from period_start or period_end if AI omitted them.
    ref_date_str = period_start or period_end
    if ref_date_str and (billing_month is None or billing_year is None):
        ref_d = date.fromisoformat(ref_date_str)
        billing_month = billing_month or ref_d.month
        billing_year = billing_year or ref_d.year

    raw_conf = str(parsed.get("confidence") or "").strip().lower()
    confidence = raw_conf if raw_conf in ("high", "medium", "low") else None

    warnings: List[str] = []
    if isinstance(parsed.get("warnings"), list):
        for w in parsed["warnings"][:6]:
            cleaned = _clean_text(w, 200)
            if cleaned:
                warnings.append(cleaned)

    if units is None and amount is None:
        return _error_result(
            code="incomplete_bill",
            title="Could not find units or bill amount",
            detail="SHEM could not read either the units consumed (kWh) or the bill amount (₹) from this document.",
            hint="Upload a clearer image showing the bill summary section, or enter the values manually below.",
            ai_provider=turn.provider,
        )

    if units is None:
        warnings.append("Units consumed (kWh) could not be read — please fill it in before saving.")
    if amount is None:
        warnings.append("Total bill amount (₹) could not be read — please fill it in before saving.")

    return BillScanResult(
        ok=True,
        provider=_clean_text(parsed.get("provider"), 80),
        account_id=_clean_text(parsed.get("account_id"), 60),
        units_kwh=units,
        amount_inr=amount,
        billing_month=billing_month,
        billing_year=billing_year,
        period_start=period_start,
        period_end=period_end,
        due_date=due_date,
        confidence=confidence,
        warnings=warnings,
        scan_note=_clean_text(parsed.get("scan_note"), 300),
        ai_provider=turn.provider,
    )
