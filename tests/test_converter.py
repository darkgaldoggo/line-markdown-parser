"""Public API contracts using synthetic Markdown only."""

import json
import random

import pytest

from line_markdown_parser import (
    build_flex_contents,
    build_flex_message,
    convert_markdown_to_line_messages,
    estimate_flex_payload_size,
    split_long_text,
)


def _bytes(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


def test_messages_are_plain_json_without_delivery_metadata():
    messages = convert_markdown_to_line_messages("# Summary\n\n**Ready** for review.")
    assert len(messages) == 1
    assert set(messages[0]) == {"type", "altText", "contents"}
    assert messages[0]["contents"]["body"]["contents"]
    assert json.loads(json.dumps(messages)) == messages
    assert "postback" not in json.dumps(messages)


@pytest.mark.parametrize("text", ["", " ", "\n\t"])
def test_empty_input(text):
    assert convert_markdown_to_line_messages(text) == []
    assert split_long_text(text) == []
    assert build_flex_contents(text) == []
    with pytest.raises(ValueError, match="empty"):
        build_flex_message(text)


@pytest.mark.parametrize("text", [None, 123, b"text", ["text"]])
def test_non_string_input_rejected(text):
    for function in (
        build_flex_contents,
        build_flex_message,
        split_long_text,
        estimate_flex_payload_size,
        convert_markdown_to_line_messages,
    ):
        with pytest.raises(TypeError, match="string"):
            function(text)


def test_invalid_unicode_rejected():
    with pytest.raises(ValueError, match="Unicode"):
        convert_markdown_to_line_messages("before" + chr(0xD800) + "after")


def test_input_budget_is_in_utf8_bytes():
    with pytest.raises(ValueError, match="input limit"):
        convert_markdown_to_line_messages("あ" * 66_667)


@pytest.mark.parametrize("text", ["---", "___", "***"])
def test_separator_only_input_still_has_visible_content(text):
    assert build_flex_message(text)["contents"]["body"]["contents"]


def test_estimate_matches_utf8_bubble():
    text = "日本語と🙂 **emphasis**\n\n[Docs](https://example.com)"
    assert estimate_flex_payload_size(text) == _bytes(
        build_flex_message(text)["contents"]
    )


def test_single_message_rejects_oversized_output():
    with pytest.raises(ValueError, match="30,000"):
        build_flex_message("word " * 10_000)


def test_single_message_has_fresh_mutable_results():
    first = build_flex_message("**Title**")
    first["contents"]["body"]["contents"].clear()
    assert build_flex_message("**Title**")["contents"]["body"]["contents"]


@pytest.mark.parametrize("alt", ["a" * 1600, "🙂" * 900, "a" * 1499 + "🙂"])
def test_alt_text_limit_counts_utf16(alt):
    result = build_flex_message("body", alt_text=alt)["altText"]
    assert len(result.encode("utf-16-le")) // 2 <= 1500
    assert result.endswith("…")
    assert result.encode("utf-8")


def test_alt_text_at_exact_limit_is_not_truncated():
    alt = "🙂" * 750
    assert build_flex_message("body", alt_text=alt)["altText"] == alt


@pytest.mark.parametrize("alt", ["", "  "])
def test_empty_explicit_alt_text_rejected(alt):
    with pytest.raises(ValueError, match="alt_text"):
        convert_markdown_to_line_messages("body", alt_text=alt)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_length": 0},
        {"max_length": -1},
        {"max_length": True},
        {"max_length": 1.5},
        {"max_payload_bytes": 0},
        {"max_payload_bytes": True},
        {"max_payload_bytes": 30_001},
        {"max_payload_bytes": 1.5},
    ],
)
def test_invalid_limits(kwargs):
    with pytest.raises(ValueError):
        split_long_text("sample", **kwargs)


def test_impossible_budget_rejected_instead_of_returning_invalid_payload():
    with pytest.raises(ValueError, match="too small"):
        split_long_text("a", max_payload_bytes=1)
    with pytest.raises(ValueError, match="too small"):
        split_long_text("```python\nx\n```", max_length=4)


def test_long_text_is_not_capped_to_five_messages():
    text = "日本語🙂" * 600
    messages = convert_markdown_to_line_messages(
        text, max_length=120, alt_text="Summary"
    )
    assert len(messages) > 5
    assert all(message["altText"] == "Summary" for message in messages)
    parts = split_long_text(text, max_length=120)
    assert "".join(parts) == text
    assert all(len(part) <= 120 for part in parts)


def test_code_block_with_blank_lines_stays_together_when_it_fits():
    code = "```python\ndef first():\n    pass\n\ndef second():\n    return 1\n```"
    parts = split_long_text("Introduction\n\n" + code + "\n\nConclusion")
    assert len(parts) == 1
    assert code in parts[0]


@pytest.mark.parametrize(
    "body",
    ["x" * 8000, "あ🙂" * 1600, "\n".join(f"line_{i:03d} = {i}" for i in range(200))],
)
def test_split_code_enforces_budget_after_wrapping(body):
    parts = split_long_text(
        "```python\n" + body + "\n```", max_length=400, max_payload_bytes=1200
    )
    assert len(parts) > 1
    for part in parts:
        assert len(part) <= 400
        assert part.startswith("```python\n")
        assert part.endswith("\n```")
        assert part.count("```") == 2
        assert estimate_flex_payload_size(part) <= 1200
    # Remove only the wrapper added by the splitter, preserving original data.
    assert "".join(part[len("```python\n") : -len("\n```")] for part in parts) == body


def test_dense_markdown_splits_by_rendered_bytes():
    text = "\n".join(
        f"- **Item {i}** [Docs](https://example.com/{i})" for i in range(80)
    )
    parts = split_long_text(text, max_length=10_000, max_payload_bytes=2500)
    assert len(parts) > 1
    assert "".join(parts) == text
    assert all(estimate_flex_payload_size(part) <= 2500 for part in parts)


@pytest.mark.parametrize(
    "link", ["https://example.com/document", "[guide](https://example.com/document)"]
)
def test_splitting_never_creates_a_different_click_destination(link):
    with pytest.raises(ValueError, match="intact link"):
        split_long_text(link, max_length=20)
    text = ("prefix " * 12) + link + (" suffix" * 12)
    parts = split_long_text(text, max_length=50)
    assert "".join(parts) == text
    assert sum(link in part for part in parts) == 1


def test_link_label_containing_spaces_stays_intact_at_preferred_boundary():
    link = "[A guide to this library](https://example.com)"
    parts = split_long_text("Start\n" + link + "\nEnd " * 10, max_length=52)
    assert sum(link in part for part in parts) == 1


def test_intact_link_at_exact_byte_budget_can_be_split_from_following_text():
    link = "[guide](https://example.com/document)"
    text = link + " suffix" * 40
    parts = split_long_text(text, max_payload_bytes=estimate_flex_payload_size(link))
    assert parts[0] == link
    assert "".join(parts) == text


def test_deterministic_mixed_input_has_valid_bounded_json():
    rng = random.Random(42)
    vocabulary = [
        "日本語🙂",
        "hello",
        "**bold**",
        "`code`",
        "\n",
        "- item\n",
        "[link](https://example.com)",
        " ",
    ]
    for _ in range(30):
        text = "".join(rng.choices(vocabulary, k=50))
        messages = convert_markdown_to_line_messages(text, max_payload_bytes=1800)
        assert messages
        assert all(_bytes(message["contents"]) <= 1800 for message in messages)
        assert all(message["contents"]["body"]["contents"] for message in messages)
