from __future__ import annotations

import re
from typing import Any


URDU_DIGITS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)

# Strings preserve compound words such as "twelve" as two phone digits.
DIGIT_WORDS = {
    # Urdu
    "صفر": "0", "زیرو": "0", "ز": "0", "زی": "0", "زڈ": "0", "او": "0",
    "ایک": "1", "ون": "1", "دو": "2", "ٹو": "2", "تین": "3", "تری": "3",
    "چار": "4", "فور": "4", "پانچ": "5", "فائیو": "5",
    "چھ": "6", "سکس": "6", "سات": "7", "سیون": "7",
    "آٹھ": "8", "اٹھ": "8", "ایٹ": "8", "نو": "9", "نائن": "9",
    "دس": "10", "گیارہ": "11", "بارہ": "12", "تیرہ": "13",
    "چودہ": "14", "پندرہ": "15", "سولہ": "16", "سترہ": "17",
    "اٹھارہ": "18", "انیس": "19", "بیس": "20", "تیس": "30",
    "چالیس": "40", "پچاس": "50", "ساٹھ": "60", "ستر": "70",
    "اسی": "80", "نوے": "90", "ننانوے": "99",
    # Roman Urdu
    "sifar": "0", "zero": "0", "o": "0", "zed": "0",
    "aik": "1", "ek": "1", "do": "2",
    "teen": "3", "char": "4", "chaar": "4", "panch": "5",
    "paanch": "5", "chay": "6", "chhai": "6", "chhe": "6", "che": "6",
    "saat": "7", "aath": "8", "ath": "8", "nau": "9",
    "gyarah": "11", "giyara": "11", "barah": "12", "bara": "12",
    "tera": "13", "chaudah": "14", "pandrah": "15", "solah": "16",
    "satrah": "17", "atharah": "18", "unnis": "19", "bees": "20",
    "tees": "30", "chalees": "40", "pachas": "50", "saath": "60",
    "sattar": "70", "assi": "80", "naway": "90", "ninyanaway": "99",
    # English
    "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16",
    "seventeen": "17", "eighteen": "18", "nineteen": "19",
    "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50",
    "sixty": "60", "seventy": "70", "eighty": "80", "ninety": "90",
}

REPEAT_WORDS = {"double": 2, "ڈبل": 2, "triple": 3, "ٹرپل": 3}
PHONE_CONTEXT_WORDS = {
    "phone", "mobile", "number", "contact",
    "فون", "موبائل", "نمبر", "رابطہ",
}


def _tokens(value: Any) -> list[str]:
    text = str(value or "").lower().translate(URDU_DIGITS)
    return re.findall(r"\d+|[a-z]+|[\u0600-\u06ff]+", text, flags=re.UNICODE)


def spoken_phone_digits(value: Any) -> str:
    """Extract numeric chunks and Urdu/English spoken number words."""
    tokens = _tokens(value)
    output: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in REPEAT_WORDS and index + 1 < len(tokens):
            next_value = DIGIT_WORDS.get(tokens[index + 1])
            if next_value is None and tokens[index + 1].isdigit():
                next_value = tokens[index + 1]
            if next_value is not None and len(next_value) == 1:
                output.append(next_value * REPEAT_WORDS[token])
                index += 2
                continue

        if token.isdigit():
            output.append(token)
        elif token in DIGIT_WORDS:
            output.append(DIGIT_WORDS[token])
        index += 1
    return "".join(output)


def normalize_phone_number(value: Any) -> str | None:
    """Return a usable spoken phone sequence without enforcing one format.

    Voice ASR can drop or merge individual digits, so appointment collection
    accepts 7–15 captured digits instead of blocking on a Pakistan-specific
    11-digit format. Very short numeric fragments remain invalid.
    """
    digits = spoken_phone_digits(value)
    if len(digits) == 12 and digits.startswith("923"):
        digits = f"0{digits[2:]}"
    if re.fullmatch(r"\d{7,15}", digits):
        return digits
    return None


def is_valid_phone_number(value: Any) -> bool:
    return normalize_phone_number(value) is not None


def has_phone_number_signal(value: Any) -> bool:
    tokens = _tokens(value)
    if any(token in PHONE_CONTEXT_WORDS for token in tokens):
        return True
    digit_units = sum(
        len(token) if token.isdigit() else len(DIGIT_WORDS.get(token, ""))
        for token in tokens
    )
    return digit_units >= 4


def has_phone_context(value: Any) -> bool:
    """Return whether the caller explicitly referred to a phone/contact number."""
    return any(token in PHONE_CONTEXT_WORDS for token in _tokens(value))
