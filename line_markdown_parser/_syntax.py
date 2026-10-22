"""Lexical ranges shared by inline parsing and size-aware splitting."""

from __future__ import annotations

import re
from bisect import bisect_right
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```")


@dataclass(frozen=True)
class FencedSegment:
    text: str
    is_code: bool = False


@dataclass(frozen=True)
class CodeFence:
    body: str
    language: str
    opening: str

    def wrap(self, body: str) -> str:
        return self.opening + "\n" + body + "\n```"


def parse_code_fence(source: str) -> CodeFence:
    """Share language/body recognition between layout and splitting.

    An unrecognized first line is code, not a header to repeat in every chunk.
    Keep all body characters except the closing fence's separating newline.
    """
    body = source[3:-3]
    language = ""
    opening = "```"
    if "\n" in body:
        first, rest = body.split("\n", 1)
        candidate = first.strip()
        if not candidate or re.fullmatch(r"[A-Za-z0-9_+#.\-]+", candidate):
            language = candidate
            opening += first
            body = rest
    if body.endswith("\n"):
        body = body[:-1]
    return CodeFence(body, language, opening)


def iter_fenced_segments(text: str) -> Iterator[FencedSegment]:
    """Recognize the same closed triple-backtick subset for rendering and splitting."""
    cursor = 0
    for match in _CODE_FENCE_RE.finditer(text):
        if match.start() > cursor:
            yield FencedSegment(text[cursor : match.start()])
        yield FencedSegment(match.group(), is_code=True)
        cursor = match.end()
    if cursor < len(text):
        yield FencedSegment(text[cursor:])


_CORE_URL_PATTERN = "https?:\\/\\/[\\w\\-\\.~:\\/?#[\\]@!$&\\'\\(\\)\\*\\+,;=%.]+"
_MARKDOWN_DESTINATION_PATTERN = "(?:<[^>\\n]+>|(?:[^\\s()<>]|\\([^\\s()<>]*\\))+)"
_MARKDOWN_DESTINATION_RE = re.compile(
    f"\\(\\s*(?P<url>{_MARKDOWN_DESTINATION_PATTERN})\\s*\\)"
)
_URL_LINK_PATTERN = re.compile(
    f"(?P<autolink><(?P<auto_url>{_CORE_URL_PATTERN})>)|(?P<plain_url>{_CORE_URL_PATTERN})"
)
_URL_START_PATTERN = re.compile(r"<?https?://")


@dataclass(frozen=True)
class _InlineLink:
    start: int
    end: int
    kind: Literal["markdown", "autolink", "plain"]
    text: str
    url: str
    label: str | None = None


