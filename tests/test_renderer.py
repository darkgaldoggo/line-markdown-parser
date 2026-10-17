"""Renderer regressions using synthetic content and reserved example domains."""

import json
import subprocess
import sys

import pytest

from line_markdown_parser import build_flex_message, estimate_flex_payload_size
from line_markdown_parser._renderer import build_flex_contents


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _spans(contents):
    return [node for node in _walk(contents) if node.get("type") == "span"]


def _text_components(contents):
    return [node for node in _walk(contents) if node.get("type") == "text"]


def _all_visible_text(contents):
    parts = []
    for node in _walk(contents):
        text = node.get("text")
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def _span_with_text(contents, text):
    for span in _spans(contents):
        if span.get("text") == text:
            return span
    raise AssertionError(
        f"span with text {text!r} not found in {json.dumps(contents, ensure_ascii=False)}"
    )


def test_inline_markdown_renders_as_flex_spans():
    contents = build_flex_contents("`code` *italic* **bold** ***both*** ~~gone~~")

    code = _span_with_text(contents, "code")
    italic = _span_with_text(contents, "italic")
    bold = _span_with_text(contents, "bold")
    both = _span_with_text(contents, "both")
    gone = _span_with_text(contents, "gone")

    assert code["color"] == "#C46A00"
    assert "`" not in _all_visible_text(contents)
    assert italic.get("style") == "italic"
    assert "weight" not in italic
    assert bold.get("weight") == "bold"
    assert bold["color"] == "#555555"
    assert both.get("weight") == "bold"
    assert both.get("style") == "italic"
    assert gone.get("decoration") == "line-through"


def test_emphasis_wrapping_inline_code_keeps_markers_hidden():
    contents = build_flex_contents(
        "bold **`b-code`** / italic *`i-code`* / both ***`x-code`*** / strike ~~`s-code`~~"
    )
    visible = _all_visible_text(contents)
    assert "**" not in visible
    assert "~~" not in visible
    assert "*" not in visible
    assert "`" not in visible

    b = _span_with_text(contents, "b-code")
    assert b.get("weight") == "bold"
    assert b["color"] == "#C46A00"

    i = _span_with_text(contents, "i-code")
    assert i.get("style") == "italic"
    assert i["color"] == "#C46A00"

    x = _span_with_text(contents, "x-code")
    assert x.get("weight") == "bold"
    assert x.get("style") == "italic"

    s = _span_with_text(contents, "s-code")
    assert s.get("decoration") == "line-through"


def test_bold_code_inside_list_item_does_not_leak_markers():
    contents = build_flex_contents(
        "ドキュメントに **`sample-model-v1`** の説明があります。\n\n"
        "- モデル名: **`sample-model-v1`**\n"
        "- 入力: **Text / Image**"
    )
    visible = _all_visible_text(contents)
    assert "**" not in visible

    model = _span_with_text(contents, "sample-model-v1")
    assert model.get("weight") == "bold"
    assert model["color"] == "#C46A00"

    plain = _span_with_text(contents, "Text / Image")
    assert plain.get("weight") == "bold"
    assert plain["color"] == "#555555"


def test_marker_line_multiline_bold_does_not_leak_markers():
    contents = build_flex_contents(
        "📌 **お知らせの見出し\n次の行にも強調を適用します。**"
    )
    visible = _all_visible_text(contents)
    assert "**" not in visible
    assert _span_with_text(contents, "お知らせの見出し").get("weight") == "bold"
    assert (
        _span_with_text(contents, "次の行にも強調を適用します。").get("weight")
        == "bold"
    )


def test_line_start_emphasis_is_not_treated_as_list_marker():
    contents = build_flex_contents(
        "**このライブラリは日本語に対応しています**という説明。\n"
        "*italic lead* も通常段落として扱う"
    )
    visible = _all_visible_text(contents)

    assert "• " not in visible
    assert "*という説明。" not in visible
    assert (
        _span_with_text(contents, "このライブラリは日本語に対応しています")["weight"]
        == "bold"
    )
    assert _span_with_text(contents, "italic lead")["style"] == "italic"


