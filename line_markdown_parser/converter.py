"""Public conversion API and size-aware splitting.

All results are fresh JSON-compatible dictionaries. No input is logged, cached
across calls, sent over the network, or written to disk.
"""

from __future__ import annotations

import json
from bisect import bisect_right
from collections import OrderedDict
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from sys import getsizeof
from typing import Any, cast

from ._flex import FlexBubble, FlexComponent, FlexMessage
from ._renderer import build_flex_contents as _render_contents
from ._syntax import _iter_links, iter_fenced_segments, parse_code_fence

DEFAULT_MAX_FLEX_PAYLOAD_BYTES = 28_000
_MAX_BUBBLE_BYTES = 30_000
_MAX_ALT_TEXT_UNITS = 1_500
_MAX_INPUT_BYTES = 200_000


def _require_text(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if any(0xD800 <= ord(char) <= 0xDFFF for char in text):
        raise ValueError("text must contain valid Unicode scalar values")
    if len(text.encode("utf-8")) > _MAX_INPUT_BYTES:
        raise ValueError("text exceeds the 200,000-byte UTF-8 input limit")
    return text


def build_flex_contents(text: str) -> list[dict[str, Any]]:
    """Build body components without a bubble, footer, or delivery metadata.

    This low-level function does not split or enforce the bubble byte limit.
    """
    _require_text(text)
    return cast(list[dict[str, Any]], _body_contents(text))


def _body_contents(text: str) -> list[FlexComponent]:
    if not text.strip():
        return []
    contents = _render_contents(text)
    # Separators alone can be removed by the renderer. A bubble cannot be empty.
    return contents or [{"type": "text", "text": text.strip(), "wrap": True}]


def _bubble(text: str) -> FlexBubble:
    contents = _body_contents(text)
    if contents:
        # Block margins separate siblings; the outer padding defines the inset.
        contents[0]["margin"] = "none"
    return {
        "type": "bubble",
        "size": "giga",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": contents,
            "paddingAll": "16px",
            "backgroundColor": "#FFFFFF",
        },
    }


def _json_size(value: object) -> int:
    return len(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )


@dataclass(frozen=True)
class _RenderCacheEntry:
    size: int
    bubble: FlexBubble | None
    cost: int


class _RenderSession:
    """Reuse candidate sizes/layouts only for one conversion or split call.

    Oversized bubbles cannot be outputs, so only retain their size. Bound source
    keys and serialized layouts together; an entry limit bounds index overhead.
    Eviction releases the source, size, and layout as one unit. Every exported
    message receives its own mutable object tree.
    """

    _MAX_CACHED_BYTES = 8_000_000
    _MAX_CACHED_ENTRIES = 1024

    def __init__(self) -> None:
        self.entries: OrderedDict[str, _RenderCacheEntry] = OrderedDict()
        self.cached_bytes = 0

    def _render(self, text: str) -> tuple[FlexBubble, int]:
        bubble = _bubble(text)
        size = _json_size(bubble)
        retained = bubble if size <= _MAX_BUBBLE_BYTES else None
        cost = getsizeof(text) + (size if retained is not None else 0)
        previous = self.entries.pop(text, None)
        if previous is not None:
            self.cached_bytes -= previous.cost
        if cost <= self._MAX_CACHED_BYTES and self._MAX_CACHED_ENTRIES > 0:
            while self.entries and (
                self.cached_bytes + cost > self._MAX_CACHED_BYTES
                or len(self.entries) >= self._MAX_CACHED_ENTRIES
            ):
                _, oldest = self.entries.popitem(last=False)
                self.cached_bytes -= oldest.cost
            self.entries[text] = _RenderCacheEntry(size, retained, cost)
            self.cached_bytes += cost
        return bubble, size

    def size(self, text: str) -> int:
        cached = self.entries.get(text)
        return cached.size if cached is not None else self._render(text)[1]

    def message(self, text: str, alt_text: str | None) -> FlexMessage:
        cached = self.entries.get(text)
        bubble = cached.bubble if cached is not None else None
        if bubble is None:
            bubble, _ = self._render(text)
        return {
            "type": "flex",
            "altText": _alt_text(text) if alt_text is None else alt_text,
            "contents": deepcopy(bubble),
        }


def estimate_flex_payload_size(text: str) -> int:
    """Return compact UTF-8 JSON bytes of the bubble (not the HTTP envelope).

    Use the same JSON serialization for delivery. The default split budget
    reserves 2,000 bytes below LINE's 30 KB bubble limit.
    """
    return _json_size(_bubble(_require_text(text)))


def _alt_text(text: str) -> str:
    text = _require_text(text).strip()
    if not text:
        raise ValueError("alt_text must not be empty")
    units = 0
    end = 0
    for end, char in enumerate(text, start=1):
        units += 2 if ord(char) > 0xFFFF else 1
        if units > _MAX_ALT_TEXT_UNITS:
            # The truncation marker itself consumes one UTF-16 code unit.
            prefix = text[: end - 1]
            while len(prefix.encode("utf-16-le")) // 2 >= _MAX_ALT_TEXT_UNITS:
                prefix = prefix[:-1]
            return prefix + "…"
    return text


