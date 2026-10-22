"""Render shared inline tokens as text components and URI actions."""

from __future__ import annotations

from ._flex import FlexSpan, FlexText
from ._inline import InlineStyle, LinkToken, TextToken, parse_inline
from ._uri import resolve_link

BODY_TEXT_COLOR = "#696969"
STRONG_TEXT_COLOR = "#555555"
LINK_TEXT_COLOR = "#0066FF"
INLINE_CODE_COLOR = "#C46A00"


def _span_for_token(token: TextToken, heading_level: int = 0) -> FlexSpan:
    style = token.style
    span: FlexSpan = {
        "type": "span",
        "text": token.text,
        "color": BODY_TEXT_COLOR,
        "size": "sm",
    }
    if style.get("bold"):
        span["weight"] = "bold"
        span["color"] = STRONG_TEXT_COLOR
    if style.get("italic"):
        span["style"] = "italic"
    if style.get("strike"):
        span["decoration"] = "line-through"
    if style.get("code"):
        span["color"] = INLINE_CODE_COLOR
    if heading_level:
        span.update(
            {"weight": "bold", "size": _heading_size(heading_level), "color": "#444444"}
        )
    return span


def _heading_size(level: int) -> str:
    return "xxl" if level == 1 else "xl" if level == 2 else "lg"


def _merge_adjacent_spans(spans: list[FlexSpan]) -> list[FlexSpan]:
    merged: list[FlexSpan] = []
    for span in spans:
        if not span["text"]:
            continue
        if merged and {k: v for k, v in merged[-1].items() if k != "text"} == {
            k: v for k, v in span.items() if k != "text"
        }:
            merged[-1]["text"] += span["text"]
        else:
            merged.append(span.copy())
    return merged


def _label_spans(text: str, style: InlineStyle, heading_level: int) -> list[FlexSpan]:
    return _merge_adjacent_spans(
        [
            _span_for_token(token, heading_level)
            for token in parse_inline(text, style, links=False)
            if isinstance(token, TextToken)
        ]
    )


def _text_component(spans: list[FlexSpan], heading_level: int = 0) -> FlexText:
    component: FlexText = {
        "type": "text",
        "contents": spans,
        "wrap": True,
        "margin": "none",
        "size": "sm",
    }
    if heading_level:
        component.update(
            {"weight": "bold", "size": _heading_size(heading_level), "margin": "xs"}
        )
    return component


def _render_link(token: LinkToken, heading_level: int) -> FlexText | None:
    target = resolve_link(token.link)
    spans = (
        _label_spans(target.text, token.style, heading_level)
        if target.parse_label
        else [_span_for_token(TextToken(target.text, token.style), heading_level)]
    )
    if not spans:
        return None
    if target.uri is None:
        return _text_component(spans, heading_level)
    if sum(len(span["text"]) for span in spans) > 40:
        remaining = 37
        shortened: list[FlexSpan] = []
        for span in spans:
            if remaining <= 0:
                break
            clipped = span.copy()
            clipped["text"] = span["text"][:remaining]
            remaining -= len(clipped["text"])
            shortened.append(clipped)
        shortened[-1]["text"] += "..."
        spans = shortened
    icon: FlexSpan = {"type": "span", "text": "🔗 ", "size": "sm"}
    if heading_level:
        icon.update({"size": _heading_size(heading_level), "weight": "bold"})
    spans.insert(0, icon)
    for span in spans:
        span.update({"color": LINK_TEXT_COLOR, "decoration": "underline"})
    component: FlexText = {
        "type": "text",
        "contents": spans,
        "wrap": True,
        "margin": "sm",
        "action": {"type": "uri", "uri": target.uri},
    }
    if heading_level:
        component.update({"size": _heading_size(heading_level), "weight": "bold"})
    return component


def process_line_to_flex_components(
    line: str, *, heading_level: int = 0
) -> list[FlexText]:
    """Resolve syntax once, then lay out text and individual clickable links."""
    style: InlineStyle = {"bold": True} if heading_level else {}
    tokens = parse_inline(line, style)
    components: list[FlexText] = []
    pending: list[TextToken] = []
    after_link = False

    def flush_text(*, before_link: bool) -> None:
        has_code = any(token.style.get("code") for token in pending)
        spans = _merge_adjacent_spans(
            [_span_for_token(token, heading_level) for token in pending]
        )
        pending.clear()
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
            or has_code
        ):
            components.append(_text_component(spans, heading_level))

    for token in tokens:
        if isinstance(token, LinkToken):
            flush_text(before_link=True)
            component = _render_link(token, heading_level)
            if component:
                components.append(component)
            after_link = True
        else:
            pending.append(token)
    flush_text(before_link=False)
    return components


def _split_text_component_on_newlines(component: FlexText) -> list[FlexText]:
    split_components: list[FlexText] = []
    current_spans: list[FlexSpan] = []
    saw_newline = False

    def flush() -> None:
        spans = _merge_adjacent_spans(current_spans)
        if spans:
            cloned = component.copy()
            cloned["contents"] = spans
            split_components.append(cloned)
        current_spans.clear()

    for span in component.get("contents", []):
        if "\n" not in span["text"]:
            current_spans.append(span)
            continue
        saw_newline = True
        parts = span["text"].split("\n")
        for part_index, part in enumerate(parts):
            if part:
                split_span = span.copy()
                split_span["text"] = part
                current_spans.append(split_span)
            if part_index < len(parts) - 1:
                flush()
    if not saw_newline:
        return [component]
    flush()
    return split_components


def process_text_block_to_flex_components(text_block: str) -> list[FlexText]:
    lines = [line.strip() for line in text_block.splitlines() if line.strip()]
    return [
        part
        for component in process_line_to_flex_components("\n".join(lines))
        for part in _split_text_component_on_newlines(component)
    ]
