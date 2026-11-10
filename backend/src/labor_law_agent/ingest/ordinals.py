"""Arabic feminine ordinal words -> int, as used in BOE article headings.

Forms seen in the BOE Labor Law text (articles 1-245):
  الأولى (1) ... العاشرة (10)
  الحادية عشرة (11) ... التاسعة عشرة (19)
  العشرون (20), الحادية والعشرون (21) ... التاسعة والتسعون (99)
  المائة (100), <1-99> بعد المائة (101-199)
  المئتان (200), <1-99> بعد المائتين (201-299)

Spelling variants are normalized first: diacritics and tatweel removed, أ/إ/آ -> ا,
ى -> ي, ة -> ه, and مئة/مئتان/مئتين -> مائة/مائتان/مائتين.
"""

from __future__ import annotations

import re

_DIACRITICS = re.compile(r"[ً-ْٰـ]")  # tashkeel, superscript alef, tatweel

_UNITS = {
    "الاولي": 1,
    "الثانيه": 2,
    "الثالثه": 3,
    "الرابعه": 4,
    "الخامسه": 5,
    "السادسه": 6,
    "السابعه": 7,
    "الثامنه": 8,
    "التاسعه": 9,
}
# In teens and compounds, "one" is الحادية, not الأولى.
_COMPOUND_UNITS = {**{k: v for k, v in _UNITS.items() if v != 1}, "الحاديه": 1}
_TEN = "العاشره"
_TEEN_SUFFIX = "عشره"
_TENS = {
    "العشرون": 20,
    "الثلاثون": 30,
    "الاربعون": 40,
    "الخمسون": 50,
    "الستون": 60,
    "السبعون": 70,
    "الثمانون": 80,
    "التسعون": 90,
}
_HUNDREDS = {"المائه": 100, "المائتان": 200}
_AFTER_HUNDREDS = {"بعد المائه": 100, "بعد المائتين": 200}


def normalize_arabic(text: str) -> str:
    text = _DIACRITICS.sub("", text)
    text = re.sub("[أإآ]", "ا", text).replace("ى", "ي").replace("ة", "ه")
    text = text.replace("مئه", "مائه").replace("مئتان", "مائتان").replace("مئتين", "مائتين")
    return " ".join(text.split())


def _below_hundred(words: str) -> int | None:
    if words in _UNITS:
        return _UNITS[words]
    if words == _TEN:
        return 10
    if words in _TENS:
        return _TENS[words]
    parts = words.split(" ")
    if len(parts) == 2 and parts[1] == _TEEN_SUFFIX and parts[0] in _COMPOUND_UNITS:
        return 10 + _COMPOUND_UNITS[parts[0]]
    if len(parts) == 2 and parts[1].startswith("و") and parts[1][1:] in _TENS:
        unit = _COMPOUND_UNITS.get(parts[0])
        if unit is not None:
            return unit + _TENS[parts[1][1:]]
    return None


def arabic_ordinal_to_int(text: str) -> int | None:
    """Return the number for a whole ordinal phrase, or None if it isn't one."""
    words = normalize_arabic(text)
    if words in _HUNDREDS:
        return _HUNDREDS[words]
    for suffix, base in _AFTER_HUNDREDS.items():
        if words.endswith(" " + suffix):
            rest = _below_hundred(words[: -len(suffix) - 1])
            return None if rest is None else base + rest
    return _below_hundred(words)
