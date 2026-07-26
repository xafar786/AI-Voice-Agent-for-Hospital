from __future__ import annotations

import re
from typing import Any, Literal

from domain.phone_normalization import spoken_phone_digits


IdKind = Literal["appointment", "doctor", "patient"]

ID_PREFIXES: dict[IdKind, str] = {
    "appointment": "APT",
    "doctor": "DC",
    "patient": "PC",
}

PREFIX_PATTERNS: dict[IdKind, re.Pattern[str]] = {
    "appointment": re.compile(
        r"(?:\bA\s*P\s*T|اے\s*پی\s*ٹی|appointment\s*(?:id)?)",
        re.IGNORECASE,
    ),
    "doctor": re.compile(
        r"(?:\bD\s*(?:C|O\s*C)|ڈی\s*سی|doctor\s*(?:id)?)",
        re.IGNORECASE,
    ),
    "patient": re.compile(
        r"(?:\bP\s*(?:C|A\s*T)|پی\s*سی|پی\s*اے\s*ٹی|patient\s*(?:id)?)",
        re.IGNORECASE,
    ),
}

ASR_ID_REPLACEMENTS = {
    # Common joined tokens observed when callers spell compact IDs.
    "زیروون": "زیرو ون",
    "zeroone": "zero one",
    "zerowon": "zero one",
    "zerrow": "zero",
    "سلیش": " ",
    "slash": " ",
}

ID_SUFFIX_STOP_PATTERN = re.compile(
    r"(?:\b(?:کو|پر|ہے|تاریخ|وقت|کل|آج|پرسوں|ری\s*شیڈول|کینسل|"
    r"to|at|on|date|time|tomorrow|today|cancel|reschedule)\b|[,،;])",
    re.IGNORECASE,
)


def normalize_external_id(
    value: Any,
    kind: IdKind,
    *,
    allow_digits_only: bool = False,
) -> str | None:
    """Canonicalize current and legacy spoken IDs without separators.

    Examples: APT-0013 -> APT13, "APT zero zero one three" -> APT13,
    DOC-0003 -> DC3, and PAT-0007 -> PC7.
    """
    text = str(value or "").strip()
    if not text:
        return None
    normalized_text = text.lower()
    for source, replacement in ASR_ID_REPLACEMENTS.items():
        normalized_text = normalized_text.replace(source, replacement)

    prefix_match = PREFIX_PATTERNS[kind].search(normalized_text)
    if not prefix_match and not allow_digits_only:
        return None

    numeric_text = normalized_text
    if prefix_match:
        numeric_text = normalized_text[prefix_match.end():]
        numeric_text = ID_SUFFIX_STOP_PATTERN.split(numeric_text, maxsplit=1)[0]
    digits = spoken_phone_digits(numeric_text)
    if not digits:
        return None
    number = int(digits)
    if number <= 0:
        return None
    return f"{ID_PREFIXES[kind]}{number}"


def normalize_appointment_id(value: Any, *, allow_digits_only: bool = False) -> str | None:
    return normalize_external_id(value, "appointment", allow_digits_only=allow_digits_only)


def normalize_doctor_id(value: Any, *, allow_digits_only: bool = False) -> str | None:
    return normalize_external_id(value, "doctor", allow_digits_only=allow_digits_only)


def normalize_patient_id(value: Any, *, allow_digits_only: bool = False) -> str | None:
    return normalize_external_id(value, "patient", allow_digits_only=allow_digits_only)
