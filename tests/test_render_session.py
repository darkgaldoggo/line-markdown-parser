"""Behavioral checks for call-local reuse and ownership of returned JSON."""

from collections import Counter
from copy import deepcopy
from sys import getsizeof

import pytest
from flex_assertions import assert_message

from line_markdown_parser import (
    convert_markdown_to_line_messages,
    converter,
    split_long_text,
)


def _record_renders(monkeypatch):
    calls = Counter()
    render = converter._render_contents

    def counted(text):
        calls[text] += 1
        return render(text)

    monkeypatch.setattr(converter, "_render_contents", counted)
    return calls


@pytest.mark.parametrize(
    "function", [convert_markdown_to_line_messages, split_long_text]
)
@pytest.mark.parametrize(
    "source",
    [
        "**short** [guide](https://example.com)",
        "\n".join(f"- **Item {i}** [Docs](https://example.com/{i})" for i in range(80)),
    ],
)
def test_candidates_are_rendered_once_per_call(monkeypatch, function, source):
    calls = _record_renders(monkeypatch)
    result = function(source)
    assert result and calls
    assert max(calls.values()) == 1
    first_counts = calls.copy()
    assert function(source) == result
    assert calls == Counter({text: count * 2 for text, count in first_counts.items()})


def _mutable_ids(value):
    if isinstance(value, dict):
        yield id(value)
        for child in value.values():
            yield from _mutable_ids(child)
    elif isinstance(value, list):
        yield id(value)
        for child in value:
            yield from _mutable_ids(child)


def test_repeated_chunks_have_independent_mutable_trees(monkeypatch):
    calls = _record_renders(monkeypatch)
    unit = "# [Guide](https://example.com)\n\n"
    messages = convert_markdown_to_line_messages(unit * 5, max_length=len(unit))
    assert len(messages) == 5 and calls[unit] == 1
    trees = [set(_mutable_ids(message)) for message in messages]
    assert sum(map(len, trees)) == len(set.union(*trees))
    expected = deepcopy(messages[1:])
    messages[0]["contents"]["body"]["contents"].clear()
    assert messages[1:] == expected
    assert convert_markdown_to_line_messages(unit, max_length=len(unit)) == expected[:1]


def test_bounded_layout_cache_preserves_results_when_evicted(monkeypatch):
    source = "\n\n".join(f"# [Guide {i}](https://example.com/{i})" for i in range(50))
    expected = convert_markdown_to_line_messages(source, max_length=100)
    monkeypatch.setattr(converter._RenderSession, "_MAX_CACHED_BYTES", 800)
    actual = convert_markdown_to_line_messages(source, max_length=100)
    assert actual == expected
    for message in actual:
        assert_message(message)


@pytest.mark.parametrize("cache_bytes", [0, 1, 800])
def test_revisited_chunks_after_eviction_keep_output_and_ownership(
    monkeypatch, cache_bytes
):
    units = [f"[Guide {i}](https://example.com/{i})\n\n" for i in range(6)]
    source = "".join(units * 2)
    expected = convert_markdown_to_line_messages(source, max_length=len(units[0]))
    calls = _record_renders(monkeypatch)
    monkeypatch.setattr(converter._RenderSession, "_MAX_CACHED_BYTES", cache_bytes)
    actual = convert_markdown_to_line_messages(source, max_length=len(units[0]))
    assert actual == expected
    assert calls[units[0]] > 1
    actual[0]["contents"]["body"]["contents"].clear()
    assert actual[6] == expected[6]


@pytest.mark.parametrize("prefix", ["item", "字🙂"])
def test_splitting_bounds_retained_source_keys_and_entry_count(monkeypatch, prefix):
    observations = []

    class ObservedSession(converter._RenderSession):
        _MAX_CACHED_BYTES = 24_000
        _MAX_CACHED_ENTRIES = 32

        def _render(self, text):
            result = super()._render(text)
            observations.append(
                (sum(getsizeof(key) for key in self.entries), len(self.entries))
            )
            return result

    monkeypatch.setattr(converter, "_RenderSession", ObservedSession)
    source = "".join(f"{prefix}{index:04x}" for index in range(1200))
    parts = split_long_text(source, max_length=200_000, max_payload_bytes=700)
    assert "".join(parts) == source
    assert len(observations) > 100
    assert max(size for size, _ in observations) <= 24_000
    assert max(count for _, count in observations) <= 32
    assert all(converter.estimate_flex_payload_size(part) <= 700 for part in parts)


def test_size_larger_than_cache_capacity_is_returned_without_retention(monkeypatch):
    monkeypatch.setattr(converter._RenderSession, "_MAX_CACHED_BYTES", 100)
    source = "large source " * 100
    session = converter._RenderSession()
    assert session.size(source) == converter.estimate_flex_payload_size(source)
    assert not session.entries
    assert session.cached_bytes == 0


def test_oversized_layout_retains_only_a_bounded_source_and_size(monkeypatch):
    monkeypatch.setattr(converter._RenderSession, "_MAX_CACHED_ENTRIES", 2)
    session = converter._RenderSession()
    for index in range(5):
        source = f"{index}" + "word " * 7000
        assert session.size(source) > 30_000
        assert session.entries[source].bubble is None
        assert len(session.entries) <= 2
    assert len(session.entries) == 2
