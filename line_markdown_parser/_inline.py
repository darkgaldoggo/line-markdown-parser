"""Inline normalization and typed syntax tokens, independent of Flex layout."""

from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TypeAlias, TypedDict

from ._syntax import (
    _inline_code_span_ranges,
    _InlineLink,
    _is_escaped,
    _iter_inline_code_spans,
    _iter_links,
    _position_inside_ranges,
    _strip_plain_url_punctuation,
)


class InlineStyle(TypedDict, total=False):
    bold: bool
    italic: bool
    strike: bool
    code: bool


@dataclass(frozen=True)
class TextToken:
    text: str
    style: InlineStyle


@dataclass(frozen=True)
class LinkToken:
    link: _InlineLink
    style: InlineStyle


InlineToken: TypeAlias = TextToken | LinkToken

_ESCAPABLE_INLINE_CHARS = set("\\`*_{}[]()#+-.!<>~")
_INLINE_DELIMITERS: tuple[tuple[str, InlineStyle], ...] = (
    ("***", {"bold": True, "italic": True}),
    ("___", {"bold": True, "italic": True}),
    ("**", {"bold": True}),
    ("__", {"bold": True}),
    ("~~", {"strike": True}),
    ("*", {"italic": True}),
    ("_", {"italic": True}),
)


def _transform_outside_inline_code(
    text: str, transform: Callable[[str], str], *, normalize_html_code: bool = False
) -> str:
    """コードを一時的に保護し、その外側だけに文字列置換を適用する。"""
    ranges = [
        (start, end, text[start:end]) for start, end, _ in _iter_inline_code_spans(text)
    ]
    code_starts = [start for start, _, _ in ranges]

    def code_end_at(position: int, minimum_start: int) -> int | None:
        index = bisect_right(code_starts, position) - 1
        # 先に処理したHTML code内のバッククォートは、後続のタグを保護しない。
        if (
            index >= 0
            and ranges[index][0] >= minimum_start
            and position < ranges[index][1]
        ):
            return ranges[index][1]
        return None

    opening_pattern = re.compile(r"<code\b", re.IGNORECASE)
    closing_pattern = re.compile(r"</code>", re.IGNORECASE)
    cursor = 0
    while opening := opening_pattern.search(text, cursor):
        if code_end := code_end_at(opening.start(), cursor):
            cursor = code_end
            continue
        tag_end = text.find(">", opening.end())
        if tag_end == -1:
            break
        closing = closing_pattern.search(text, tag_end + 1)
        if closing is None:
            break
        replacement = text[opening.start() : closing.end()]
        if normalize_html_code:
            body = text[tag_end + 1 : closing.start()]
            delimiter = "`" * (
                max((len(run) for run in re.findall(r"`+", body)), default=0) + 1
            )
            replacement = f"{delimiter} {body} {delimiter}"
        ranges.append((opening.start(), closing.end(), replacement))
        cursor = closing.end()
    if not ranges:
        return transform(text)

    prefix = "\x00code:"
    while prefix in text:
        prefix += ":"
    fragments: list[str] = []
    protected: list[str] = []
    cursor = 0
    for start, end, replacement in sorted(ranges):
        if start < cursor:
            continue
        fragments.extend((text[cursor:start], f"{prefix}{len(protected)}\x00"))
        protected.append(replacement)
        cursor = end
    fragments.append(text[cursor:])
    transformed = transform("".join(fragments))
    return re.sub(
        re.escape(prefix) + r"(\d+)\x00",
        lambda match: protected[int(match.group(1))],
        transformed,
    )


