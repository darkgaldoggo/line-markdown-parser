"""Pure Markdown-to-Flex component rendering without I/O or logging."""

import re
import urllib.parse
from bisect import bisect_left, bisect_right
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

LINE_ACTION_URI_MAX_LENGTH = 1000
BODY_TEXT_COLOR = "#696969"
STRONG_TEXT_COLOR = "#555555"
LINK_TEXT_COLOR = "#0066FF"
INLINE_CODE_COLOR = "#C46A00"
MUTED_TEXT_COLOR = "#888888"
CODE_BLOCK_BACKGROUND = "#F5F5F5"
CODE_BLOCK_INDENT_SPACE = "\xa0"


def is_char_emoji(char):
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


_ESCAPABLE_INLINE_CHARS = set("\\`*_{}[]()#+-.!<>~")
_INLINE_DELIMITERS: tuple[tuple[str, dict[str, bool]], ...] = (
    ("***", {"bold": True, "italic": True}),
    ("___", {"bold": True, "italic": True}),
    ("**", {"bold": True}),
    ("__", {"bold": True}),
    ("~~", {"strike": True}),
    ("*", {"italic": True}),
    ("_", {"italic": True}),
)
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
    kind: str
    text: str
    url: str
    label: str | None = None


def _iter_links(text: str) -> Iterator[_InlineLink]:
    """ラベルの括弧を一度だけ走査し、コードとエスケープを除外してリンクを返す。"""
    code_ends: dict[int, int] = {}
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
    fragments = []
    protected = []
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
            pattern = f"<{tag}\\b[^>]*>([\\s\\S]*?)</{tag}>"
            source = re.sub(
                pattern,
                lambda match, prefix=opener, suffix=closer: (
                    f"{prefix}{match.group(1)}{suffix}"
                ),
                source,
                flags=re.IGNORECASE,
            )
        return source

    return _transform_outside_inline_code(text, replace_tags, normalize_html_code=True)


def _is_escaped(text: str, index: int) -> bool:
    """index位置の文字が、直前の奇数個のバックスラッシュでエスケープされているか判定する。"""
    slash_count = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        slash_count += 1
        cursor -= 1
    return slash_count % 2 == 1


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


def _span_for_text(text: str, style: dict[str, bool]) -> dict | None:
    if text == "":
        return None
    span = {"type": "span", "text": text, "color": BODY_TEXT_COLOR, "size": "sm"}
    if style.get("bold"):
        span["weight"] = "bold"
        span["color"] = STRONG_TEXT_COLOR
    if style.get("italic"):
        span["style"] = "italic"
    if style.get("strike"):
        span["decoration"] = "line-through"
    if style.get("code"):
        span["color"] = INLINE_CODE_COLOR
    return span


