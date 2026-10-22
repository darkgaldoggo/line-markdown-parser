# API specification

`line-markdown-parser` converts Markdown strings into LINE Flex Message dictionaries without runtime dependencies or network requests. This document describes the current source tree; see the changelog for released versions.

## Functions

All functions are exported from `line_markdown_parser`. Names beginning with `_` are implementation details.

```python
convert_markdown_to_line_messages(
    text,
    *,
    alt_text=None,
    max_length=1600,
    max_payload_bytes=28000,
) -> list[dict]

build_flex_message(text, *, alt_text=None) -> dict
build_flex_contents(text) -> list[dict]
split_long_text(text, max_length=1600, max_payload_bytes=28000) -> list[str]
estimate_flex_payload_size(text) -> int
```

| Function | Behavior |
| --- | --- |
| `convert_markdown_to_line_messages` | Split and render every chunk in input order. Each item contains `type: "flex"`, `altText`, and one bubble in `contents`. Return `[]` for empty or whitespace-only input when other arguments are valid. |
| `build_flex_message` | Render one message without splitting. Empty or whitespace-only input, or a bubble exceeding 30,000 bytes, raises `ValueError`. |
| `build_flex_contents` | Return the body component list without a bubble or message wrapper. Empty or whitespace-only input returns `[]`. No splitting or bubble size check; the caller must validate the custom bubble. |
| `split_long_text` | Return Markdown chunks within both source-length and rendered-byte limits. Empty or whitespace-only input returns `[]` after argument validation. |
| `estimate_flex_payload_size` | Return the rendered bubble's compact UTF-8 JSON size, including for empty input. |

Every call returns fresh mutable dictionaries; modifying one message does not affect other messages or later calls. Candidate layouts may be reused within a call, but input and output are not cached across calls. Visual properties and exact component nesting may change without changing this contract.

## Limits and splitting

- `max_length` is a positive integer measured in Python string characters. It is a source-length limit, not a LINE API character limit.
- `max_payload_bytes` is an integer from 1 to 30,000. Its default is 28,000, below LINE's [30 KB bubble limit](https://developers.line.biz/en/reference/messaging-api/#flex-message).
- Booleans, invalid limit values, or budgets too small for a rendered fragment raise `ValueError`. No oversized fragment is returned.

The byte budget and size estimator use the bubble's compact JSON with non-ASCII characters encoded directly as UTF-8. They exclude the Flex wrapper, alternative text, recipients, other messages, and HTTP headers. Layout components add overhead, so source length alone does not predict rendered size.

Splitting prefers paragraph, line, and word boundaries. Closed triple-backtick code fences are repeated around each fragment, even when splitting a single code line. Other inline formatting may become ordinary text across a split; arbitrary nesting and all fence styles are not preserved.

Outside fenced code, recognized URLs and Markdown links remain intact. A link that cannot fit either limit raises `ValueError` instead of producing a partial link. URLs inside fenced code may split as ordinary code text.

## Alternative text and input validation

`alt_text` supplies notification and chat-list text. When omitted, each message uses its source chunk. Explicit alternative text is reused for every message. Surrounding whitespace is removed; an empty result raises `ValueError`.

Alternative text is limited to 1,500 UTF-16 code units. Supplementary Unicode characters count as two units. Truncation includes an ellipsis within that limit and preserves whole Unicode characters.

All text arguments must be strings; other types raise `TypeError`. Every public function rejects text exceeding 200,000 UTF-8 bytes with `ValueError`. This also applies to explicit `alt_text` before truncation. Lone surrogate code points raise `ValueError`.

## Markdown rendering

| Input | Output |
| --- | --- |
| Headings and paragraphs | Text with spacing and visual hierarchy. |
| Emphasis and inline code | Styled text components or spans. |
| Unordered and ordered lists | List text and indentation. |
| Quotes | Visually separated text. |
| Horizontal rules | Divider text. |
| Fenced code and tables | Code-style text boxes; no syntax highlighting or interactive tables. |
| Links | Labels and supported URI actions. |
| Images | Labels and links; no fetching or image components. |

Paragraphs, headings, quotes, list items, and emoji-leading lines share inline parsing. For example, `# [Guide](https://example.com)` produces a heading with a URI action. Links occupy separate text components so each destination is clickable. Link labels retain the `🔗 ` prefix and are shortened to 40 characters; the action keeps the full destination.

Full CommonMark conformance, HTML rendering, arbitrary nesting, and exact browser-style layout are outside the scope. Malformed input or unusual fences may render as ordinary text or lose formatting. Table alignment depends on client fonts and display width.

Only `http` and `https` receive [URI actions](https://developers.line.biz/en/reference/messaging-api/#uri-action). Unsupported schemes retain their labels without an action. Malformed HTTP(S) destinations and URLs exceeding the action URI length limit remain text. Existing percent escapes and URL delimiters are preserved when encoding destinations. Destinations are not verified. Lowercase `http://` and `https://` with ASCII hostnames are supported; uppercase schemes, IPv6 hosts, and title-bearing links such as `[Guide](https://example.com "title")` are outside the supported subset.

## Integration

The converter returns all messages without sending or truncating them. LINE [reply](https://developers.line.biz/en/reference/messaging-api/#send-reply-message) and [push](https://developers.line.biz/en/reference/messaging-api/#send-push-message) requests accept at most five messages. Applications handle batching, reply-token restrictions, authentication, recipients, and retries.

Validate integrations using the [Flex Message Simulator](https://developers.line.biz/flex-simulator/), [message validation endpoints](https://developers.line.biz/en/reference/messaging-api/#message-objects), and target LINE clients.