def _normalize_inline_html_lite(text: str) -> str:
    """対応するインラインHTMLタグをMarkdown記法に置き換える。"""
    if not text or "<" not in text:
        return text
    tag_replacements: tuple[tuple[str, str, str], ...] = (
        ("strong", "**", "**"),
        ("b", "**", "**"),
        ("em", "*", "*"),
        ("i", "*", "*"),
        ("s", "~~", "~~"),
        ("del", "~~", "~~"),
    )

    def replace_tags(source: str) -> str:
        for tag, opener, closer in tag_replacements:
            # Pair the first opening tag with the next closing tag, as before,
            # but advance both cursors instead of rescanning an unmatched suffix.
            closings = list(re.finditer(f"</{tag}>", source, re.IGNORECASE))
            closing_index = 0
            cursor = 0
            fragments: list[str] = []
            for opening in re.finditer(f"<{tag}\\b", source, re.IGNORECASE):
                if opening.start() < cursor:
                    continue
                tag_end = source.find(">", opening.end())
                if tag_end == -1:
                    break
                while (
                    closing_index < len(closings)
                    and closings[closing_index].start() <= tag_end
                ):
                    closing_index += 1
                if closing_index == len(closings):
                    break
                closing = closings[closing_index]
                fragments.extend(
                    (
                        source[cursor : opening.start()],
                        opener,
                        source[tag_end + 1 : closing.start()],
                        closer,
                    )
                )
                cursor = closing.end()
                closing_index += 1
            fragments.append(source[cursor:])
            source = "".join(fragments)
        return source

    return _transform_outside_inline_code(text, replace_tags, normalize_html_code=True)


def _can_open_inline_delimiter(text: str, index: int, delimiter: str) -> bool:
    after_index = index + len(delimiter)
    if after_index >= len(text) or text[after_index].isspace():
        return False
    if _is_escaped(text, index):
        return False
    if delimiter.startswith("_"):
        before = text[index - 1] if index > 0 else ""
        after = text[after_index]
        if before.isalnum() and after.isalnum():
            return False
    return True


def _can_close_inline_delimiter(text: str, index: int, delimiter: str) -> bool:
    before = text[index - 1] if index > 0 else ""
    if not before or before.isspace():
        return False
    if _is_escaped(text, index):
        return False
    if delimiter.startswith("_"):
        after_index = index + len(delimiter)
        after = text[after_index] if after_index < len(text) else ""
        if before.isalnum() and after.isalnum():
            return False
    return True


def _find_closing_inline_delimiter(
    text: str,
    start: int,
    delimiter: str,
    code_ranges: list[tuple[int, int]] | None = None,
    *,
    cache: dict[str, list[int]] | None = None,
) -> int | None:
    """同じ本文・保護範囲の閉じ記号を共有し、未閉じ記号ごとの再探索を避ける。"""
    if cache is None:
        cache = {}
    if delimiter not in cache:
        positions: list[int] = []
        protected = sorted(code_ranges or [])
        range_index = 0
        cursor = 0
        while cursor < len(text):
            found_at = text.find(delimiter, cursor)
            if found_at == -1:
                break
            while (
                range_index < len(protected) and protected[range_index][1] <= found_at
            ):
                range_index += 1
            inside_protected = (
                range_index < len(protected) and protected[range_index][0] <= found_at
            )
            if not inside_protected and _can_close_inline_delimiter(
                text, found_at, delimiter
            ):
                positions.append(found_at)
            cursor = found_at + 1
        cache[delimiter] = positions
    positions = cache[delimiter]
    position_index = bisect_left(positions, start)
    return positions[position_index] if position_index < len(positions) else None


def _find_unclosed_inline_delimiter(text: str) -> tuple[str, int] | None:
    code_ranges = _inline_code_span_ranges(text)
    closing_cache: dict[str, list[int]] = {}
    index = 0
    while index < len(text):
        if _position_inside_ranges(index, code_ranges):
            index += 1
            continue
        matched = False
        for delimiter, _style_update in _INLINE_DELIMITERS:
            if not text.startswith(delimiter, index):
                continue
            if not _can_open_inline_delimiter(text, index, delimiter):
                continue
            inner_start = index + len(delimiter)
            closing_index = _find_closing_inline_delimiter(
                text, inner_start, delimiter, code_ranges, cache=closing_cache
            )
            if closing_index is None:
                return (delimiter, index)
            index = closing_index + len(delimiter)
            matched = True
            break
        if not matched:
            index += 1
    return None


