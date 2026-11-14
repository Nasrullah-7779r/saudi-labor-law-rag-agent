"""Removes ``<thinking>…</thinking>`` blocks from streamed model text. Pure, no I/O.

Some Bedrock models (Amazon Nova with tool use) write their reasoning inline as
``<thinking>…</thinking>`` before answering. It is not meant for end users. Tags can be split
across stream chunks, so text that could be the start of a tag is held back until the next
chunk shows whether it is one.
"""

from __future__ import annotations

OPEN_TAG = "<thinking>"
CLOSE_TAG = "</thinking>"


def _partial_tag_suffix(text: str, tag: str) -> int:
    """Length of the longest suffix of ``text`` that is a proper prefix of ``tag``."""
    for n in range(min(len(text), len(tag) - 1), 0, -1):
        if text.endswith(tag[:n]):
            return n
    return 0


class ThinkingFilter:
    """Feed it one model turn's text chunks; it returns only the visible text.

    Leading whitespace of the turn (e.g. the newline after ``</thinking>``) is dropped too.
    An unclosed ``<thinking>`` hides the rest of the turn.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._in_thinking = False
        self._started = False  # visible text already emitted this turn

    def feed(self, chunk: str) -> str:
        self._buffer += chunk
        visible: list[str] = []
        while self._buffer:
            if self._in_thinking:
                end = self._buffer.find(CLOSE_TAG)
                if end == -1:
                    keep = _partial_tag_suffix(self._buffer, CLOSE_TAG)
                    self._buffer = self._buffer[len(self._buffer) - keep :] if keep else ""
                    break
                self._buffer = self._buffer[end + len(CLOSE_TAG) :]
                self._in_thinking = False
                continue
            start = self._buffer.find(OPEN_TAG)
            if start == -1:
                keep = _partial_tag_suffix(self._buffer, OPEN_TAG)
                cut = len(self._buffer) - keep
                visible.append(self._buffer[:cut])
                self._buffer = self._buffer[cut:]
                break
            visible.append(self._buffer[:start])
            self._buffer = self._buffer[start + len(OPEN_TAG) :]
            self._in_thinking = True
        return self._emit("".join(visible))

    def flush(self) -> str:
        """End of the turn: release held-back text that turned out not to be a tag."""
        rest = "" if self._in_thinking else self._buffer
        self._buffer = ""
        self._in_thinking = False
        return self._emit(rest)

    def _emit(self, text: str) -> str:
        if not self._started:
            text = text.lstrip()
            self._started = bool(text)
        return text
