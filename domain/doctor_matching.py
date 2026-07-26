from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import Any


URDU_TO_LATIN = {
    "ا": "a", "آ": "a", "أ": "a", "إ": "a", "ع": "a",
    "ب": "b", "پ": "p", "ت": "t", "ٹ": "t", "ث": "s",
    "ج": "j", "چ": "ch", "ح": "h", "خ": "kh",
    "د": "d", "ڈ": "d", "ذ": "z", "ر": "r", "ڑ": "r",
    "ز": "z", "ژ": "zh", "س": "s", "ش": "sh",
    "ص": "s", "ض": "z", "ط": "t", "ظ": "z", "غ": "gh",
    "ف": "f", "ق": "q", "ک": "k", "ك": "k", "گ": "g",
    "ل": "l", "م": "m", "ن": "n", "ں": "n",
    "و": "w", "ؤ": "w", "ہ": "h", "ھ": "h", "ۃ": "h",
    "ی": "y", "ے": "y", "ئ": "y", "ء": "",
}


def doctor_name_key(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\b(?:dr|doctor)\.?\b", " ", text)
    text = text.replace("ڈاکٹر", " ")
    transliterated = "".join(URDU_TO_LATIN.get(char, char) for char in text)
    transliterated = re.sub(r"\b(?:md|mbbs|fcps)\b", " ", transliterated)
    letters = re.sub(r"[^a-z]+", "", transliterated)
    return re.sub(r"[aeiou]", "", letters)


def doctor_names_match(requested_name: Any, catalog_name: Any) -> bool:
    return doctor_name_match_score(requested_name, catalog_name) >= 0.78


def doctor_name_match_score(requested_name: Any, catalog_name: Any) -> float:
    requested_key = doctor_name_key(requested_name)
    catalog_key = doctor_name_key(catalog_name)
    if not requested_key or not catalog_key:
        return 0.0
    if requested_key == catalog_key:
        return 1.0
    return SequenceMatcher(None, requested_key, catalog_key).ratio()
