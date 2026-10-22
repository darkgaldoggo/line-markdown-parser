"""Assertions for this library's emitted subset, not a general LINE validator.

Reference: https://developers.line.biz/en/reference/messaging-api/#flex-message
Keep these rules independent of production TypedDict definitions so that missing
required fields, invalid parent-child relations, and leaked tokens are detected.
"""

import json
import re
from urllib.parse import urlsplit


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def visible_text(value):
    return "".join(node["text"] for node in walk(value) if "text" in node)


def actions(value):
    return [node["uri"] for node in walk(value) if node.get("type") == "uri"]


def _properties(node, allowed):
    assert set(node) <= set(allowed.split())
    for name in ("color", "backgroundColor"):
        if name in node:
            assert isinstance(node[name], str)
            assert re.fullmatch(r"#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?", node[name])
    for name in (
        "size",
        "margin",
        "spacing",
        "paddingAll",
        "paddingStart",
        "width",
        "cornerRadius",
    ):
        if name in node:
            assert isinstance(node[name], str) and node[name]
    for name, values in {
        "weight": {"regular", "bold"},
        "style": {"normal", "italic"},
        "decoration": {"none", "underline", "line-through"},
        "align": {"start", "end", "center"},
        "gravity": {"top", "bottom", "center"},
        "alignItems": {"flex-start", "flex-end", "center"},
    }.items():
        if name in node:
            assert node[name] in values
    if "wrap" in node:
        assert type(node["wrap"]) is bool
    if "flex" in node:
        assert type(node["flex"]) is int and node["flex"] >= 0


def _component(node, *, span=False, depth=0):
    # The renderer emits shallow layouts regardless of Markdown nesting.
    assert depth <= 8
    assert isinstance(node, dict)
    kind = node.get("type")
    if span:
        assert kind == "span"
        _properties(node, "type text color size weight style decoration")
        assert isinstance(node.get("text"), str) and node["text"]
    elif kind == "box":
        _properties(
            node,
            "type layout contents spacing margin paddingAll paddingStart backgroundColor cornerRadius width flex alignItems",
        )
        assert node.get("layout") in {"vertical", "horizontal", "baseline"}
        assert isinstance(node.get("contents"), list) and node["contents"]
        for child in node["contents"]:
            _component(child, depth=depth + 1)
    else:
        assert kind == "text"
        _properties(
            node,
            "type text contents wrap margin size weight color align gravity flex action",
        )
        assert ("text" in node) != ("contents" in node)
        if "text" in node:
            assert isinstance(node["text"], str) and node["text"]
        else:
            assert isinstance(node["contents"], list) and node["contents"]
            for child in node["contents"]:
                _component(child, span=True, depth=depth + 1)
        if "action" in node:
            action = node["action"]
            assert isinstance(action, dict) and set(action) == {"type", "uri"}
            assert action["type"] == "uri"
            uri = action["uri"]
            assert isinstance(uri, str) and 0 < len(uri) <= 1000 and uri.isascii()
            assert not re.search(r"\s|%(?![0-9a-fA-F]{2})", uri)
            try:
                parsed = urlsplit(uri)
                port = parsed.port
            except ValueError as error:
                raise AssertionError("invalid action URI") from error
            assert parsed.scheme in {"http", "https"} and parsed.hostname
            assert port is None or 0 <= port <= 65535


def assert_message(message, max_payload_bytes=30000):
    assert set(message) == {"type", "altText", "contents"}
    assert message["type"] == "flex"
    assert isinstance(message["altText"], str) and message["altText"].strip()
    assert len(message["altText"].encode("utf-16-le")) // 2 <= 1500
    bubble = message["contents"]
    assert set(bubble) == {"type", "size", "body"}
    assert bubble["type"] == "bubble" and bubble["size"] == "giga"
    assert bubble["body"]["type"] == "box"
    _component(bubble["body"])
    assert (
        len(
            json.dumps(bubble, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        )
        <= max_payload_bytes
    )
    assert json.loads(json.dumps(message)) == message
