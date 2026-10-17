# Behavior specification

This document defines the public contract for the initial 0.1.0 release of `line-markdown-parser`.

## Scope

The library converts a Markdown string into ordinary Python dictionaries that describe LINE Flex Messages. Each message contains one bubble. It has no runtime dependencies, performs no network requests, and reads no credentials or application configuration.

The goal is readable conversational output. Full CommonMark conformance, HTML rendering, syntax highlighting, image downloading, and exact reproduction of a browser's Markdown layout are outside the scope.

## Public functions

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

These names are exported from `line_markdown_parser`. Modules and names beginning with `_` are implementation details.

### Message conversion

`convert_markdown_to_line_messages` splits the input and renders each resulting chunk as a separate Flex Message. The order follows the input. It returns all generated messages; it does not impose a five-message limit or discard later chunks. Empty or whitespace-only input produces an empty list when the other arguments are valid.

Each message has the following shape:

```json
{
  "type": "flex",
  "altText": "Alternative text",
  "contents": {
    "type": "bubble",
    "body": {
      "type": "box",
      "layout": "vertical",
      "contents": []
    }
  }
}
```

The example illustrates the object hierarchy only; real messages have nonempty rendered body components. Visual properties and exact component nesting may change without changing this API contract.

### Single-bubble construction

`build_flex_message` returns a Flex Message wrapper, alternative text, and one bubble. It does not split input. Empty or whitespace-only content and a bubble exceeding 30,000 compact UTF-8 JSON bytes raise `ValueError`. Use the main converter for long output.

`build_flex_contents` is a lower-level function that returns the body component list, not a bubble or message wrapper. It does not split input or enforce the bubble size limit. Empty or whitespace-only input returns `[]`. The caller must create a valid surrounding bubble and check its final size when using these components in a custom layout.

### Splitting and size estimation

`split_long_text` returns Markdown chunks and prefers paragraph, line, and word boundaries where possible. Each returned chunk fits `max_length`, measured in Python string characters, and the rendered byte budget. This source-length setting is not a LINE request limit. Closed triple-backtick code fences are repeated around their split code fragments, including when a single code line needs splitting. Other inline formatting may become ordinary text at a split. Full preservation of arbitrary nested Markdown and all code-fence forms is not guaranteed.

Outside fenced code, recognized URLs and Markdown links are kept intact across chunk boundaries. A link that cannot fit as a whole within `max_length` or `max_payload_bytes` causes `ValueError`, even if the surrounding text could fit. The splitter does not manufacture a shorter clickable URL from a partial destination. URLs inside fenced code are ordinary code text and may be split with that code.

`max_length` must be a positive integer. `max_payload_bytes` must be an integer from 1 through 30,000. Booleans are not valid limit values. Invalid values, or budgets too small to hold a rendered fragment, raise `ValueError`; the function does not return an oversized fragment. Empty or whitespace-only input returns `[]` after argument validation.

`max_payload_bytes` limits the compact UTF-8 JSON representation of the rendered bubble. `estimate_flex_payload_size(text)` measures this same representation. It does not count the `type: "flex"` wrapper, alternative text, recipient data, other messages, or HTTP headers. Non-ASCII text is measured as UTF-8 bytes, not as escaped ASCII sequences.

The default budget is 28,000 bytes, below LINE's documented 30 KB bubble limit. A small source string can still produce a large bubble because each text span and layout component adds JSON overhead. Use the rendered-size estimate when assessing output. LINE's size limits are defined in the [Flex Message API reference](https://developers.line.biz/en/reference/messaging-api/#flex-message).

### Alternative text

`alt_text` overrides notification and chat-list text. When omitted, alternative text uses the source text of each message chunk. Explicit alternative text is reused for every generated message. Surrounding whitespace is removed; empty or whitespace-only alternative text raises `ValueError`. The result is bounded to 1,500 UTF-16 code units; supplementary Unicode characters count as two units. Truncation includes an ellipsis within the bound and does not leave half of a supplementary character. This bound applies to alternative text, not to the Markdown source or rendered body.

### Input validation

Text arguments must be strings. Other types raise `TypeError`. Every public function rejects text larger than 200,000 bytes when encoded as UTF-8 with `ValueError`. The same input bound applies to explicit `alt_text` before its display-length truncation. Lone surrogate code points raise `ValueError` because the generated JSON must be valid UTF-8.

## Markdown handling

| Input | Rendering approach |
| --- | --- |
| Headings and paragraphs | Text components with spacing and visual hierarchy. |
| Common emphasis and inline code | Styled text components or spans where supported. |
| Unordered and ordered lists | Readable list text and indentation. |
| Quotes | Visually separated quoted text. |
| Horizontal rules | Flex separators. |
| Fenced code | Code-style text boxes, without executing code. |
| Markdown tables | Code-style text boxes; no interactive table component. |
| Markdown links | Link labels and supported URI actions. |
| Markdown images | Labels and links; no remote image retrieval or image component. |

This is a best-effort renderer, not a complete Markdown grammar. Malformed input, deeply nested structures, and unusual fence lengths may render as ordinary text or lose some formatting. Table alignment is affected by the recipient's font and display width. Rendering must never be interpreted as executing Markdown, HTML, or code.

The library emits URI actions for `http` and `https` only. Unsupported Markdown link schemes keep their label without an action. Malformed HTTP(S) destinations and URLs exceeding the action URI length limit remain text. URI rendering does not perform destination checks. Applications that accept untrusted content should apply their own destination policy before displaying clickable links. LINE's action contract is described in the [URI action reference](https://developers.line.biz/en/reference/messaging-api/#uri-action).

## Delivery responsibility

The return value is message data, not a request that has been sent. The caller owns authentication, recipients, reply-token usage, request batching, retry behavior, rate limits, costs, and logging.

LINE reply and push requests allow up to five message objects. A conversion can produce more. The library leaves the delivery decision to the caller and does not truncate the returned list. Do not assume that a reply token permits multiple successive reply requests. Refer to the official [reply](https://developers.line.biz/en/reference/messaging-api/#send-reply-message) and [push](https://developers.line.biz/en/reference/messaging-api/#send-push-message) documentation when choosing a strategy.

## Validation boundary

The initial release uses automated tests to check generated objects, text handling, and size behavior. Live LINE API delivery and rendering on actual LINE clients have not been verified for this release. A passing test suite does not establish recipient-visible appearance or API acceptance in every environment.

Integration validation can use the [Flex Message Simulator](https://developers.line.biz/flex-simulator/) and LINE's [message validation endpoints](https://developers.line.biz/en/reference/messaging-api/#message-objects). Visual checks should cover the clients supported by the application. LINE documents environment-dependent rendering in its [Flex Message guide](https://developers.line.biz/en/docs/messaging-api/using-flex-messages/).