def _inline_links(text: str, code_ranges: list[tuple[int, int]]) -> list[_InlineLink]:
    """リンクの範囲を返す。URL内の記号を外側の強調と混同しないために使う。"""
    links: list[_InlineLink] = []
    prefix = ""
    previous_end = 0
    for link in _iter_links(text, code_ranges=code_ranges):
        start, end = link.start, link.end
        if _position_inside_ranges(start, code_ranges):
            continue
        prefix += text[previous_end:start]
        if link.kind == "plain":
            url = _strip_plain_url_punctuation(link.url)
            opener = _find_unclosed_inline_delimiter(prefix + "x")
            if opener and url.endswith(opener[0]):
                url = url[: -len(opener[0])]
            end = start + len(url)
        links.append(
            replace(
                link,
                end=end,
                url=text[start:end] if link.kind == "plain" else link.url,
                text=text[start:end],
            )
        )
        prefix += "x"
        previous_end = end
    return links


def _parse_inline_tokens(
    text: str, style: InlineStyle, *, parse_links: bool = False, _depth: int = 0
) -> list[InlineToken]:
    """インラインのMarkdownを解析し、リンクの前後にも同じ強調を適用する。

    インラインコードを優先して処理し、その範囲を保持して強調の開始・終了記号を対応付ける。
    これにより **`code`** のような記法を扱う。コード内のMarkdownは装飾として解釈しない。
    parse_linksが有効な場合、位置と宛先を保持したLinkTokenを返す。
    アクション行への分離は強調範囲の確定後に行う。
    """
    if _depth >= 64:
        span = TextToken(text, style) if text else None
        return [span] if span else []
    spans: list[InlineToken] = []
    buffer: list[str] = []
    index = 0
    code_spans = _iter_inline_code_spans(text)
    code_span_by_start = {
        start: (end, code_text) for start, end, code_text in code_spans
    }
    code_ranges = [(start, end) for start, end, _ in code_spans]
    links = _inline_links(text, code_ranges) if parse_links else []
    link_ranges = [(link.start, link.end) for link in links]
    link_by_start = {link.start: link for link in links}
    protected_ranges = code_ranges + link_ranges
    closing_cache: dict[str, list[int]] = {}

    def flush_text() -> None:
        if buffer:
            span = TextToken("".join(buffer), style)
            if span:
                spans.append(span)
            buffer.clear()

    while index < len(text):
        char = text[index]
        if (
            char == "\\"
            and index + 1 < len(text)
            and (text[index + 1] in _ESCAPABLE_INLINE_CHARS)
        ):
            buffer.append(text[index + 1])
            index += 2
            continue
        if index in code_span_by_start:
            end, code_text = code_span_by_start[index]
            flush_text()
            code_style = style.copy()
            code_style["code"] = True
            span = TextToken(code_text, code_style) if code_text else None
            if span:
                spans.append(span)
            index = end
            continue
        if index in link_by_start:
            link = link_by_start[index]
            end = link.end
            flush_text()
            spans.append(LinkToken(link, style.copy()))
            index = end
            continue
        matched = False
        for delimiter, style_update in _INLINE_DELIMITERS:
            if not text.startswith(delimiter, index):
                continue
            if not _can_open_inline_delimiter(text, index, delimiter):
                continue
            inner_start = index + len(delimiter)
            closing_index = _find_closing_inline_delimiter(
                text, inner_start, delimiter, protected_ranges, cache=closing_cache
            )
            if closing_index is None:
                continue
            inner_text = text[inner_start:closing_index]
            if not inner_text.strip():
                continue
            flush_text()
            child_style = style.copy()
            child_style.update(style_update)
            spans.extend(
                _parse_inline_tokens(
                    inner_text, child_style, parse_links=parse_links, _depth=_depth + 1
                )
            )
            index = closing_index + len(delimiter)
            matched = True
            break
        if matched:
            continue
        if char in "*_":
            run_end = index
            while run_end < len(text) and text[run_end] == char:
                run_end += 1
            before = text[index - 1] if index else ""
            after = text[run_end] if run_end < len(text) else ""
            if run_end - index in (2, 3) and (
                not (before.isalnum() and after.isalnum())
            ):
                index = run_end
                continue
        buffer.append(char)
        index += 1
    flush_text()
    return spans


def parse_inline(
    text: str, style: InlineStyle | None = None, *, links: bool = True
) -> list[InlineToken]:
    """Normalize supported inline HTML, then parse one shared inline grammar."""
    return _parse_inline_tokens(
        _normalize_inline_html_lite(text), (style or {}).copy(), parse_links=links
    )