def _merge_adjacent_spans(spans: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for span in spans:
        if not span or not span.get("text"):
            continue
        if merged:
            previous = merged[-1]
            previous_key = {k: v for k, v in previous.items() if k != "text"}
            current_key = {k: v for k, v in span.items() if k != "text"}
            if previous_key == current_key:
                previous["text"] += span["text"]
                continue
        merged.append(span)
    return merged


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


def _inline_link_ranges(
    text: str, code_ranges: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """リンクの範囲を返す。URL内の記号を外側の強調と混同しないために使う。"""
    ranges: list[tuple[int, int]] = []
    prefix = ""
    previous_end = 0
    for link in _iter_links(text):
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
        ranges.append((start, end))
        prefix += "x"
        previous_end = end
    return ranges


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


def _parse_inline_styled_spans(
    text: str, style: dict[str, bool], *, parse_links: bool = False, _depth: int = 0
) -> list[dict]:
    """インラインのMarkdownを解析し、リンクの前後にも同じ強調を適用する。

    インラインコードを優先して処理し、その範囲を保持して強調の開始・終了記号を対応付ける。
    これにより **`code`** のような記法を扱う。コード内のMarkdownは装飾として解釈しない。
    parse_linksが有効な場合、_linkを内部トークンとして使う。
    アクション行への分離は強調範囲の確定後に行う。
    """
    if _depth >= 64:
        span = _span_for_text(text, style)
        return [span] if span else []
    spans: list[dict] = []
    buffer: list[str] = []
    index = 0
    code_spans = _iter_inline_code_spans(text)
    code_span_by_start = {
        start: (end, code_text) for start, end, code_text in code_spans
    }
    code_ranges = [(start, end) for start, end, _ in code_spans]
    link_ranges = _inline_link_ranges(text, code_ranges) if parse_links else []
    link_end_by_start = dict(link_ranges)
    protected_ranges = code_ranges + link_ranges
    closing_cache: dict[str, list[int]] = {}

    def flush_text() -> None:
        if buffer:
            span = _span_for_text("".join(buffer), style)
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
            code_style = dict(style)
            code_style["code"] = True
            span = _span_for_text(code_text, code_style)
            if span:
                spans.append(span)
            index = end
            continue
        if index in link_end_by_start:
            end = link_end_by_start[index]
            flush_text()
            spans.append(
                {"type": "_link", "text": text[index:end], "style": dict(style)}
            )
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
            child_style = dict(style)
            child_style.update(style_update)
            spans.extend(
                _parse_inline_styled_spans(
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


def _parse_inline_to_spans(
    text: str, base_style: dict[str, bool] | None = None, *, normalize_html: bool = True
) -> list[dict]:
    if text == "":
        return []
    style = dict(base_style or {})
    source = _normalize_inline_html_lite(text) if normalize_html else text
    spans = _parse_inline_styled_spans(source, style)
    return _merge_adjacent_spans(spans)


def process_text_segment_to_spans(
    text_segment, base_style: dict[str, bool] | None = None
):
    """テキストを、Markdownのインライン装飾を反映したFlex spanに変換する。"""
    return _parse_inline_to_spans(text_segment, base_style)


def process_line_to_flex_components(line):
    """強調範囲を確定してから、通常テキストと URI アクション行へ分離する。"""
    tokens = _parse_inline_styled_spans(
        _normalize_inline_html_lite(line), {}, parse_links=True
    )
    components: list[dict] = []
    pending_spans: list[dict] = []
    after_link = False

    def flush_text(*, before_link: bool) -> None:
        spans = _merge_adjacent_spans(pending_spans)
        pending_spans.clear()
        if after_link:
            while spans:
                spans[0]["text"] = spans[0]["text"].lstrip(" \t")
                if spans[0]["text"]:
                    break
                spans.pop(0)
        if before_link:
            while spans:
                spans[-1]["text"] = spans[-1]["text"].rstrip(" \t")
                if spans[-1]["text"]:
                    break
                spans.pop()
        visible = "".join(span["text"] for span in spans)
        if visible.strip() and (
            not (before_link or after_link)
            or visible.strip("。、,・/／|｜ \t\n")
            or any(span.get("color") == INLINE_CODE_COLOR for span in spans)
        ):
            components.append(
                {
                    "type": "text",
                    "contents": spans,
                    "wrap": True,
                    "margin": "none",
                    "size": "sm",
                }
            )

    for token in tokens:
        if token["type"] == "_link":
            flush_text(before_link=True)
            components.extend(
                _process_line_to_flex_components_without_code_spans(
                    token["text"], token["style"]
                )
            )
            after_link = True
        else:
            pending_spans.append(token)
    flush_text(before_link=False)
    return components


def _clone_text_component_with_spans(
    component: dict[str, Any], spans: list[dict]
) -> dict[str, Any] | None:
    merged_spans = _merge_adjacent_spans(spans)
    if not merged_spans:
        return None
    cloned = {key: value for key, value in component.items() if key != "contents"}
    cloned["contents"] = merged_spans
    return cloned


def _split_text_component_on_newlines(
    component: dict[str, Any],
) -> list[dict[str, Any]]:
    if component.get("type") != "text" or not isinstance(
        component.get("contents"), list
    ):
        return [component]
    split_components: list[dict[str, Any]] = []
    current_spans: list[dict] = []
    saw_newline = False
    for span in component.get("contents", []):
        span_text = span.get("text")
        if not isinstance(span_text, str) or "\n" not in span_text:
            current_spans.append(span)
            continue
        saw_newline = True
        parts = span_text.split("\n")
        for part_index, part in enumerate(parts):
            if part:
                split_span = dict(span)
                split_span["text"] = part
                current_spans.append(split_span)
            if part_index < len(parts) - 1:
                split_component = _clone_text_component_with_spans(
                    component, current_spans
                )
                if split_component:
                    split_components.append(split_component)
                current_spans = []
    if not saw_newline:
        return [component]
    split_component = _clone_text_component_with_spans(component, current_spans)
    if split_component:
        split_components.append(split_component)
    return split_components


def _normalize_link_adjacent_text_segment(
    segment: str, *, trim_start: bool, trim_end: bool
) -> str:
    """Drop separator spaces that only existed around an inline link in Markdown."""
    if trim_start:
        segment = segment.lstrip(" \t")
    if trim_end:
        segment = segment.rstrip(" \t")
    return segment


def _process_line_to_flex_components_without_code_spans(
    line, base_style: dict[str, bool] | None = None
):
    """インラインコードの外側だけをリンク化し、通常テキストは装飾つきのFlex spanに変換する。"""
    line_components = []
    inline_code_ranges = _inline_code_span_ranges(line)
    last_index = 0
    for link in _iter_links(line):
        match_start, match_end = link.start, link.end
        if _position_inside_ranges(match_start, inline_code_ranges):
            continue
        if match_start > last_index:
            segment = _normalize_link_adjacent_text_segment(
                line[last_index:match_start], trim_start=last_index > 0, trim_end=True
            )
            if segment.strip("。、,・/／|｜ "):
                spans = process_text_segment_to_spans(segment, base_style)
                if spans:
                    line_components.append(
                        {
                            "type": "text",
                            "contents": spans,
                            "wrap": True,
                            "margin": "none",
                            "size": "sm",
                        }
                    )
        action_uri = None
        markdown_text_raw = None
        link_consumed_end = match_end
        if link.kind == "markdown":
            markdown_text_raw = link.label
            action_uri = link.url
            if action_uri and action_uri.startswith("<") and action_uri.endswith(">"):
                action_uri = action_uri[1:-1].strip()
            if not action_uri:
                last_index = match_end
                continue
        elif link.kind == "autolink":
            markdown_text_raw = None
            action_uri = link.url
        elif link.kind == "plain":
            markdown_text_raw = None
            original_plain_url = link.url
            action_uri = _strip_plain_url_punctuation(original_plain_url)
            if not action_uri:
                last_index = match_end
                continue
            link_consumed_end = match_start + len(action_uri)
        else:
            last_index = match_end
            continue
        link_component = None
        if action_uri:
            action_uri = action_uri.strip()
            if not action_uri.startswith(("http://", "https://")):
                # Unsupported destinations never become actions. Preserve the
                # useful label without exposing a local or custom-scheme URI.
                segment = markdown_text_raw or link.text
                spans = process_text_segment_to_spans(segment, base_style)
                if spans:
                    line_components.append(
                        {
                            "type": "text",
                            "contents": spans,
                            "wrap": True,
                            "margin": "none",
                            "size": "sm",
                        }
                    )
                last_index = match_end
                continue
            try:
                parsed_uri = urllib.parse.urlsplit(action_uri)
                if not parsed_uri.scheme or not parsed_uri.hostname:
                    raise ValueError("Invalid URL structure (missing scheme or netloc)")
                valid_hostname_pattern = "^[a-zA-Z0-9\\.\\-:]+$"
                if not re.fullmatch(valid_hostname_pattern, parsed_uri.netloc):
                    raise ValueError(
                        f"Invalid hostname characters in netloc: {parsed_uri.netloc}"
                    )
                # Accessing port validates both its numeric form and range.
                _ = parsed_uri.port
                if re.search(r"%(?![0-9A-Fa-f]{2})", action_uri):
                    raise ValueError("Invalid percent escape")
                # RFC 3986 pchar, plus the separators allowed in each component.
                path_safe = "/:@!$&'()*+,;=%"
                sanitized_path = urllib.parse.quote(parsed_uri.path, safe=path_safe)
                sanitized_query = urllib.parse.quote(
                    parsed_uri.query, safe=path_safe + "?"
                )
                sanitized_fragment = urllib.parse.quote(
                    parsed_uri.fragment, safe=path_safe + "?"
                )
                sanitized_uri = (
                    f"{parsed_uri.scheme}://{parsed_uri.netloc}{sanitized_path}"
                )
                if "?" in action_uri.partition("#")[0]:
                    sanitized_uri += f"?{sanitized_query}"
                if "#" in action_uri:
                    sanitized_uri += f"#{sanitized_fragment}"
                action_uri = sanitized_uri
            except ValueError:
                segment = link.text
                spans = process_text_segment_to_spans(segment, base_style)
                if spans:
                    line_components.append(
                        {
                            "type": "text",
                            "contents": spans,
                            "wrap": True,
                            "margin": "none",
                            "size": "sm",
                        }
                    )
                last_index = match_end
                continue
            if len(action_uri) > LINE_ACTION_URI_MAX_LENGTH:
                segment = link.text
                spans = process_text_segment_to_spans(segment, base_style)
                if spans:
                    line_components.append(
                        {
                            "type": "text",
                            "contents": spans,
                            "wrap": True,
                            "margin": "none",
                            "size": "sm",
                        }
                    )
                last_index = match_end
                continue
            is_markdown_link = link.kind == "markdown"
            is_autolink = link.kind == "autolink"
            display_text_source = ""
            if is_markdown_link:
                display_text_source = (
                    markdown_text_raw.strip()
                    if markdown_text_raw and markdown_text_raw.strip()
                    else action_uri
                )
            elif is_autolink:
                display_text_source = action_uri
            else:
                display_text_source = action_uri
            display_spans = (
                process_text_segment_to_spans(display_text_source, base_style)
                if is_markdown_link and markdown_text_raw and markdown_text_raw.strip()
                else [_span_for_text(action_uri, base_style or {})]
            )
            total_text_length = sum(len(span.get("text", "")) for span in display_spans)
            if total_text_length > 40:
                remaining = 37
                shortened = []
                for span in display_spans:
                    if remaining <= 0:
                        break
                    clipped = dict(span)
                    clipped["text"] = span["text"][:remaining]
                    remaining -= len(clipped["text"])
                    shortened.append(clipped)
                shortened[-1]["text"] += "..."
                display_spans = shortened
            link_icon_span = {
                "type": "span",
                "text": "🔗 ",
                "color": LINK_TEXT_COLOR,
                "size": "sm",
                "decoration": "underline",
            }
            final_spans = [link_icon_span]
            for span in display_spans:
                span["color"] = LINK_TEXT_COLOR
                span["decoration"] = "underline"
                final_spans.append(span)
            link_component = {
                "type": "text",
                "contents": final_spans,
                "wrap": True,
                "margin": "sm",
                "action": {"type": "uri", "uri": action_uri},
            }
        if link_component:
            line_components.append(link_component)
        last_index = link_consumed_end
    if last_index < len(line):
        segment = _normalize_link_adjacent_text_segment(
            line[last_index:], trim_start=last_index > 0, trim_end=False
        )
        if segment and segment.strip("。、,・/／|｜ "):
            spans = process_text_segment_to_spans(segment, base_style)
            if spans:
                line_components.append(
                    {
                        "type": "text",
                        "contents": spans,
                        "wrap": True,
                        "margin": "none",
                        "size": "sm",
                    }
                )
    if not line_components and last_index == 0 and line.strip():
        if line.strip().strip("。、,・/／|｜ "):
            spans = process_text_segment_to_spans(line.strip(), base_style)
            if spans:
                line_components.append(
                    {
                        "type": "text",
                        "contents": spans,
                        "wrap": True,
                        "margin": "none",
                        "size": "sm",
                    }
                )
    return line_components


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
    if re.match("^(\\s*)(\\d+)([.)])\\s+(.*)", line):
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
            start_line, opener_index + len(delimiter), delimiter
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
            elif _find_closing_inline_delimiter(line.strip(), 0, delimiter) is not None:
                next_closing_line = index
        closing_line_cache[delimiter] = closing_lines
    closing_line = closing_line_cache[delimiter][start_index]
    if closing_line is None:
        return None
    joined = "\n".join(line.strip() for line in lines[start_index : closing_line + 1])
    return (joined, closing_line + 1)


def process_text_block_to_flex_components(text_block: str) -> list[dict[str, Any]]:
    """複数行を含むテキストを Flex コンポーネントのフラットなリストへ変換する。"""
    components: list[dict[str, Any]] = []
    normalized_lines = [
        raw_line.strip() for raw_line in text_block.splitlines() if raw_line.strip()
    ]
    if not normalized_lines:
        return components
    line_components = process_line_to_flex_components("\n".join(normalized_lines))
    for component in line_components:
        components.extend(_split_text_component_on_newlines(component))
    return components


def _paragraph_box(
    components: list[dict[str, Any]], *, margin: str = "md"
) -> dict[str, Any] | None:
    non_empty = [component for component in components if component]
    if not non_empty:
        return None
    return {
        "type": "box",
        "layout": "vertical",
        "spacing": "xs",
        "contents": non_empty,
        "margin": margin,
    }


def _spacer_component() -> dict[str, Any]:
    return {
        "type": "text",
        "text": " ",
        "size": "xxs",
        "margin": "none",
        "color": "#FFFFFF",
    }


def _preserve_code_block_indentation(code: str) -> str:
    """Keep leading indentation visible in LINE clients that collapse ASCII spaces."""
    preserved_lines: list[str] = []
    for line in code.split("\n"):
        expanded_line = line.expandtabs(4)
        stripped_line = expanded_line.lstrip(" ")
        leading_space_count = len(expanded_line) - len(stripped_line)
        preserved_lines.append(
            CODE_BLOCK_INDENT_SPACE * leading_space_count + stripped_line
        )
    return "\n".join(preserved_lines)


def _render_code_block(raw_code: str) -> dict[str, Any] | None:
    code_content = raw_code[3:-3]
    language = ""
    body = code_content
    if "\n" in code_content:
        first_line, rest = code_content.split("\n", 1)
        candidate_language = first_line.strip()
        if not candidate_language:
            body = rest.rstrip("\n")
        elif re.fullmatch("[A-Za-z0-9_+#.\\-]+", candidate_language):
            language = candidate_language
            body = rest.rstrip("\n")
    if not language and (not body.strip()):
        return None
    block_contents: list[dict[str, Any]] = []
    if language:
        block_contents.append(
            {
                "type": "text",
                "text": language,
                "wrap": True,
                "color": MUTED_TEXT_COLOR,
                "size": "xxs",
                "weight": "bold",
                "margin": "none",
            }
        )
    if body.strip():
        block_contents.append(
            {
                "type": "text",
                "text": _preserve_code_block_indentation(body),
                "wrap": True,
                "color": "#333333",
                "size": "sm",
                "margin": "xs" if language else "none",
            }
        )
    return {
        "type": "box",
        "layout": "vertical",
        "contents": block_contents,
        "backgroundColor": CODE_BLOCK_BACKGROUND,
        "paddingAll": "10px",
        "cornerRadius": "md",
        "margin": "md",
    }


def _render_heading(heading_text: str, level: int) -> dict[str, Any] | None:
    spans = process_text_segment_to_spans(heading_text, {"bold": True})
    if not spans:
        return None
    size = "xxl" if level == 1 else "xl" if level == 2 else "lg"
    for span in spans:
        span["weight"] = "bold"
        span["size"] = size
        if not span.get("code"):
            span["color"] = "#444444"
    return {
        "type": "text",
        "contents": spans,
        "wrap": True,
        "weight": "bold",
        "size": size,
        "margin": "xs",
    }


def _render_separator() -> dict[str, Any]:
    return {
        "type": "text",
        "text": "───────────────────────",
        "wrap": True,
        "color": "#CCCCCC",
        "size": "sm",
        "align": "center",
        "margin": "none",
    }


def _render_quote_block(quote_text: str) -> dict[str, Any] | None:
    inner_components = process_text_block_to_flex_components(quote_text)
    if not inner_components:
        return None
    return {
        "type": "box",
        "layout": "horizontal",
        "contents": [
            {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": " ", "size": "xxs", "color": "#FFB6C1"}
                ],
                "width": "4px",
                "backgroundColor": "#FFB6C1",
                "cornerRadius": "2px",
            },
            {
                "type": "box",
                "layout": "vertical",
                "contents": inner_components,
                "spacing": "xs",
                "paddingStart": "10px",
                "flex": 1,
            },
        ],
        "backgroundColor": "#FFF7FA",
        "paddingAll": "8px",
        "cornerRadius": "md",
        "margin": "md",
    }


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


def _render_table_block(table_lines: list[str]) -> dict[str, Any] | None:
    table_text = "\n".join(line.strip() for line in table_lines if line.strip())
    if not table_text:
        return None
    return {
        "type": "box",
        "layout": "vertical",
        "contents": [
            {
                "type": "text",
                "text": "table",
                "wrap": True,
                "color": MUTED_TEXT_COLOR,
                "size": "xxs",
                "weight": "bold",
                "margin": "none",
            },
            {
                "type": "text",
                "text": table_text,
                "wrap": True,
                "color": "#333333",
                "size": "xs",
                "margin": "xs",
            },
        ],
        "backgroundColor": CODE_BLOCK_BACKGROUND,
        "paddingAll": "10px",
        "cornerRadius": "md",
        "margin": "md",
    }


def _task_list_prefix(raw_list_item_text: str) -> tuple[str, str]:
    task_match = re.match(
        "^\\[(?P<mark>[ xX])\\]\\s+(?P<text>[\\s\\S]+)$", raw_list_item_text
    )
    if not task_match:
        return ("", raw_list_item_text)
    marker = "☑ " if task_match.group("mark").lower() == "x" else "☐ "
    return (marker, task_match.group("text").strip())


def _render_list_item(
    bullet_text: str,
    raw_list_item_text: str,
    indent_level: int,
    *,
    ordered: bool = False,
) -> dict[str, Any] | None:
    task_prefix, item_text = _task_list_prefix(raw_list_item_text.strip())
    display_bullet = task_prefix or bullet_text
    if indent_level == 0:
        padding_start = "10px"
        marker = display_bullet
    elif indent_level <= 2:
        padding_start = "30px"
        marker = display_bullet if ordered or task_prefix else "◦ "
    else:
        padding_start = "50px"
        marker = display_bullet if ordered or task_prefix else "▪ "
    item_components = process_text_block_to_flex_components(item_text)
    if not item_components:
        return None
    return {
        "type": "box",
        "layout": "horizontal",
        "contents": [
            {
                "type": "text",
                "text": marker,
                "wrap": False,
                "flex": 0,
                "margin": "none",
                "gravity": "top",
                "size": "sm",
                "color": BODY_TEXT_COLOR,
            },
            {
                "type": "box",
                "layout": "vertical",
                "contents": item_components,
                "flex": 1,
                "margin": "sm",
                "spacing": "xs",
            },
        ],
        "margin": "xs",
        "paddingStart": padding_start,
        "alignItems": "flex-start",
    }


def parse_text_with_links(text):
    """テキストを解析し、コードブロック、見出し、リスト、リンク、太字をFlex Messageのコンテンツに変換する。"""
    code_delimiter_pattern = "(```[\\s\\S]*?```)"
    segments = re.split(code_delimiter_pattern, text)
    contents = []
    for segment in segments:
        if segment is None or not segment.strip():
            continue
        is_code_block = re.fullmatch(code_delimiter_pattern, segment)
        if is_code_block:
            component_to_add = _render_code_block(segment)
            if component_to_add:
                contents.append(component_to_add)
        else:
            normalized_segment = "\n".join(
                _transform_outside_inline_code(
                    line,
                    lambda source: re.sub(
                        "<br\\s*/?>", "\n", source, flags=re.IGNORECASE
                    ),
                )
                for line in segment.split("\n")
            )
            lines = normalized_segment.strip().split("\n")
            normalized_lines = []
            prev_was_list = False
            for raw_line in lines:
                stripped = raw_line.strip()
                heading_match_tmp = re.match("^(#{1,6})\\s+(.*)", stripped)
                separator_line_match_tmp = re.match(
                    "^(\\s*)(?:[-‐]{3,}|\\*{3,}|_{3,})\\s*$", stripped
                )
                list_match_tmp = (
                    _UNORDERED_LIST_MATCH_RE.match(raw_line)
                    if not separator_line_match_tmp
                    else None
                )
                numbered_list_match_tmp = re.match(
                    "^(\\s*)(\\d+)([.)])\\s+(.*)", raw_line
                )
                is_list_line = bool(list_match_tmp or numbered_list_match_tmp)
                should_merge_with_prev_list = (
                    not is_list_line
                    and prev_was_list
                    and stripped
                    and raw_line[:1].isspace()
                    and (not heading_match_tmp)
                    and (not separator_line_match_tmp)
                )
                if should_merge_with_prev_list and normalized_lines:
                    continuation = raw_line.lstrip()
                    prev_line = normalized_lines[-1]
                    if _ends_with_markdown_hard_break(
                        prev_line
                    ) or _looks_like_list_item_title_line(prev_line):
                        prev_line = _strip_markdown_hard_break(prev_line).rstrip()
                        normalized_lines[-1] = prev_line + "\n" + continuation
                    else:
                        normalized_lines[-1] = prev_line.rstrip() + " " + continuation
                    prev_was_list = True
                    continue
                normalized_lines.append(raw_line)
                prev_was_list = is_list_line
            lines = normalized_lines
            closing_line_cache: dict[str, list[int | None]] = {}
            current_paragraph_components = []

            def add_paragraph_if_exists(components=current_paragraph_components):
                paragraph_box = _paragraph_box(components)
                if paragraph_box:
                    contents.append(paragraph_box)
                components.clear()

            line_index = 0
            while line_index < len(lines):
                line = lines[line_index]
                line_strip = line.strip()
                if not line_strip:
                    add_paragraph_if_exists()
                    contents.append(_spacer_component())
                    line_index += 1
                    continue
                heading_match = re.match("^(#{1,6})\\s+(.*)", line_strip)
                separator_line_match = re.match(
                    "^(\\s*)(?:[-‐]{3,}|\\*{3,}|_{3,})\\s*$", line_strip
                )
                list_match = (
                    _UNORDERED_LIST_MATCH_RE.match(line)
                    if not separator_line_match
                    else None
                )
                numbered_list_match = re.match(
                    "^(\\s*)(\\d+)([.)])\\s+([\\s\\S]+)", line
                )
                if _looks_like_markdown_table_start(lines, line_index):
                    add_paragraph_if_exists()
                    table_lines = [lines[line_index], lines[line_index + 1]]
                    line_index += 2
                    while line_index < len(lines):
                        candidate_line = lines[line_index]
                        if not candidate_line.strip() or "|" not in candidate_line:
                            break
                        if _TABLE_BLOCK_TERMINATOR_RE.match(candidate_line):
                            break
                        table_lines.append(candidate_line)
                        line_index += 1
                    table_component = _render_table_block(table_lines)
                    if table_component:
                        contents.append(table_component)
                    continue
                if line_strip.startswith(">"):
                    add_paragraph_if_exists()
                    quote_lines: list[str] = []
                    while line_index < len(lines):
                        quote_line = lines[line_index].strip()
                        if not quote_line.startswith(">"):
                            break
                        quote_lines.append(re.sub("^>\\s?", "", quote_line))
                        line_index += 1
                    quote_component = _render_quote_block(
                        "\n".join(quote_lines).strip()
                    )
                    if quote_component:
                        contents.append(quote_component)
                    continue
                if heading_match:
                    add_paragraph_if_exists()
                    level = len(heading_match.group(1))
                    heading_text = heading_match.group(2).strip()
                    component_to_add = _render_heading(heading_text, level)
                    if component_to_add:
                        contents.append(component_to_add)
                    line_index += 1
                    continue
                elif numbered_list_match:
                    add_paragraph_if_exists()
                    indent_spaces = numbered_list_match.group(1)
                    indent_level = len(indent_spaces)
                    list_number = numbered_list_match.group(2)
                    list_delimiter = numbered_list_match.group(3)
                    raw_list_item_text = numbered_list_match.group(4).strip()
                    component_to_add = _render_list_item(
                        f"{list_number}{list_delimiter} ",
                        raw_list_item_text,
                        indent_level,
                        ordered=True,
                    )
                    if component_to_add:
                        contents.append(component_to_add)
                    line_index += 1
                    continue
                elif list_match:
                    add_paragraph_if_exists()
                    indent_spaces = list_match.group(1)
                    indent_level = len(indent_spaces)
                    raw_list_item_text = list_match.group(2).strip()
                    component_to_add = _render_list_item(
                        "• ", raw_list_item_text, indent_level
                    )
                    if component_to_add:
                        contents.append(component_to_add)
                    line_index += 1
                    continue
                elif separator_line_match:
                    add_paragraph_if_exists()
                    contents.append(_render_separator())
                    line_index += 1
                    continue
                is_marker_line = False
                if (
                    not list_match
                    and (not numbered_list_match)
                    and (not heading_match)
                    and line_strip
                ):
                    if is_char_emoji(line_strip[0]):
                        is_marker_line = True
                if is_marker_line:
                    add_paragraph_if_exists()
                    marker_multiline_block = _collect_multiline_inline_block(
                        lines, line_index, closing_line_cache
                    )
                    if marker_multiline_block:
                        block_text, next_line_index = marker_multiline_block
                        marker_line_components = process_text_block_to_flex_components(
                            block_text
                        )
                        line_index = next_line_index
                    else:
                        marker_line_components = process_line_to_flex_components(
                            line_strip
                        )
                        line_index += 1
                    if marker_line_components:
                        component_to_add = {
                            "type": "box",
                            "layout": "vertical",
                            "contents": marker_line_components,
                            "margin": "md",
                            "spacing": "xs",
                        }
                        contents.append(component_to_add)
                    continue
                else:
                    space_indent_match = re.match("^(\\s+)(.+)", line)
                    if (
                        space_indent_match
                        and (not list_match)
                        and (not numbered_list_match)
                    ):
                        add_paragraph_if_exists()
                        indent_spaces = space_indent_match.group(1)
                        indent_level = len(indent_spaces)
                        indented_text = space_indent_match.group(2).strip()
                        if indent_level <= 2:
                            padding_start = "20px"
                        elif indent_level <= 4:
                            padding_start = "40px"
                        else:
                            padding_start = "60px"
                        if indented_text:
                            indented_flex_components_list = (
                                process_line_to_flex_components(indented_text)
                            )
                            if indented_flex_components_list:
                                component_to_add = {
                                    "type": "box",
                                    "layout": "vertical",
                                    "contents": indented_flex_components_list,
                                    "margin": "xs",
                                    "paddingStart": padding_start,
                                }
                                contents.append(component_to_add)
                        line_index += 1
                        continue
                    multiline_inline_block = _collect_multiline_inline_block(
                        lines, line_index, closing_line_cache
                    )
                    if multiline_inline_block:
                        block_text, next_line_index = multiline_inline_block
                        line_flex_components_list = (
                            process_text_block_to_flex_components(block_text)
                        )
                        if line_flex_components_list:
                            current_paragraph_components.extend(
                                comp for comp in line_flex_components_list if comp
                            )
                        line_index = next_line_index
                        continue
                    line_flex_components_list = process_line_to_flex_components(
                        line_strip
                    )
                    if line_flex_components_list:
                        current_paragraph_components.extend(
                            comp for comp in line_flex_components_list if comp
                        )
                    line_index += 1
            add_paragraph_if_exists()
    if not contents and text.strip():
        contents.extend(process_line_to_flex_components(text.strip()))
    return contents


def _is_separator_text_component(component: dict) -> bool:
    """Flexのテキストコンポーネントが区切り線かどうかを判定する。"""
    if not isinstance(component, dict):
        return False
    if component.get("type") != "text":
        return False
    text_value = component.get("text", "")
    if not isinstance(text_value, str):
        return False
    return re.fullmatch("\\s*[-‐─]{3,}\\s*", text_value) is not None


def build_flex_contents(text_message: str) -> list[dict]:
    """Render Markdown as Flex body components, without sending or logging it."""
    if not isinstance(text_message, str):
        raise TypeError("text_message must be a string")
    contents = parse_text_with_links(text_message)
    while contents and _is_separator_text_component(contents[0]):
        contents.pop(0)
    while contents and _is_separator_text_component(contents[-1]):
        contents.pop()
    return contents
