from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


URDU_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

NUMBER_WORDS = {
    # Urdu
    "صفر": 0, "زیرو": 0,
    "ایک": 1, "دو": 2, "تین": 3, "چار": 4, "پانچ": 5, "چھ": 6,
    "سات": 7, "آٹھ": 8, "اٹھ": 8, "نو": 9, "دس": 10,
    "گیارہ": 11, "بارہ": 12, "تیرہ": 13, "چودہ": 14, "پندرہ": 15,
    "سولہ": 16, "سترہ": 17, "اٹھارہ": 18, "انیس": 19, "بیس": 20,
    "اکیس": 21, "بائیس": 22, "تئیس": 23, "تیس": 30, "پینتالیس": 45,
    # Roman Urdu
    "zero": 0, "aik": 1, "ek": 1, "do": 2, "teen": 3,
    "char": 4, "chaar": 4, "panch": 5, "paanch": 5,
    "chay": 6, "chhai": 6, "che": 6, "saat": 7,
    "aath": 8, "ath": 8, "nau": 9, "no": 9, "now": 9,
    "das": 10, "gyarah": 11, "giyara": 11, "barah": 12,
    "tera": 13, "chaudah": 14, "pandrah": 15, "solah": 16,
    "satrah": 17, "atharah": 18, "unnis": 19, "bees": 20,
    "ikkis": 21, "baais": 22, "teis": 23, "tees": 30,
    "paintalis": 45, "pentaalis": 45,
    # English
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "twenty-one": 21, "twenty-two": 22,
    "twenty-three": 23, "thirty": 30, "forty-five": 45,
}

NUMBER_TOKEN = "|".join(
    sorted((re.escape(word) for word in NUMBER_WORDS), key=len, reverse=True)
)
VALUE_TOKEN = rf"(?:\d{{1,2}}|{NUMBER_TOKEN})"

MORNING_TERMS = {"am", "a.m", "صبح", "subah", "morning"}
EVENING_TERMS = {
    "pm", "p.m", "شام", "shaam", "evening", "دوپہر", "dopahar",
    "afternoon", "رات", "raat", "night",
}


@dataclass(frozen=True)
class TimeNormalizationResult:
    recognized: bool
    value: str | None = None
    candidates: tuple[str, ...] = ()
    ambiguous: bool = False


def _number(value: str) -> int | None:
    token = value.strip().lower().translate(URDU_DIGITS)
    if token.isdigit():
        return int(token)
    return NUMBER_WORDS.get(token)


def _period(text: str) -> str | None:
    tokens = set(re.findall(r"[\w.-]+", text.lower(), flags=re.UNICODE))
    if tokens & MORNING_TERMS:
        return "am"
    if tokens & EVENING_TERMS:
        return "pm"
    return None


