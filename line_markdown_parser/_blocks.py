"""Block recognition for the supported Markdown subset; no Flex generation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from ._inline import (
    _find_closing_inline_delimiter,
    _find_unclosed_inline_delimiter,
    _transform_outside_inline_code,
)
from ._syntax import _inline_code_span_ranges, iter_fenced_segments, parse_code_fence


@dataclass(frozen=True)
class Block:
    kind: Literal[
        "paragraph",
        "spacer",
        "code",
        "table",
        "quote",
        "heading",
        "list",
        "separator",
        "marker",
        "indent",
    ]
    text: str = ""
    lines: tuple[str, ...] = ()
    level: int = 0
    bullet: str = ""
    ordered: bool = False
    is_task: bool = False
    language: str = ""


_MARKDOWN_HARD_BREAK_RE = re.compile("( {2,}|<br\\s*/?>)\\s*$", flags=re.IGNORECASE)
_UNORDERED_LIST_MATCH_RE = re.compile(
    "^(\\s*)(?:(?:[-*+‐•]\\s+)|(?:・\\s*))([\\s\\S]+)$"
)
_LIST_ITEM_MARKER_RE = re.compile(
    "^\\s*(?:(?:[-*+‐•]\\s+)|(?:・\\s*)|\\d+[.)]\\s+)(?P<text>.*)$"
)
_LIST_ITEM_TITLE_CONTENT_RE = re.compile("^(\\*{1,3})(?!\\s).+?(?<!\\s)\\1(?:[:：])?$")
_TABLE_BLOCK_TERMINATOR_RE = re.compile(
    "^\\s*(?:#{1,6}\\s+|(?:[-*+‐•]\\s+|・\\s*)|\\d+[.)]\\s+|>)"
)


def is_char_emoji(char: str) -> bool:
    """文字が絵文字の主要なUnicode範囲に含まれるか判定する。"""
    if not char:
        return False
    code = ord(char)
    return (
        127744 <= code <= 128511
        or 128512 <= code <= 128591
        or 128640 <= code <= 128767
        or (129280 <= code <= 129535)
        or (9728 <= code <= 9983)
        or (9984 <= code <= 10175)
        or (129648 <= code <= 129791)
    )


def _ends_with_markdown_hard_break(text: str) -> bool:
    """末尾行が Markdown のハード改行マーカー（末尾2スペース / <br>）で終わるか判定する。"""
    last_line = text.split("\n")[-1]
    return bool(_MARKDOWN_HARD_BREAK_RE.search(last_line))


def _strip_markdown_hard_break(text: str) -> str:
    """末尾行の Markdown ハード改行マーカー（末尾2スペース / <br>）を除去する。"""
    lines = text.split("\n")
    if not lines:
        return text
    lines[-1] = _MARKDOWN_HARD_BREAK_RE.sub("", lines[-1])
    return "\n".join(lines)


def _looks_like_list_item_title_line(text: str) -> bool:
    """リストの末尾行がタイトルとみなせる場合にTrueを返す（改行として扱う）。"""
    last_line = text.split("\n")[-1].rstrip()
    match = _LIST_ITEM_MARKER_RE.match(last_line)
    if not match:
        return False
    item_text = (match.group("text") or "").strip()
    if not item_text:
        return False
    if item_text.endswith((":", "：")):
        return True
    return bool(_LIST_ITEM_TITLE_CONTENT_RE.fullmatch(item_text))


def _allows_multiline_inline_continuation(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith(">"):
        return False
    if re.match("^(#{1,6})\\s+(.*)", stripped):
        return False
    if re.match("^(\\s*)(?:[-‐]{3,}|\\*{3,}|_{3,})\\s*$", stripped):
        return False
    if _UNORDERED_LIST_MATCH_RE.match(line):
        return False
    if _ORDERED_LIST_START_RE.match(line):
        return False
    if re.match("^\\s+.+", line):
        return False
    return True


def _collect_multiline_inline_block(
    lines: list[str], start_index: int, closing_line_cache: dict[str, list[int | None]]
) -> tuple[str, int] | None:
    start_line = lines[start_index].strip()
    opener = _find_unclosed_inline_delimiter(start_line)
    if opener is None:
        return None
    delimiter, opener_index = opener
    if (
        _find_closing_inline_delimiter(
            start_line,
            opener_index + len(delimiter),
            delimiter,
            _inline_code_span_ranges(start_line),
        )
        is not None
    ):
        return None
    if delimiter not in closing_line_cache:
        closing_lines: list[int | None] = [None] * len(lines)
        next_closing_line: int | None = None
        for index in range(len(lines) - 1, -1, -1):
            closing_lines[index] = next_closing_line
            line = lines[index]
            if not _allows_multiline_inline_continuation(line):
                next_closing_line = None
            elif (
                _find_closing_inline_delimiter(
                    line.strip(), 0, delimiter, _inline_code_span_ranges(line.strip())
                )
                is not None
            ):
                next_closing_line = index
        closing_line_cache[delimiter] = closing_lines
    closing_line = closing_line_cache[delimiter][start_index]
    if closing_line is None:
        return None
    joined = "\n".join(line.strip() for line in lines[start_index : closing_line + 1])
    return (joined, closing_line + 1)


def _is_markdown_table_separator(line: str) -> bool:
    stripped = line.strip()
    if "|" not in stripped:
        return False
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    if len(cells) < 2:
        return False
    return all(re.fullmatch(":?-{3,}:?", cell or "") for cell in cells)


def _looks_like_markdown_table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    header = lines[index].strip()
    if "|" not in header or header.count("|") < 1:
        return False
    return _is_markdown_table_separator(lines[index + 1])


def _task_list_prefix(raw_list_item_text: str) -> tuple[str, str]:
    task_match = re.match(
        "^\\[(?P<mark>[ xX])\\]\\s+(?P<text>[\\s\\S]+)$", raw_list_item_text
    )
    if not task_match:
        return ("", raw_list_item_text)
    marker = "☑ " if task_match.group("mark").lower() == "x" else "☐ "
    return (marker, task_match.group("text").strip())


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")
_SEPARATOR_RE = re.compile(r"^(\s*)(?:[-‐]{3,}|\*{3,}|_{3,})\s*$")
_ORDERED_LIST_START_RE = re.compile(r"^(\s*)(\d+)([.)])\s+(.*)")
_ORDERED_LIST_RE = re.compile(r"^(\s*)(\d+)([.)])\s+([\s\S]+)")


def _normalize_lines(segment: str) -> list[str]:
    segment = "\n".join(
        _transform_outside_inline_code(
            line, lambda source: re.sub(r"<br\s*/?>", "\n", source, flags=re.IGNORECASE)
        )
        for line in segment.split("\n")
    )
    normalized: list[str] = []
    prev_was_list = False
    for line in segment.strip().split("\n"):
        stripped = line.strip()
        separator = _SEPARATOR_RE.match(stripped)
        is_list = bool(
            (_UNORDERED_LIST_MATCH_RE.match(line) if not separator else None)
            or _ORDERED_LIST_START_RE.match(line)
        )
        if (
            not is_list
            and prev_was_list
            and stripped
            and line[:1].isspace()
            and not _HEADING_RE.match(stripped)
            and not separator
        ):
            continuation = line.lstrip()
            previous = normalized[-1]
            if _ends_with_markdown_hard_break(
                previous
            ) or _looks_like_list_item_title_line(previous):
                normalized[-1] = (
                    _strip_markdown_hard_break(previous).rstrip() + "\n" + continuation
                )
            else:
                normalized[-1] = previous.rstrip() + " " + continuation
            continue
        normalized.append(line)
        prev_was_list = is_list
    return normalized


def _parse_lines(lines: list[str]) -> list[Block]:
    blocks: list[Block] = []
    paragraph: list[str] = []
    closing_cache: dict[str, list[int | None]] = {}

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(Block("paragraph", lines=tuple(paragraph)))
            paragraph.clear()

    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        heading = _HEADING_RE.match(stripped)
        separator = _SEPARATOR_RE.match(stripped)
        unordered = _UNORDERED_LIST_MATCH_RE.match(line) if not separator else None
        ordered = _ORDERED_LIST_RE.match(line)
        if not stripped:
            flush_paragraph()
            blocks.append(Block("spacer"))
        elif _looks_like_markdown_table_start(lines, index):
            flush_paragraph()
            start = index
            index += 2
            while (
                index < len(lines)
                and lines[index].strip()
                and "|" in lines[index]
                and not _TABLE_BLOCK_TERMINATOR_RE.match(lines[index])
            ):
                index += 1
            blocks.append(Block("table", lines=tuple(lines[start:index])))
            continue
        elif stripped.startswith(">"):
            flush_paragraph()
            quote: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote.append(re.sub(r"^>\s?", "", lines[index].strip()))
                index += 1
            blocks.append(Block("quote", text="\n".join(quote).strip()))
            continue
        elif heading:
            flush_paragraph()
            blocks.append(
                Block("heading", text=heading[2].strip(), level=len(heading[1]))
            )
        elif ordered or unordered:
            flush_paragraph()
            match = ordered or unordered
            assert match is not None
            text = match[4].strip() if ordered else match[2].strip()
            task_prefix, text = _task_list_prefix(text)
            bullet = f"{match[2]}{match[3]} " if ordered else "• "
            blocks.append(
                Block(
                    "list",
                    text=text,
                    level=len(match[1]),
                    bullet=task_prefix or bullet,
                    ordered=bool(ordered),
                    is_task=bool(task_prefix),
                )
            )
        elif separator:
            flush_paragraph()
            blocks.append(Block("separator"))
        elif is_char_emoji(stripped[0]):
            flush_paragraph()
            multiline = _collect_multiline_inline_block(lines, index, closing_cache)
            if multiline:
                text, index = multiline
                blocks.append(Block("marker", text=text))
                continue
            blocks.append(Block("marker", text=stripped))
        elif indent := re.match(r"^(\s+)(.+)", line):
            flush_paragraph()
            blocks.append(Block("indent", text=indent[2].strip(), level=len(indent[1])))
        else:
            multiline = _collect_multiline_inline_block(lines, index, closing_cache)
            if multiline:
                text, index = multiline
                paragraph.append(text)
                continue
            paragraph.append(stripped)
        index += 1
    flush_paragraph()
    return blocks


def parse_blocks(text: str) -> list[Block]:
    blocks: list[Block] = []
    for segment in iter_fenced_segments(text):
        if not segment.text.strip():
            continue
        if not segment.is_code:
            blocks.extend(_parse_lines(_normalize_lines(segment.text)))
            continue
        fence = parse_code_fence(segment.text)
        blocks.append(
            Block("code", text=fence.body.rstrip("\n"), language=fence.language)
        )
    return blocks
