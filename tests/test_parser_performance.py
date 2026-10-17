import json
import subprocess
import sys

import pytest

from line_markdown_parser import build_flex_contents


@pytest.mark.parametrize(
    "function_name,source",
    [
        ("build_flex_contents", "[x](" + "a" * 1000),
        ("split_long_text", "[x](" + "a" * 1000),
        ("build_flex_contents", "[" * 200_000),
        ("build_flex_contents", "*a " * 30_000),
        ("build_flex_contents", "*a\n" * 3000),
        ("convert_markdown_to_line_messages", "*a\n" * 3000),
    ],
    ids=[
        "unclosed-link-render",
        "unclosed-link-split",
        "unclosed-labels",
        "unclosed-inline-emphasis",
        "unclosed-multiline-emphasis-render",
        "unclosed-multiline-emphasis-convert",
    ],
)
def test_unclosed_markdown_finishes_within_generous_timeout(function_name, source):
    # A subprocess bounds a regression without leaving a stuck parser in pytest.
    # The fixed cases take well under a second; allow slower CI hosts ample room.
    script = """
import json
import sys
import line_markdown_parser

function_name, source = json.load(sys.stdin)
assert getattr(line_markdown_parser, function_name)(source)
print("ok")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        input=json.dumps([function_name, source]),
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    assert result.stdout.strip() == "ok"


def _spans(value):
    if isinstance(value, dict):
        if value.get("type") == "span":
            yield value
        for child in value.values():
            yield from _spans(child)
    elif isinstance(value, list):
        for child in value:
            yield from _spans(child)


def test_multiline_emphasis_has_no_short_lookahead_limit():
    source = "**start\n" + "middle\n" * 3000 + "end**"
    spans = list(_spans(build_flex_contents(source)))
    assert spans[0]["text"] == "start"
    assert spans[-1]["text"] == "end"
    assert all(span.get("weight") == "bold" for span in spans)


@pytest.mark.parametrize("boundary", ["", "# Heading", "- item", "> quote", "  indent"])
def test_multiline_emphasis_does_not_cross_block_boundaries(boundary):
    contents = build_flex_contents(f"*start\n{boundary}\nend*")
    assert not any(span.get("style") == "italic" for span in _spans(contents))
