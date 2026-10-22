from copy import deepcopy

import pytest
from flex_assertions import assert_message

from line_markdown_parser import build_flex_message, convert_markdown_to_line_messages


@pytest.mark.parametrize(
    "text",
    [
        "---",
        "***",
        "# [Heading](https://example.com)",
        "> **quote**\n> [guide](https://example.org)",
        "- [ ] todo\n  - [x] done\n    1. nested",
        "```python\ndef sample():\n\treturn 'example'\n```",
        "| Name | Value |\n| --- | --- |\n| A | B |",
        "🙂 marker\n\nBody <strong>bold</strong><br>new line\n  indented",
    ],
)
def test_emitted_structures(text):
    for message in convert_markdown_to_line_messages(text, max_payload_bytes=1200):
        assert_message(message, 1200)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda message: message.update(type="text"),
        lambda message: message.update(altText="🙂" * 751),
        lambda message: message["contents"].update(type="carousel"),
        lambda message: message["contents"]["body"].pop("layout"),
        lambda message: message["contents"]["body"].update(contents=[]),
        lambda message: message["contents"]["body"].update(
            contents=[{"type": "_link", "text": "leaked"}]
        ),
        lambda message: message["contents"]["body"].update(contents=[{"type": "text"}]),
        lambda message: message["contents"]["body"].update(
            contents=[{"type": "text", "text": "both", "contents": []}]
        ),
        lambda message: message["contents"]["body"].update(
            contents=[{"type": "span", "text": "wrong parent"}]
        ),
        lambda message: message["contents"]["body"].update(
            contents=[{"type": "text", "contents": [{"type": "span", "text": ""}]}]
        ),
        lambda message: message["contents"]["body"].update(
            contents=[{"type": "text", "text": "bad", "wrap": "yes"}]
        ),
        lambda message: message["contents"]["body"].update(
            contents=[
                {
                    "type": "text",
                    "text": "bad",
                    "action": {"type": "uri", "uri": "urn:example"},
                }
            ]
        ),
        lambda message: message["contents"]["body"].update(
            contents=[
                {
                    "type": "text",
                    "text": "bad",
                    "action": {"type": "uri", "uri": "https://example.com/%no"},
                }
            ]
        ),
        lambda message: message["contents"]["body"].update(
            contents=[
                {
                    "type": "text",
                    "text": "bad",
                    "action": {
                        "type": "uri",
                        "uri": "https://example.com/" + "x" * 1000,
                    },
                }
            ]
        ),
    ],
)
def test_structure_assertions_reject_invalid_output(mutation):
    message = deepcopy(build_flex_message("valid"))
    mutation(message)
    with pytest.raises(AssertionError):
        assert_message(message)


@pytest.mark.parametrize(
    "uri", ["https://example.com:abc", "https://example.com:99999"]
)
def test_structure_assertions_reject_invalid_ports(uri):
    message = build_flex_message("body")
    message["contents"]["body"]["contents"] = [
        {"type": "text", "text": "bad", "action": {"type": "uri", "uri": uri}}
    ]
    with pytest.raises(AssertionError, match="invalid action URI"):
        assert_message(message)


def test_structure_assertions_reject_an_oversized_bubble():
    message = build_flex_message("body " * 100)
    with pytest.raises(AssertionError):
        assert_message(message, 200)


@pytest.mark.parametrize("patch", [{"color": "red"}, {"wrap": True}])
def test_structure_assertions_reject_invalid_span_properties(patch):
    message = build_flex_message("body")
    span = {"type": "span", "text": "body", **patch}
    message["contents"]["body"]["contents"] = [{"type": "text", "contents": [span]}]
    with pytest.raises(AssertionError):
        assert_message(message)