def test_multiline_bold_markers_apply_across_soft_line_breaks():
    contents = build_flex_contents(
        "次の段落は複数行の強調です。\n\n"
        "**最初の強調行\n"
        "これは絵文字を含む次の強調行です。🌸✨**\n\n"
        "最後の通常段落です。"
    )
    visible = _all_visible_text(contents)

    assert "**最初の強調行" not in visible
    assert "🌸✨**" not in visible
    assert _span_with_text(contents, "最初の強調行")["weight"] == "bold"
    assert (
        _span_with_text(
            contents,
            "これは絵文字を含む次の強調行です。🌸✨",
        )["weight"]
        == "bold"
    )


def test_headings_render_with_visible_size_hierarchy():
    contents = build_flex_contents(
        "# H1 見出し\n## H2 見出し\n### H3 見出し\n#### H4 見出し\n###### H6 見出し"
    )

    assert _span_with_text(contents, "H1 見出し")["size"] == "xxl"
    assert _span_with_text(contents, "H2 見出し")["size"] == "xl"
    assert _span_with_text(contents, "H3 見出し")["size"] == "lg"
    assert _span_with_text(contents, "H4 見出し")["size"] == "lg"
    assert _span_with_text(contents, "H6 見出し")["size"] == "lg"
    assert all(
        _span_with_text(contents, text)["weight"] == "bold"
        for text in [
            "H1 見出し",
            "H2 見出し",
            "H3 見出し",
            "H4 見出し",
            "H6 見出し",
        ]
    )


def test_code_span_does_not_reparse_markdown_inside():
    contents = build_flex_contents(
        "code span: `**not bold** and [x](https://example.com)`"
    )

    code = _span_with_text(contents, "**not bold** and [x](https://example.com)")
    assert code["color"] == "#C46A00"
    assert "weight" not in code
    assert not [node for node in _walk(contents) if node.get("action")]


def test_markdown_link_autolink_plain_url_and_punctuation_are_preserved():
    contents = build_flex_contents(
        "[A **B**](https://example.com/検索?q=AI) and "
        "<https://example.com/auto> and https://example.com/end."
    )

    actions = [node["action"]["uri"] for node in _walk(contents) if node.get("action")]
    assert actions == [
        "https://example.com/%E6%A4%9C%E7%B4%A2?q=AI",
        "https://example.com/auto",
        "https://example.com/end",
    ]
    assert _span_with_text(contents, "A ")["color"] == "#0066FF"
    link_b = _span_with_text(contents, "B")
    assert link_b["color"] == "#0066FF"
    assert link_b["decoration"] == "underline"
    assert link_b["weight"] == "bold"
    assert _all_visible_text(contents).endswith(".")


def test_markdown_link_label_can_include_inline_code():
    contents = build_flex_contents(
        "markdown link label styles: [**bold** and `code` label](https://example.com/label-style)"
    )
    visible = _all_visible_text(contents)
    actions = [node["action"]["uri"] for node in _walk(contents) if node.get("action")]

    assert actions == ["https://example.com/label-style"]
    assert "](" not in visible
    assert _span_with_text(contents, "bold")["weight"] == "bold"
    code = _span_with_text(contents, "code")
    assert code["color"] == "#0066FF"
    assert code["decoration"] == "underline"


def test_bold_list_item_spanning_action_uri_keeps_label_and_description_bold():
    contents = build_flex_contents(
        "- **[資料A](https://example.com/document-a)：説明A**\n"
        "- **[資料B](https://example.com/document-b)：説明B**"
    )

    assert "*" not in _all_visible_text(contents)
    assert [
        node["action"]["uri"] for node in _walk(contents) if node.get("action")
    ] == [
        "https://example.com/document-a",
        "https://example.com/document-b",
    ]
    for text in ("資料A", "資料B", "：説明A", "：説明B"):
        assert _span_with_text(contents, text)["weight"] == "bold"
    for text in ("資料A", "資料B"):
        assert _span_with_text(contents, text)["color"] == "#0066FF"
        assert _span_with_text(contents, text)["decoration"] == "underline"


@pytest.mark.parametrize(
    "delimiter,expected_style",
    [
        ("**", {"weight": "bold"}),
        ("__", {"weight": "bold"}),
        ("***", {"weight": "bold", "style": "italic"}),
        ("*", {"style": "italic"}),
        ("~~", {"decoration": "line-through"}),
    ],
)
def test_emphasis_spans_multiple_links_without_affecting_following_text(
    delimiter, expected_style
):
    contents = build_flex_contents(
        f"通常 {delimiter}前 [一](https://example.com/one) 中 "
        f"[二](https://example.com/two) 後{delimiter} 通常"
    )

    assert delimiter not in _all_visible_text(contents)
    for text in ("前", "中", "後"):
        span = next(span for span in _spans(contents) if span["text"].strip() == text)
        assert all(span.get(key) == value for key, value in expected_style.items())
    for text in ("一", "二"):
        span = _span_with_text(contents, text)
        assert span["decoration"] == "underline"
        assert all(
            span.get(key) == value
            for key, value in expected_style.items()
            if key != "decoration"
        )
    for span in _spans(contents):
        if "通常" in span["text"]:
            assert not any(key in span for key in ("weight", "style", "decoration"))