def build_flex_message(text: str, *, alt_text: str | None = None) -> dict[str, Any]:
    """Build one standalone Flex message; raise ValueError if it exceeds 30 KB.

    Use convert_markdown_to_line_messages for automatic splitting. alt_text
    defaults to the source text and is bounded to 1,500 UTF-16 code units.
    """
    _require_text(text)
    if not text.strip():
        raise ValueError("text must not be empty")
    bubble = _bubble(text)
    if _json_size(bubble) > _MAX_BUBBLE_BYTES:
        raise ValueError(
            "bubble exceeds 30,000 bytes; use convert_markdown_to_line_messages"
        )
    message: FlexMessage = {
        "type": "flex",
        "altText": _alt_text(text if alt_text is None else alt_text),
        "contents": bubble,
    }
    return cast(dict[str, Any], message)


def _validate_limits(max_length: int, max_payload_bytes: int) -> None:
    if (
        isinstance(max_length, bool)
        or not isinstance(max_length, int)
        or max_length < 1
    ):
        raise ValueError("max_length must be a positive integer")
    if (
        isinstance(max_payload_bytes, bool)
        or not isinstance(max_payload_bytes, int)
        or not 1 <= max_payload_bytes <= _MAX_BUBBLE_BYTES
    ):
        raise ValueError("max_payload_bytes must be an integer between 1 and 30,000")


def split_long_text(
    text: str,
    max_length: int = 1600,
    max_payload_bytes: int = DEFAULT_MAX_FLEX_PAYLOAD_BYTES,
) -> list[str]:
    """Split Markdown into pieces that fit both source length and rendered bytes.

    Prefer paragraph/line/word boundaries. Closed triple-backtick code fences
    are repeated around each code fragment, including a single oversized line.
    Other inline syntax may become plain text when split. Impossible budgets
    raise ValueError; no over-budget fragment is returned.
    """
    _require_text(text)
    _validate_limits(max_length, max_payload_bytes)
    return _split_long_text(text, max_length, max_payload_bytes, _RenderSession())


def _split_long_text(
    text: str, max_length: int, max_payload_bytes: int, session: _RenderSession
) -> list[str]:
    if not text.strip():
        return []

    def fits(candidate: str) -> bool:
        return (
            len(candidate) <= max_length
            and session.size(candidate) <= max_payload_bytes
        )

    def split_unit(
        body: str, wrap: Callable[[str], str], *, preserve_links: bool = False
    ) -> list[str]:
        if fits(wrap(body)):
            return [wrap(body)]
        pieces: list[str] = []
        start = 0
        overhead = len(wrap(""))
        link_ranges = (
            [(link.start, link.end) for link in _iter_links(body)]
            if preserve_links
            else []
        )
        links_by_start = dict(link_ranges)
        link_starts = [start for start, _ in link_ranges]

        def safe_boundary(end: int) -> int:
            index = bisect_right(link_starts, end) - 1
            if index >= 0:
                link_start, link_end = link_ranges[index]
                if link_start < end < link_end:
                    return link_start
            return end

        while start < len(body):
            end = safe_boundary(min(len(body), start + max_length - overhead))
            while end > start and not fits(wrap(body[start:end])):
                end = safe_boundary(start + (end - start) * 3 // 4)
            if end <= start:
                # Shrinking is conservative, and can jump past a whole link.
                # Try that atomic token before declaring the budget impossible.
                link_end = links_by_start.get(start)
                if link_end is not None and fits(wrap(body[start:link_end])):
                    end = link_end
            if end <= start:
                raise ValueError(
                    "limits are too small for a rendered fragment or intact link"
                )
            if end < len(body):
                # Keep at least half the fitting candidate to avoid tiny chunks.
                for separator in ("\n\n", "\n", " "):
                    boundary = body.rfind(separator, start + (end - start) // 2, end)
                    if boundary >= 0:
                        preferred_end = safe_boundary(boundary + len(separator))
                        if preferred_end > start and fits(
                            wrap(body[start:preferred_end])
                        ):
                            end = preferred_end
                            break
            pieces.append(wrap(body[start:end]))
            start = end
        if not pieces:
            raise ValueError("limits are too small for an empty fenced block")
        return pieces

    if fits(text):
        return [text]

    chunks: list[str] = []
    for fenced in iter_fenced_segments(text):
        segment = fenced.text
        if fenced.is_code:
            fence = parse_code_fence(segment)
            chunks.extend(split_unit(fence.body, fence.wrap))
        else:
            chunks.extend(split_unit(segment, lambda piece: piece, preserve_links=True))

    parts: list[str] = []
    current = ""
    for chunk in chunks:
        candidate = current + chunk
        if not current or fits(candidate):
            current = candidate
        else:
            if current.strip():
                parts.append(current)
            current = chunk
    if current.strip():
        parts.append(current)
    # Validate rendered output after every boundary decision; Markdown size is
    # not monotonic with source length (a closing delimiter can change layout).
    if any(not fits(part) for part in parts):
        raise ValueError("unable to split text within the requested limits")
    return parts


def convert_markdown_to_line_messages(
    text: str,
    *,
    alt_text: str | None = None,
    max_length: int = 1600,
    max_payload_bytes: int = DEFAULT_MAX_FLEX_PAYLOAD_BYTES,
) -> list[dict[str, Any]]:
    """Convert Markdown to ordered standalone Flex messages, without sending.

    Empty input returns []. The caller manages LINE's five-message request
    limit and delivery. This function never truncates the message list.
    """
    normalized_alt = _alt_text(alt_text) if alt_text is not None else None
    _require_text(text)
    _validate_limits(max_length, max_payload_bytes)
    session = _RenderSession()
    parts = _split_long_text(text, max_length, max_payload_bytes, session)
    return [
        cast(dict[str, Any], session.message(part, normalized_alt)) for part in parts
    ]