def _components(text: str) -> tuple[int, int, bool] | None:
    normalized = re.sub(r"\s+", " ", text.translate(URDU_DIGITS).lower()).strip()
    period = _period(normalized)

    # Standard clock formats: 9:15, 09.15, 9 15.
    match = re.search(r"\b([01]?\d|2[0-3])\s*[:.]\s*([0-5]\d)\b", normalized)
    if match:
        return int(match.group(1)), int(match.group(2)), bool(period or int(match.group(1)) > 12)

    # Compact ASR formats such as 900, 0900, or 0915. Exclude likely years.
    match = re.search(r"(?:زیرو|zero)\s*(\d{3})\b", normalized)
    if match:
        compact = f"0{match.group(1)}"
        hour, minute = int(compact[:2]), int(compact[2:])
        if hour <= 23 and minute <= 59:
            return hour, minute, bool(period or hour > 12)

    match = re.search(r"\b(\d{3,4})\b", normalized)
    if match:
        compact = match.group(1).zfill(4)
        hour, minute = int(compact[:2]), int(compact[2:])
        if hour <= 23 and minute <= 59 and not (1900 <= int(match.group(1)) <= 2099):
            return hour, minute, bool(period or hour > 12)

    # ساڑھے آٹھ / saray 8 / half past eight.
    match = re.search(
        rf"(?:ساڑھے|ساڑھے\s+بجے|saray|saadhe|sadhe|half\s+past)\s+({VALUE_TOKEN})",
        normalized,
        flags=re.IGNORECASE,
    )
    if match and (hour := _number(match.group(1))) is not None:
        return hour, 30, bool(period or hour > 12)

    # پونے نو / ponay 9 / quarter to nine.
    match = re.search(
        rf"(?:پونے|ponay|paunay|quarter\s+to)\s+({VALUE_TOKEN})",
        normalized,
        flags=re.IGNORECASE,
    )
    if match and (next_hour := _number(match.group(1))) is not None:
        hour = (next_hour - 1) % 24
        return hour, 45, bool(period or next_hour > 12)

    # نو بج کر پندرہ منٹ / 9 baj kar 15.
    match = re.search(
        rf"({VALUE_TOKEN})\s*(?:بج\s*کر|baj\s*kar|baje\s*kar|past)\s*"
        rf"({VALUE_TOKEN})(?:\s*(?:منٹ|minute|minutes|min))?",
        normalized,
        flags=re.IGNORECASE,
    )
    if match:
        hour, minute = _number(match.group(1)), _number(match.group(2))
        if hour is not None and minute is not None and hour <= 23 and minute <= 59:
            return hour, minute, bool(period or hour > 12)

    # ASR commonly drops "بج کر": نو 15 / nine fifteen / 9 15.
    match = re.search(
        rf"\b({VALUE_TOKEN})\s+({VALUE_TOKEN})(?:\s*(?:منٹ|minute|minutes|min))?\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if match:
        hour, minute = _number(match.group(1)), _number(match.group(2))
        if hour is not None and minute in {0, 15, 30, 45} and hour <= 23:
            return hour, minute, bool(period or hour > 12)

    # نو بجے / 9 baje / nine o'clock.
    match = re.search(
        rf"({VALUE_TOKEN})\s*(?:بجے|baje|o['’]?\s*clock)\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if match and (hour := _number(match.group(1))) is not None and hour <= 23:
        return hour, 0, bool(period or hour > 12)

    # 9 am / nine pm / نو صبح.
    match = re.search(
        rf"\b({VALUE_TOKEN})\s*(?:am|a\.m\.?|pm|p\.m\.?|صبح|شام|رات|"
        rf"subah|shaam|raat|morning|evening|night)\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if match and (hour := _number(match.group(1))) is not None and hour <= 23:
        return hour, 0, True
    return None


def _candidate_times(hour: int, minute: int, text: str, explicit_24_hour: bool) -> tuple[str, ...]:
    period = _period(text)
    if period == "am":
        resolved_hour = 0 if hour == 12 else hour
        return (f"{resolved_hour:02d}:{minute:02d}",)
    if period == "pm":
        resolved_hour = hour if hour >= 12 else hour + 12
        return (f"{resolved_hour:02d}:{minute:02d}",)
    if explicit_24_hour or hour > 12 or hour == 0:
        return (f"{hour:02d}:{minute:02d}",)
    if hour == 12:
        return (f"12:{minute:02d}", f"00:{minute:02d}")
    return (f"{hour:02d}:{minute:02d}", f"{hour + 12:02d}:{minute:02d}")


def normalize_time_for_slots(
    text: str,
    available_slots: Iterable[str] = (),
) -> TimeNormalizationResult:
    standardized_slots = {
        slot
        for raw_slot in available_slots
        if (slot := str(raw_slot).strip())
        and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", slot)
    }
    parsed = _components(text)
    if not parsed:
        period = _period(text)
        if period and standardized_slots:
            matches = tuple(sorted(
                slot
                for slot in standardized_slots
                if (int(slot[:2]) < 12) == (period == "am")
            ))
            if len(matches) == 1:
                return TimeNormalizationResult(True, matches[0], matches, False)
            if matches:
                return TimeNormalizationResult(True, None, matches, True)
        return TimeNormalizationResult(recognized=False)

    hour, minute, explicit_24_hour = parsed
    candidates = _candidate_times(hour, minute, text, explicit_24_hour)
    matches = tuple(candidate for candidate in candidates if candidate in standardized_slots)
    if len(matches) == 1:
        return TimeNormalizationResult(True, matches[0], matches, False)
    if len(matches) > 1:
        return TimeNormalizationResult(True, None, matches, True)
    if len(candidates) == 1:
        return TimeNormalizationResult(True, candidates[0], candidates, False)
    return TimeNormalizationResult(True, None, candidates, True)


def mentions_clock_time(text: str) -> bool:
    """Return whether text contains an actual clock expression.

    A period word by itself (for example, "رات" in "کل رات سے درد ہے")
    is deliberately not considered a requested appointment time.
    """
    return _components(text) is not None
