import pytest

from labor_law_agent.ingest.ordinals import arabic_ordinal_to_int, normalize_arabic

# Hand-written expected values; words are NOT generated with production logic.
CASES = [
    # units 1-10
    ("الأولى", 1),
    ("الثانية", 2),
    ("الثالثة", 3),
    ("الرابعة", 4),
    ("الخامسة", 5),
    ("السادسة", 6),
    ("السابعة", 7),
    ("الثامنة", 8),
    ("التاسعة", 9),
    ("العاشرة", 10),
    # teens 11-19
    ("الحادية عشرة", 11),
    ("الثانية عشرة", 12),
    ("الثالثة عشرة", 13),
    ("الرابعة عشرة", 14),
    ("الخامسة عشرة", 15),
    ("السادسة عشرة", 16),
    ("السابعة عشرة", 17),
    ("الثامنة عشرة", 18),
    ("التاسعة عشرة", 19),
    # tens 20-90
    ("العشرون", 20),
    ("الثلاثون", 30),
    ("الأربعون", 40),
    ("الخمسون", 50),
    ("الستون", 60),
    ("السبعون", 70),
    ("الثمانون", 80),
    ("التسعون", 90),
    # compounds
    ("الحادية والعشرون", 21),
    ("الثانية والعشرون", 22),
    ("الخامسة والثلاثون", 35),
    ("الرابعة والثمانون", 84),
    ("التاسعة والتسعون", 99),
    # hundreds
    ("المائة", 100),
    ("الأولى بعد المائة", 101),
    ("العاشرة بعد المائة", 110),
    ("الحادية عشرة بعد المائة", 111),
    ("العشرون بعد المائة", 120),
    ("الثالثة والتسعون بعد المائة", 193),
    ("الرابعة والثمانون بعد المائة", 184),
    ("التاسعة والتسعون بعد المائة", 199),
    ("المئتان", 200),
    ("المائتان", 200),
    ("الأولى بعد المائتين", 201),
    ("الخامسة والأربعون بعد المائتين", 245),
]


@pytest.mark.parametrize(("words", "expected"), CASES)
def test_ordinal_words_to_int(words: str, expected: int) -> None:
    assert arabic_ordinal_to_int(words) == expected


@pytest.mark.parametrize(
    ("words", "expected"),
    [
        ("الأُولَى", 1),  # diacritics
        ("الاولى", 1),  # no hamza
        ("الإولى", 1),  # hamza below
        ("الأولي", 1),  # ى -> ي
        ("الثانيه", 2),  # ة -> ه
        ("الثـــانية", 2),  # tatweel
        ("الأولى بعد المئة", 101),  # مئة vs مائة
        ("المِئَة", 100),
        ("المئه", 100),
        ("الأولى بعد المئتين", 201),
        ("  الرابعة   والثمانون ", 84),  # extra spaces
        ("الحاديه عشره", 11),
        ("الخامسة والأربعون بعد المئتين", 245),
    ],
)
def test_spelling_variants(words: str, expected: int) -> None:
    assert arabic_ordinal_to_int(words) == expected


@pytest.mark.parametrize(
    "text",
    [
        "الأولى والعشرون",  # unit 1 must be الحادية in compounds
        "الحادية",  # الحادية alone is not an ordinal
        "العاشرة عشرة",
        "الخامسة من هذا النظام",
        "",
        "   ",
        "كلام عشوائي",
        "بعد المائة",
        "بعد المائتين",
        "الأولى بعد",
        "الأولى بعد المائة الأولى",
        "المادة الأولى",
    ],
)
def test_non_ordinals_return_none(text: str) -> None:
    assert arabic_ordinal_to_int(text) is None


def test_normalize_arabic_collapses_forms() -> None:
    assert normalize_arabic("الأُولَى") == "الاولي"
    assert normalize_arabic("المئة") == "المائه"
    assert normalize_arabic("المئتين") == "المائتين"
    assert normalize_arabic("  الثانية   عشرة ") == "الثانيه عشره"
