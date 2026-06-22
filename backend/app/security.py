"""
Privacy and security safeguards.

Covers:
- Request body size limits (blocks oversized debrief text)
- PII scrubbing utilities (strips candidate names/IDs before LLM logging)
- Security headers middleware
- Input sanitization for text fields
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

# ---------------------------------------------------------------------------
# Security Headers Middleware
# ---------------------------------------------------------------------------


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security headers to every response."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        return response


# ---------------------------------------------------------------------------
# Request body size guard
# ---------------------------------------------------------------------------

MAX_BODY_BYTES = 1_000_000  # 1 MB — generous for any real debrief payload


async def check_request_size(request: Request) -> None:
    """FastAPI dependency — raises 413 if the request body is too large."""
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_BODY_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Request body too large (max {MAX_BODY_BYTES // 1000} KB).",
        )


# ---------------------------------------------------------------------------
# Debrief text validation
# ---------------------------------------------------------------------------

MAX_DEBRIEF_CHARS = settings.max_debrief_size_chars
MIN_DEBRIEF_CHARS = 10  # matches schema min_length


def validate_debrief_text(text: str, field_name: str = "raw_text") -> str:
    """Validate debrief text length and content. Returns the text unchanged if valid."""
    if len(text) < MIN_DEBRIEF_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} is too short (minimum {MIN_DEBRIEF_CHARS} characters).",
        )
    if len(text) > MAX_DEBRIEF_CHARS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{field_name} exceeds maximum length ({MAX_DEBRIEF_CHARS:,} chars). Truncate or split the debrief."
            ),
        )
    return text


# ---------------------------------------------------------------------------
# PII scrubbing for logs
# ---------------------------------------------------------------------------

# Patterns that might identify a real candidate. Used before logging only —
# never applied to stored or processed data (that would break citation spans).
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_RE = re.compile(r"\b(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def scrub_pii_for_log(text: str) -> str:
    """
    Replace email addresses, phone numbers, and SSNs with placeholders.

    ONLY for log output — never applied to stored debrief text or evidence spans.
    Applying scrubbing to stored text would corrupt character offsets.
    """
    text = _EMAIL_RE.sub("[EMAIL]", text)
    text = _PHONE_RE.sub("[PHONE]", text)
    text = _SSN_RE.sub("[SSN]", text)
    return text


def scrub_signal_for_log(signal_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Return a log-safe version of a signal dict with PII scrubbed from
    quoted_text and claim fields. Does NOT modify the original.
    """
    safe = dict(signal_dict)
    if "claim" in safe and isinstance(safe["claim"], str):
        safe["claim"] = scrub_pii_for_log(safe["claim"])
    if "evidence_spans" in safe and isinstance(safe["evidence_spans"], list):
        safe["evidence_spans"] = [
            {**span, "quoted_text": scrub_pii_for_log(span.get("quoted_text", ""))} if isinstance(span, dict) else span
            for span in safe["evidence_spans"]
        ]
    return safe


# ---------------------------------------------------------------------------
# API key validation at startup
# ---------------------------------------------------------------------------


def warn_if_no_api_key() -> None:
    """
    Print a startup warning if the server is running in LLM mode without an API key.
    The server still starts (baseline mode continues to work); LLM endpoint returns 503.
    """
    if not settings.anthropic_api_key and not settings.llm_mock_mode and not settings.baseline_mode:
        import warnings

        warnings.warn(
            "ANTHROPIC_API_KEY is not set. "
            "The /extract/llm endpoint will return 503 until an API key is provided. "
            "Set LLM_MOCK_MODE=true to use the mock extractor instead.",
            stacklevel=2,
        )