def _iter_links(
    text: str, *, code_ranges: list[tuple[int, int]] | None = None
) -> Iterator[_InlineLink]:
    """ラベルの括弧を一度だけ走査し、コードとエスケープを除外してリンクを返す。"""
    code_ends: dict[int, int] = {}
    if code_ranges is not None:
        # Joined inline blocks already have a consistent full-text code scan.
        code_ends.update(code_ranges)
    else:
        # Splitting can detach backticks on other lines. Keep line-local ranges
        # there so a newly exposed Markdown link cannot acquire a partial URI.
        offset = 0
        for line in text.split("\n"):
            code_ends.update(
                (offset + start, offset + end)
                for start, end, _ in _iter_inline_code_spans(line)
            )
            offset += len(line) + 1
    links: list[_InlineLink] = []
    opening: int | None = None
    index = 0
    while index < len(text):
        if index in code_ends:
            index = code_ends[index]
            continue
        if text[index] == "\\" and index + 1 < len(text):
            index += 2
            continue
        if text[index] == "[":
            opening = index
        elif text[index] == "]":
            if opening is not None:
                destination = _MARKDOWN_DESTINATION_RE.match(text, index + 1)
                if destination:
                    end = destination.end()
                    links.append(
                        _InlineLink(
                            opening,
                            end,
                            "markdown",
                            text[opening:end],
                            destination.group("url"),
                            text[opening + 1 : index],
                        )
                    )
                    index = end - 1
            opening = None
        index += 1
    index = 0
    cursor = 0
    while cursor < len(text):
        while index < len(links) and links[index].start < cursor:
            index += 1
        link = links[index] if index < len(links) else None
        # Markdownの手前でURLの開始だけを探し、宛先内のURLを再走査しない。
        boundary = link.start if link is not None else len(text)
        candidate = _URL_START_PATTERN.search(text, cursor, boundary)
        if candidate is None and link is not None:
            yield link
            cursor = link.end
            index += 1
        elif candidate is not None:
            # Explicit autolinks, and Markdown-looking text in a URL's path,
            # query or fragment, remain part of that URL. A Markdown link right
            # after the authority starts a separate token instead of corrupting
            # the hostname (https://example.com[Guide](...)).
            limit = len(text) if text[candidate.start()] == "<" else boundary
            match = _URL_LINK_PATTERN.match(text, candidate.start(), limit)
            if match is not None and link is not None and match.end() == boundary:
                plain = match.group("plain_url")
                if plain and any(char in plain.partition("://")[2] for char in "/?#"):
                    match = _URL_LINK_PATTERN.match(text, candidate.start())
            if match is None:
                cursor = candidate.start() + 1
                continue
            autolink = match.group("autolink") is not None
            yield _InlineLink(
                match.start(),
                match.end(),
                "autolink" if autolink else "plain",
                match.group(),
                match.group("auto_url" if autolink else "plain_url"),
            )
            cursor = match.end()
        else:
            break


def _is_escaped(text: str, index: int) -> bool:
    """index位置の文字が、直前の奇数個のバックスラッシュでエスケープされているか判定する。"""
    slash_count = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        slash_count += 1
        cursor -= 1
    return slash_count % 2 == 1


def _iter_inline_code_spans(text: str) -> list[tuple[int, int, str]]:
    """インラインコードを (開始位置, 終了位置, 正規化した本文) のタプルで列挙する。

    終了位置は閉じるバッククォートの直後。本文の改行と連続する空白を半角スペース1つにまとめる。
    強調の解析でもこの範囲を使い、**`code`** のような記法を処理する。
    """
    spans: list[tuple[int, int, str]] = []
    index = 0
    while index < len(text):
        if text[index] != "`" or _is_escaped(text, index):
            index += 1
            continue
        run_end = index
        while run_end < len(text) and text[run_end] == "`":
            run_end += 1
        delimiter = text[index:run_end]
        closing = run_end
        closing_index: int | None = None
        while closing < len(text):
            candidate = text.find(delimiter, closing)
            if candidate == -1:
                break
            if not _is_escaped(text, candidate):
                closing_index = candidate
                break
            closing = candidate + 1
        if closing_index is None:
            index = run_end
            continue
        code_text = text[run_end:closing_index]
        code_text = re.sub("\\s+", " ", code_text.replace("\n", " ")).strip(" ")
        end = closing_index + len(delimiter)
        spans.append((index, end, code_text))
        index = end
    return spans


def _inline_code_span_ranges(text: str) -> list[tuple[int, int]]:
    """インラインコードの範囲を、バッククォートも含めて返す。"""
    return [(start, end) for start, end, _ in _iter_inline_code_spans(text)]


def _position_inside_ranges(position: int, ranges: list[tuple[int, int]]) -> bool:
    """開始位置順で重複のない範囲から、指定位置を二分探索する。"""
    index = bisect_right(ranges, position, key=lambda interval: interval[0]) - 1
    return index >= 0 and position < ranges[index][1]


def _strip_plain_url_punctuation(url: str) -> str:
    while url and url[-1] in ".,;:!?)>":
        if (
            url[-1] == ")"
            and "(" in url[:-1]
            and (url[:-1].count("(") >= url.count(")"))
        ):
            break
        url = url[:-1]
    return url
