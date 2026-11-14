"""ThinkingFilter through feed/flush only."""

from __future__ import annotations

import pytest

from labor_law_agent.reasoning_filter import ThinkingFilter


def _run(chunks: list[str]) -> str:
    f = ThinkingFilter()
    return "".join(f.feed(c) for c in chunks) + f.flush()


@pytest.mark.parametrize(
    ("chunks", "expected"),
    [
        (["Hello world"], "Hello world"),
        (["Hello ", "world"], "Hello world"),
        (["<thinking>plan</thinking>Answer"], "Answer"),
        (["Before <thinking>plan</thinking>after"], "Before after"),
        (["<thinking>a</thinking>One <thinking>b</thinking>two"], "One two"),
        (["<thinking>a</thinking><thinking>b</thinking>Answer"], "Answer"),
        (["<thinking>never closed"], ""),
        (["Answer <thinking>never closed"], "Answer "),
        (["<thinking>never ", "closed </think"], ""),
        (["<thinking>x</thinking>\n\n  Answer"], "Answer"),
        (["<thinking>x</thinking>", "\n", "Answer"], "Answer"),
        (["\n  Answer"], "Answer"),
        (["<thinking>x</thinking>Line one\n\nline  two"], "Line one\n\nline  two"),
        (["<thinking>فكرة</thinking>\nيستحق العامل الأجر (المادة 4)."], "يستحق العامل الأجر (المادة 4)."),
        (["مرحبا <thinking>x</thinking>", "بك"], "مرحبا بك"),
        (["a < b and c <d"], "a < b and c <d"),
        (["<"], "<"),
        (["<think"], "<think"),
        (["<thinking"], "<thinking"),
        (["</thinking>Answer"], "</thinking>Answer"),
    ],
)
def test_filter_cases(chunks: list[str], expected: str) -> None:
    assert _run(chunks) == expected


def test_lone_angle_bracket_is_held_then_released_on_flush() -> None:
    f = ThinkingFilter()
    assert f.feed("<") == ""
    assert f.flush() == "<"


def test_partial_open_tag_is_held_then_released_by_next_chunk() -> None:
    f = ThinkingFilter()
    assert f.feed("x <think") == "x "
    assert f.feed("er") == "<thinker"


def test_partial_open_tag_held_until_completed_then_hidden() -> None:
    f = ThinkingFilter()
    assert f.feed("<think") == ""
    assert f.feed("ing>secret</thinking>Answer") == "Answer"
    assert f.flush() == ""


def test_text_never_leaks_while_hidden() -> None:
    f = ThinkingFilter()
    out = [f.feed(c) for c in ["<thinking>", "secret ", "stuff", "</thinking>", "Hi"]]
    assert out == ["", "", "", "", "Hi"]


@pytest.mark.parametrize("text", ["<thinking>x</thinking>Answer", "A<thinking>xy</thinking>\nB"])
def test_every_two_way_split_gives_same_result(text: str) -> None:
    expected = _run([text])
    for i in range(len(text) + 1):
        assert _run([text[:i], text[i:]]) == expected, f"split at {i}"


@pytest.mark.parametrize("text", ["<thinking>x</thinking>Answer", "A<thinking>xy</thinking>\nB"])
def test_char_by_char_gives_same_result(text: str) -> None:
    assert _run(list(text)) == _run([text])


def test_every_three_way_split_of_tagged_text() -> None:
    text = "<thinking>x</thinking>Answer"
    for i in range(len(text) + 1):
        for j in range(i, len(text) + 1):
            assert _run([text[:i], text[i:j], text[j:]]) == "Answer", f"split at {i},{j}"


def test_split_expected_values() -> None:
    assert _run(["<thinking>x</thinking>Answer"]) == "Answer"
    assert _run(["<thi", "nking>x</thin", "king>Ans", "wer"]) == "Answer"


def test_flush_resets_hidden_state() -> None:
    f = ThinkingFilter()
    f.feed("<thinking>open")
    assert f.flush() == ""
    assert f.flush() == ""