def test_multiline_link_emphasis_preserves_nested_label_code_and_uri():
    contents = build_flex_contents(
        "**前\n[A *B* `C**D`](https://example.com/a**b?q=c%26d+e)：後**"
    )

    assert _all_visible_text(contents) == "前🔗 A B C**D：後"
    for text in ("前", "A ", "B", "C**D", "：後"):
        assert _span_with_text(contents, text)["weight"] == "bold"
    assert _span_with_text(contents, "B")["style"] == "italic"
    assert [
        node["action"]["uri"] for node in _walk(contents) if node.get("action")
    ] == [
        "https://example.com/a**b?q=c%26d+e",
    ]


@pytest.mark.parametrize(
    "link",
    [
        "https://example.com/path",
        "<https://example.com/path>",
    ],
)
@pytest.mark.parametrize("delimiter", ["**", "__", "***", "*"])
def test_emphasis_around_bare_and_auto_url_does_not_enter_action_uri(link, delimiter):
    contents = build_flex_contents(f"{delimiter}{link}{delimiter}.")

    assert _all_visible_text(contents) == "🔗 https://example.com/path."
    assert [
        node["action"]["uri"] for node in _walk(contents) if node.get("action")
    ] == [
        "https://example.com/path",
    ]
    if len(delimiter) > 1:
        assert _span_with_text(contents, "https://example.com/path")["weight"] == "bold"


@pytest.mark.parametrize(
    "source",
    [
        "**[資料](https://example.com)：本文",
        "[資料](https://example.com)：本文**",
        "** [資料](https://example.com)：本文 **",
    ],
)
def test_unresolved_bold_markers_fall_back_to_plain_text(source):
    contents = build_flex_contents(source)

    assert "*" not in _all_visible_text(contents)
    assert "資料" in _all_visible_text(contents)
    assert "本文" in _all_visible_text(contents)
    assert all("weight" not in span for span in _spans(contents))


def test_link_bold_cleanup_preserves_escaped_markers_code_and_literal_uri():
    contents = build_flex_contents(
        r"\*\*説明\*\* `**コード**` 2**3 [資料](https://example.com/a**b)"
        "\nhttps://example.com/tail**"
    )

    assert "**説明**" in _all_visible_text(contents)
    assert _span_with_text(contents, "**コード**")["color"] == "#C46A00"
    assert "2**3" in _all_visible_text(contents)
    assert [
        node["action"]["uri"] for node in _walk(contents) if node.get("action")
    ] == [
        "https://example.com/a**b",
        "https://example.com/tail**",
    ]


def test_bold_around_unsupported_link_preserves_label_and_hides_destination():
    contents = build_flex_contents("**[attachment](sandbox://local/file.txt)**")

    assert _all_visible_text(contents) == "attachment"
    assert _span_with_text(contents, "attachment")["weight"] == "bold"
    assert not any(node.get("action") for node in _walk(contents))


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/file",
        "https://bad_host.example.com/file",
        "https://example.com/" + "x" * 1000,
    ],
)
def test_bold_around_unrenderable_uri_keeps_text_without_stray_markers(url):
    contents = build_flex_contents(f"**前 [資料]({url}) 後**")

    assert "**" not in _all_visible_text(contents)
    assert "資料" in _all_visible_text(contents)
    assert "前" in _all_visible_text(contents)
    assert "後" in _all_visible_text(contents)
    assert not any(node.get("action") for node in _walk(contents))


