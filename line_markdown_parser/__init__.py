"""Markdown to LINE Flex Messages, with no network or SDK dependencies."""

from .converter import (
    DEFAULT_MAX_FLEX_PAYLOAD_BYTES,
    build_flex_contents,
    build_flex_message,
    convert_markdown_to_line_messages,
    estimate_flex_payload_size,
    split_long_text,
)

__version__ = "0.1.2"
__all__ = [
    "DEFAULT_MAX_FLEX_PAYLOAD_BYTES",
    "build_flex_contents",
    "build_flex_message",
    "convert_markdown_to_line_messages",
    "estimate_flex_payload_size",
    "split_long_text",
]
