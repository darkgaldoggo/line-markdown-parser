import pytest
from flex_assertions import visible_text

from line_markdown_parser import build_flex_contents
from line_markdown_parser._inline import _normalize_inline_html_lite


@pytest.mark.parametrize(
    "tag,delimiter",
    [
        ("strong", "**"),
        ("b", "**"),
        ("em", "*"),
        ("i", "*"),
        ("s", "~~"),
        ("del", "~~"),
    ],
)
def test_html_pairing_keeps_supported_and_malformed_behavior(tag, delimiter):
    assert (
        _normalize_inline_html_lite(f"<{tag}>word</{tag}>")
        == f"{delimiter}word{delimiter}"
    )
    assert (
        _normalize_inline_html_lite(
            f"<{tag.upper()} class='example'>word</{tag.upper()}>"
        )
        == f"{delimiter}word{delimiter}"
    )
    for text in (f"<{tag}>" * 20, f"<{tag}" * 20, f"</{tag}>word<{tag}>"):
        assert _normalize_inline_html_lite(text) == text
        assert visible_text(build_flex_contents(text)) == text
    # Same-tag nesting follows the existing lightweight first-pair behavior.
    assert (
        _normalize_inline_html_lite(f"<{tag}><{tag}>word</{tag}></{tag}>")
        == f"{delimiter}<{tag}>word{delimiter}</{tag}>"
    )
    source = f"<{tag}>first</{tag}> " + f"<{tag}>" * 20
    assert (
        _normalize_inline_html_lite(source)
        == f"{delimiter}first{delimiter} " + f"<{tag}>" * 20
    )


def test_nested_tags_and_code_protection_remain_supported():
    assert (
        _normalize_inline_html_lite("<strong>bold <em>both</em></strong>")
        == "**bold *both***"
    )
    for source in ("`<b>literal</b>`", "<code><b>literal</b></code>"):
        assert visible_text(build_flex_contents(source)) == "<b>literal</b>"
    assert (
        _normalize_inline_html_lite("<b>first</b><b>second</b>")
        == "**first****second**"
    )


@pytest.mark.parametrize(
    "tag,key,value",
    [
        ("strong", "weight", "bold"),
        ("b", "weight", "bold"),
        ("em", "style", "italic"),
        ("i", "style", "italic"),
        ("s", "decoration", "line-through"),
        ("del", "decoration", "line-through"),
    ],
)
@pytest.mark.parametrize("adjacent", [False, True])
def test_supported_html_tags_through_public_renderer(tag, key, value, adjacent):
    from flex_assertions import walk

    source = f"<{tag}>first</{tag}>"
    if adjacent:
        source += f"<{tag}>second</{tag}>"
    contents = build_flex_contents(source)
    spans = [node for node in walk(contents) if node.get("type") == "span"]
    assert visible_text(contents) == ("firstsecond" if adjacent else "first")
    assert spans and all(span.get(key) == value for span in spans)
