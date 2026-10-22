"""Common inline contracts across layouts and source-length/byte splitting."""

import json

import pytest
from flex_assertions import actions, assert_message, visible_text, walk

from line_markdown_parser import (
    build_flex_message,
    convert_markdown_to_line_messages,
    estimate_flex_payload_size,
)

CONTEXTS = ["{}", "# {}", "## {}", "### {}", "> {}", "- {}", "1. {}", "🐶 {}"]
FEATURES = [
    ("**bold**", "bold", [], {"weight": "bold"}),
    ("*italic*", "italic", [], {"style": "italic"}),
    ("~~strike~~", "strike", [], {"decoration": "line-through"}),
    ("`https://example.com/*code*`", "https://example.com/*code*", [], {}),
    ("<b>bold</b>", "bold", [], {"weight": "bold"}),
    (
        "[Guide](https://example.com/docs)",
        "Guide",
        ["https://example.com/docs"],
        {"decoration": "underline"},
    ),
    (
        "**before [Guide](https://example.com) after**",
        "Guide",
        ["https://example.com"],
        {"weight": "bold", "decoration": "underline"},
    ),
    (
        "https://example.com/path?q=%20#part",
        "https://example.com/path?q=%20#part",
        ["https://example.com/path?q=%20#part"],
        {"decoration": "underline"},
    ),
    (
        "<https://example.com>",
        "https://example.com",
        ["https://example.com"],
        {"decoration": "underline"},
    ),
    ("[Guide](urn:example)", "Guide", [], {}),
    ("[bad](https://example.com/%Q0)", "[bad](https://example.com/%Q0)", [], {}),
]


@pytest.mark.parametrize("context", CONTEXTS)
@pytest.mark.parametrize("feature,expected,uris,style", FEATURES)
@pytest.mark.parametrize("split", [False, True], ids=["single", "split"])
def test_inline_contract_in_every_context(
    context, feature, expected, uris, style, split
):
    line = context.format(feature)
    repeats = 4 if split else 1
    text = (line + "\n\n") * repeats
    messages = convert_markdown_to_line_messages(
        text, max_length=len(line) + 2 if split else 1600
    )
    assert len(messages) == repeats
    assert actions(messages) == uris * repeats
    for message in messages:
        assert_message(message)
        inline_text = "".join(
            node["text"] for node in walk(message) if node.get("type") == "span"
        )
        if context.startswith("🐶"):
            inline_text = inline_text.removeprefix("🐶").lstrip()
        expected_text = "🔗 " + expected if uris else expected
        if feature.startswith("**before"):
            expected_text = "before" + expected_text + "after"
        assert inline_text == expected_text
        spans = [
            node
            for node in walk(message)
            if node.get("type") == "span" and expected == node["text"]
        ]
        assert spans and all(
            all(span.get(key) == value for key, value in style.items())
            for span in spans
        )
        for span in spans:
            for key, default in (
                ("weight", "regular"),
                ("style", "normal"),
                ("decoration", "none"),
            ):
                expected_style = (
                    "bold"
                    if key == "weight" and context.startswith("#")
                    else style.get(key, default)
                )
                assert span.get(key, default) == expected_style
            if feature.startswith("`"):
                assert span["color"] == (
                    "#444444" if context.startswith("#") else "#C46A00"
                )
        if context.startswith("#"):
            size = (
                "xxl"
                if context.startswith("# ")
                else "xl"
                if context.startswith("## ")
                else "lg"
            )
            assert all(
                node.get("weight") == "bold" and node.get("size") == size
                for node in walk(message)
                if node.get("type") == "span"
            )


def test_heading_mixes_text_links_emphasis_and_literal_code():
    message = build_flex_message(
        "## Start **[A](https://example.com/a)** `https://example.net/code` and [*B*](https://example.org/b)"
    )
    assert_message(message)
    assert actions(message) == ["https://example.com/a", "https://example.org/b"]
    visible = visible_text(message)
    for fragment in ("Start", "🔗 A", "https://example.net/code", "and", "🔗 B"):
        assert fragment in visible
    assert "[A]" not in visible and "[B]" not in visible
    assert all(
        node["size"] == "xl" for node in walk(message) if node.get("type") == "span"
    )
    assert any(
        node.get("style") == "italic" and node["text"] == "B"
        for node in walk(message)
        if node.get("type") == "span"
    )


def test_heading_links_are_preserved_under_byte_splitting():
    text = "\n\n".join(f"# [Guide {i}](https://example.com/{i})" for i in range(30))
    messages = convert_markdown_to_line_messages(
        text, max_length=10000, max_payload_bytes=1000
    )
    assert len(messages) > 1
    assert actions(messages) == [f"https://example.com/{i}" for i in range(30)]
    for message in messages:
        assert_message(message, 1000)


def test_heading_long_link_label_keeps_the_existing_shortening_rule():
    text = "# [" + "x" * 60 + "](https://example.com)"
    message = build_flex_message(text)
    assert visible_text(message) == "🔗 " + "x" * 37 + "..."
    assert actions(message) == ["https://example.com"]
    assert estimate_flex_payload_size(text) == len(
        json.dumps(
            message["contents"], ensure_ascii=False, separators=(",", ":")
        ).encode()
    )


@pytest.mark.parametrize(
    "delimiter,style",
    [
        ("**", {"weight": "bold"}),
        ("*", {"style": "italic"}),
        ("~~", {"decoration": "line-through"}),
    ],
)
@pytest.mark.parametrize("code_on_start_line", [False, True])
def test_multiline_emphasis_ignores_delimiters_inside_code(
    delimiter, style, code_on_start_line
):
    separator = " " if code_on_start_line else "\n"
    source = f"{delimiter}start{separator}`literal{delimiter}`\nend{delimiter}"
    message = build_flex_message(source)
    assert_message(message)
    assert (
        visible_text(message)
        == f"start{' ' if code_on_start_line else ''}literal{delimiter}end"
    )
    spans = [node for node in walk(message) if node.get("type") == "span"]
    assert spans and all(
        all(span.get(key) == value for key, value in style.items()) for span in spans
    )
    assert any(
        span["text"] == f"literal{delimiter}" and span["color"] == "#C46A00"
        for span in spans
    )


@pytest.mark.parametrize("context", CONTEXTS)
def test_bare_url_adjacent_to_markdown_link_keeps_both_destinations(context):
    source = context.format("https://example.com[Guide](https://example.org/docs)")
    messages = convert_markdown_to_line_messages(source)
    assert actions(messages) == ["https://example.com", "https://example.org/docs"]
    assert "[Guide]" not in visible_text(messages)
    for message in messages:
        assert_message(message)


def test_link_after_multiline_inline_code_uses_the_same_code_ranges():
    source = "> `a\n> b` [Guide](https://example.com) `c`"
    message = build_flex_message(source)
    assert_message(message)
    assert actions(message) == ["https://example.com"]
    assert visible_text(message) == " a b🔗 Guidec"
    assert "[Guide]" not in visible_text(message)