def test_markdown_link_destination_absorbs_parentheses_and_angle_brackets():
    contents = build_flex_contents(
        "[path_(test)](https://example.com/path_(test))\n"
        "[query parens](https://example.com/search?q=(test))\n"
        "[nested-ish](https://example.com/a_(b)_c)\n"
        "[angle URL](<https://example.com/path_(angle)>)\n"
        "[angle query](<https://example.com/search?q=(angle)&lang=ja>)"
    )
    visible = _all_visible_text(contents)
    actions = [node["action"]["uri"] for node in _walk(contents) if node.get("action")]

    assert actions == [
        "https://example.com/path_(test)",
        "https://example.com/search?q=(test)",
        "https://example.com/a_(b)_c",
        "https://example.com/path_(angle)",
        "https://example.com/search?q=(angle)&lang=ja",
    ]
    assert "](" not in visible
    assert "<https://" not in visible
    assert "_c)" not in visible
    assert visible.count("🔗 ") == 5


def test_encoded_url_is_preserved_without_roundtrip_corruption():
    contents = build_flex_contents(
        "[encoded amp](https://example.com/search?q=a%26b&lang=ja)\n"
        "[plus sign](https://example.com/search?q=a+b)\n"
        "[encoded slash](https://example.com/a%2Fb)"
    )
    actions = [node["action"]["uri"] for node in _walk(contents) if node.get("action")]

    assert actions == [
        "https://example.com/search?q=a%26b&lang=ja",
        "https://example.com/search?q=a+b",
        "https://example.com/a%2Fb",
    ]


def test_unencoded_non_ascii_url_is_still_quoted():
    contents = build_flex_contents("[検索](https://example.com/検索?q=AI)")
    actions = [node["action"]["uri"] for node in _walk(contents) if node.get("action")]

    assert actions == ["https://example.com/%E6%A4%9C%E7%B4%A2?q=AI"]


def test_inline_link_context_does_not_indent_surrounding_text():
    contents = build_flex_contents(
        "通常文の途中で [資料](https://example.com/document) を参照して、"
        "次に [two_(ok)](https://example.com/two_(ok)) を置く。"
    )
    non_action_span_texts = [
        span.get("text", "")
        for component in _text_components(contents)
        if not component.get("action")
        for span in component.get("contents", [])
    ]

    assert "通常文の途中で" in non_action_span_texts
    assert "を参照して、次に" in non_action_span_texts
    assert "を置く。" in non_action_span_texts
    assert all(
        not text.startswith(" ") for text in non_action_span_texts if text.strip()
    )
    assert all(not text.endswith(" ") for text in non_action_span_texts if text.strip())


def test_sandbox_markdown_link_keeps_label_without_exposing_destination():
    contents = build_flex_contents(
        "before [attachment](sandbox://local/file.txt) after"
    )
    visible = _all_visible_text(contents)

    assert "attachment" in visible
    assert "sandbox://" not in visible
    assert "before" in visible
    assert "after" in visible


def test_code_fence_renders_language_label_and_body():
    contents = build_flex_contents("```python\nprint('hi')\n```")
    text_nodes = _text_components(contents)

    assert any(
        node.get("text") == "python" and node.get("size") == "xxs"
        for node in text_nodes
    )
    assert any(node.get("text") == "print('hi')" for node in text_nodes)
    assert any(node.get("backgroundColor") == "#F5F5F5" for node in _walk(contents))


def test_code_fence_preserves_leading_indentation():
    contents = build_flex_contents(
        "```json5\n{\n  features: {\n    enabled: true\n  }\n}\n```"
    )
    code_nodes = [
        node.get("text")
        for node in _text_components(contents)
        if isinstance(node.get("text"), str) and node.get("text").startswith("{")
    ]

    assert code_nodes
    code = code_nodes[0]
    assert "\n\u00a0\u00a0features" in code
    assert "\n\u00a0\u00a0\u00a0\u00a0enabled" in code
    assert "\n  features" not in code


def test_blockquote_keeps_inline_formatting():
    contents = build_flex_contents("> quoted `code` and **bold**\n> next line")

    assert any(node.get("backgroundColor") == "#FFF7FA" for node in _walk(contents))
    assert _span_with_text(contents, "code")["color"] == "#C46A00"
    assert _span_with_text(contents, "bold")["weight"] == "bold"
    assert ">" not in _all_visible_text(contents)


def test_task_list_nested_list_and_table_fallback_render_readably():
    text = """- [x] done
  - [ ] nested `flag`

| key | value |
| --- | --- |
| code | `abc` |
"""
    contents = build_flex_contents(text)
    visible = _all_visible_text(contents)

    assert "☑ " in visible
    assert "☐ " in visible
    assert _span_with_text(contents, "flag")["color"] == "#C46A00"
    assert any(node.get("paddingStart") == "30px" for node in _walk(contents))
    assert any(node.get("text") == "table" for node in _text_components(contents))
    assert "| key | value |" in visible


