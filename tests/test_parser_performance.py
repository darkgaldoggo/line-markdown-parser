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
        ("build_flex_contents", r"\[" * 90_000),
        ("build_flex_contents", "[label `a[b]` " * 10_000),
        ("build_flex_contents", "*a " * 30_000),
        ("build_flex_contents", "*a\n" * 3000),
        ("convert_markdown_to_line_messages", "*a\n" * 3000),
        ("build_flex_contents", "<b" * 90_000),
    ],
    ids=[
        "unclosed-link-render",
        "unclosed-link-split",
        "unclosed-labels",
        "escaped-brackets",
        "unclosed-labels-containing-code",
        "unclosed-inline-emphasis",
        "unclosed-multiline-emphasis-render",
        "unclosed-multiline-emphasis-convert",
        "unfinished-html-opener",
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
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_link_scanning_does_not_rescan_later_destinations():
    script = """
from line_markdown_parser._syntax import _iter_links

for unit, count in (("[A](https://example.com),", 8000), ("[x](urn:item)", 15000)):
    assert len(list(_iter_links(unit * count))) == count
print("ok")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
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


@pytest.mark.parametrize("tag", ["b", "strong", "em", "i", "s", "del"])
def test_unclosed_html_tags_are_bounded_at_every_public_entry_point(tag):
    # Bound each adversarial input independently. Combining all six tags under
    # one timeout measures cumulative work and is sensitive to CI host speed.
    script = r"""
import sys
import line_markdown_parser as parser

unit = f"<{sys.argv[1]}>"
source = unit * (180_000 // len(unit))
contents = parser.build_flex_contents(source)
assert contents
assert parser.estimate_flex_payload_size(source) > 30_000
try:
    parser.build_flex_message(source)
except ValueError as error:
    assert "30,000" in str(error)
else:
    raise AssertionError("oversized message accepted")
parts = parser.split_long_text(source, max_length=200_000)
assert "".join(parts) == source
messages = parser.convert_markdown_to_line_messages(source, max_length=200_000)
assert len(messages) == len(parts) > 1
print("ok")
"""
    result = subprocess.run(
        [sys.executable, "-c", script, tag],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
