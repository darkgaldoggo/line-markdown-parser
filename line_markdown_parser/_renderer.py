"""Flex layout for recognized Markdown blocks, without I/O or logging."""

from ._blocks import Block, parse_blocks
from ._flex import FlexBox, FlexComponent, FlexText
from ._inline_renderer import (
    BODY_TEXT_COLOR,
    process_line_to_flex_components,
    process_text_block_to_flex_components,
)

MUTED_TEXT_COLOR = "#888888"
CODE_BLOCK_BACKGROUND = "#F5F5F5"
CODE_BLOCK_INDENT_SPACE = "\xa0"


def _paragraph_box(
    components: list[FlexComponent], *, margin: str = "md"
) -> FlexBox | None:
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


def _spacer_component() -> FlexText:
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


def _render_code_block(block: Block) -> FlexBox | None:
    language, body = block.language, block.text
    if not language and (not body.strip()):
        return None
    block_contents: list[FlexComponent] = []
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


def _render_separator() -> FlexText:
    return {
        "type": "text",
        "text": "───────────────────────",
        "wrap": True,
        "color": "#CCCCCC",
        "size": "sm",
        "align": "center",
        "margin": "none",
    }


def _render_quote_block(quote_text: str) -> FlexBox | None:
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
                "contents": list(inner_components),
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


def _render_table_block(table_lines: tuple[str, ...]) -> FlexBox | None:
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


def _render_list_item(block: Block) -> FlexBox | None:
    indent_level = block.level
    display_bullet = block.bullet
    if indent_level == 0:
        padding_start = "10px"
        marker = display_bullet
    elif indent_level <= 2:
        padding_start = "30px"
        marker = display_bullet if block.ordered or block.is_task else "◦ "
    else:
        padding_start = "50px"
        marker = display_bullet if block.ordered or block.is_task else "▪ "
    item_components = process_text_block_to_flex_components(block.text)
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
                "contents": list(item_components),
                "flex": 1,
                "margin": "sm",
                "spacing": "xs",
            },
        ],
        "margin": "xs",
        "paddingStart": padding_start,
        "alignItems": "flex-start",
    }


def _render_heading(text: str, level: int) -> FlexComponent | None:
    components = process_line_to_flex_components(text, heading_level=level)
    if len(components) == 1:
        components[0]["margin"] = "xs"
        return components[0]
    return _paragraph_box(list(components), margin="xs")


def _render_inline_block(text: str) -> list[FlexText]:
    if "\n" in text:
        return process_text_block_to_flex_components(text)
    return process_line_to_flex_components(text)


def _render_block(block: Block) -> FlexComponent | None:
    if block.kind == "spacer":
        return _spacer_component()
    if block.kind == "separator":
        return _render_separator()
    if block.kind == "code":
        return _render_code_block(block)
    if block.kind == "table":
        return _render_table_block(block.lines)
    if block.kind == "quote":
        return _render_quote_block(block.text)
    if block.kind == "heading":
        return _render_heading(block.text, block.level)
    if block.kind == "list":
        return _render_list_item(block)
    if block.kind == "paragraph":
        return _paragraph_box(
            [
                component
                for line in block.lines
                for component in _render_inline_block(line)
            ]
        )
    if block.kind == "marker":
        return _paragraph_box(list(_render_inline_block(block.text)))
    components = process_line_to_flex_components(block.text)
    if not components:
        return None
    return {
        "type": "box",
        "layout": "vertical",
        "contents": list(components),
        "margin": "xs",
        "paddingStart": "20px"
        if block.level <= 2
        else "40px"
        if block.level <= 4
        else "60px",
    }


def build_flex_contents(text_message: str) -> list[FlexComponent]:
    """Render recognized blocks; all inline contexts use the same parser."""
    if not isinstance(text_message, str):
        raise TypeError("text_message must be a string")
    rendered = [
        (block.kind, component)
        for block in parse_blocks(text_message)
        if (component := _render_block(block))
    ]
    if not rendered and text_message.strip():
        return list(process_line_to_flex_components(text_message.strip()))
    # Trim by syntax kind, without inferring semantics from rendered text/color.
    start, end = 0, len(rendered)
    while start < end and rendered[start][0] == "separator":
        start += 1
    while end > start and rendered[end - 1][0] == "separator":
        end -= 1
    return [component for _, component in rendered[start:end]]