def test_commonmark_list_variants_and_paren_ordered_list_render_as_lists():
    text = """* star bullet
+ plus bullet
- hyphen bullet
  * nested star
1) paren ordered
2. dot ordered
- [ ] task item
"""
    contents = build_flex_contents(text)
    visible = _all_visible_text(contents)

    assert "* star bullet" not in visible
    assert "+ plus bullet" not in visible
    assert "1) " in visible
    assert "2. " in visible
    assert "☐ " in visible
    assert any(node.get("paddingStart") == "30px" for node in _walk(contents))
    assert any(
        node.get("type") == "box"
        and node.get("layout") == "vertical"
        and node.get("margin") == "sm"
        for node in _walk(contents)
    )


def test_html_lite_and_escaped_markers_are_absorbed():
    contents = build_flex_contents("<strong>bold</strong> <code>x</code> \\*literal\\*")

    assert _span_with_text(contents, "bold")["weight"] == "bold"
    assert _span_with_text(contents, "x")["color"] == "#C46A00"
    assert "*literal*" in _all_visible_text(contents)


def test_flex_payload_estimate_stays_under_default_for_mixed_markdown_sample():
    sample = """# Summary
LLM output with `inline_code`, *italic*, **bold**, and [link](https://example.com).

> A useful quoted note.

1. First
2. Second

```json
{"ok": true}
```
"""

    message = build_flex_message(sample, alt_text="preview")
    assert message["type"] == "flex"
    assert estimate_flex_payload_size(sample) < 28000


@pytest.mark.parametrize(
    "destination",
    [
        "javascript:alert%281%29",
        "data:text/plain,example",
        "mailto:reader@example.com",
        "file:///tmp/example.txt",
        "sandbox://local/example.txt",
        "ftp://example.com/example.txt",
    ],
)
def test_unsupported_markdown_destinations_never_become_actions(destination):
    contents = build_flex_contents(f"before [label]({destination}) after")
    visible = _all_visible_text(contents)

    assert "before" in visible
    assert "label" in visible
    assert "after" in visible
    assert destination not in visible
    assert not any(node.get("action") for node in _walk(contents))


@pytest.mark.parametrize(
    "destination",
    [
        "https://reader@example.com/document",
        "https://bad_host.example.com/document",
    ],
)
def test_invalid_authority_never_becomes_an_action(destination):
    contents = build_flex_contents(f"[label]({destination})")

    assert "label" in _all_visible_text(contents)
    assert not any(node.get("action") for node in _walk(contents))


def test_unknown_html_is_visible_text_and_not_an_executable_component():
    source = "<widget>plain text</widget> <script>alert(1)</script>"
    contents = build_flex_contents(source)

    assert _all_visible_text(contents) == source
    assert not any(node.get("action") for node in _walk(contents))
    assert all(node.get("type") in {"box", "text", "span"} for node in _walk(contents))


def test_code_block_preserves_html_and_url_as_literal_text():
    source = "<strong>example</strong> https://example.com/document"
    contents = build_flex_contents(f"```html\n{source}\n```")

    assert any(node.get("text") == source for node in _text_components(contents))
    assert not any(node.get("action") for node in _walk(contents))


@pytest.mark.parametrize("literal", ["<b>x</b>", "<br>", "<BR />", "<code>x</code>"])
def test_inline_code_preserves_html_literals(literal):
    contents = build_flex_contents(f"before `{literal}` after")

    assert _span_with_text(contents, literal)["color"] == "#C46A00"
    assert _all_visible_text(contents) == f"before {literal} after"


def test_html_emphasis_wraps_multiple_literal_code_spans():
    contents = build_flex_contents(
        "<strong>before `<b>x</b>` between `<br>` after</strong><br>next"
    )

    for literal in ("<b>x</b>", "<br>"):
        span = _span_with_text(contents, literal)
        assert span["color"] == "#C46A00"
        assert span["weight"] == "bold"
    assert _span_with_text(contents, "next").get("weight") is None


@pytest.mark.parametrize("literal", ["<b>x</b>", "<br>", "`x` <b>y</b>"])
def test_html_code_preserves_its_contents(literal):
    contents = build_flex_contents(f"<strong><code>{literal}</code></strong>")

    span = _span_with_text(contents, literal)
    assert span["color"] == "#C46A00"
    assert span["weight"] == "bold"


def test_escaped_backticks_do_not_protect_html_from_normalization():
    contents = build_flex_contents(r"\`<b>x</b>\`")

    assert _all_visible_text(contents) == "`x`"
    assert _span_with_text(contents, "x")["weight"] == "bold"
    assert not any(span.get("color") == "#C46A00" for span in _spans(contents))


@pytest.mark.parametrize("opener,closer", [("`", "`"), ("<code>", "</code>")])
def test_code_markers_on_other_lines_do_not_suppress_html_breaks(opener, closer):
    contents = build_flex_contents(f"x {opener}y\nz <br> w\n{closer} q")

    visible_lines = [
        "".join(span["text"] for span in component.get("contents", []))
        for component in _text_components(contents)
    ]
    assert visible_lines == [f"x {opener}y", "z", "w", f"{closer} q"]
    assert not any(span.get("color") == "#C46A00" for span in _spans(contents))


def test_multiline_emphasis_preserves_inline_code_and_html_breaks():
    contents = build_flex_contents("**start\n`<br>` middle<br>end**")

    assert _span_with_text(contents, "<br>")["color"] == "#C46A00"
    assert all(span.get("weight") == "bold" for span in _spans(contents))
    assert _all_visible_text(contents) == "start<br> middleend"
    assert len(_text_components(contents)) == 3


@pytest.mark.parametrize(
    "destination",
    [
        "https://:",
        "https://:443",
        "https://example.com:abc",
        "https://example.com:99999",
        "https://example.com/%",
        "https://example.com/%2",
        "https://example.com/?q=%GG",
    ],
)
def test_malformed_http_url_stays_visible_without_an_action(destination):
    source = f"[label]({destination})"
    contents = build_flex_contents(source)

    assert _all_visible_text(contents) == source
    assert not any(node.get("action") for node in _walk(contents))


@pytest.mark.parametrize(
    "destination",
    [
        "https://example.com:443/document",
        "https://example.com/a@b,c;d:e!f$g&h'i(j)*k+l=m",
        "https://example.com/?path=/a:b@c,d&next=?x=1!$'()*+;",
        "https://example.com/#/route?id=1&next=a@b,c!$'()*+;",
        "https://example.com/a%2fb?q=%26#%3f",
        "https://example.com/path?",
        "https://example.com/path#",
        "https://example.com/path?#",
    ],
)
def test_uri_components_keep_reserved_characters_and_existing_escapes(destination):
    contents = build_flex_contents(f"[label](<{destination}>)")

    assert [
        node["action"]["uri"] for node in _walk(contents) if node.get("action")
    ] == [destination]


def test_non_ascii_uri_components_are_encoded_without_changing_delimiters():
    contents = build_flex_contents(
        "[label](https://example.com/検索?q=日本語#/項目?id=1)"
    )

    assert [
        node["action"]["uri"] for node in _walk(contents) if node.get("action")
    ] == [
        "https://example.com/%E6%A4%9C%E7%B4%A2?q=%E6%97%A5%E6%9C%AC%E8%AA%9E"
        "#/%E9%A0%85%E7%9B%AE?id=1"
    ]


@pytest.mark.parametrize("punctuation", ["、", "/", "|", "／", "。"])
def test_punctuation_only_paragraphs_and_list_items_remain_visible(punctuation):
    paragraph = build_flex_contents(f"A\n\n{punctuation}\n\nB")
    numbered_list = build_flex_contents(f"1. {punctuation}\n2. Normal")

    assert punctuation in _all_visible_text(paragraph)
    assert f"1. {punctuation}" in _all_visible_text(numbered_list)
    assert "2. Normal" in _all_visible_text(numbered_list)


def test_link_separator_cleanup_does_not_remove_punctuation_in_code():
    contents = build_flex_contents(
        "[A](https://example.com) / [B](https://example.org) `|`"
    )

    assert "/" not in _all_visible_text(contents)
    assert _span_with_text(contents, "|")["color"] == "#C46A00"


def test_many_unclosed_html_code_tags_finish_within_timeout():
    script = """
from line_markdown_parser import build_flex_contents

for prefix, opening in (
    ("", "<code>\\n"),
    ("<code>valid</code>\\n", "<code>\\n"),
    ("", "<code "),
):
    assert build_flex_contents(prefix + opening * 20_000)
print("ok")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    assert result.stdout.strip() == "ok"
