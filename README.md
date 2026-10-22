# line-markdown-parser

Convert LLM Markdown into readable LINE Flex Message dictionaries with no runtime dependencies.

[日本語](https://github.com/darkgaldoggo/line-markdown-parser/blob/main/README-ja.md)

The library builds on conversion logic refined through ongoing use in a LINE bot.

Headings, paragraphs, lists, quotes, code, and links receive a chat-friendly layout. Long output is split into separate messages. Sending remains the responsibility of your application.

## Installation

Requires Python 3.10 or later.

```bash
python -m pip install line-markdown-parser
```

## Quick start

```python
import json

from line_markdown_parser import convert_markdown_to_line_messages

markdown = """# Project update

The **first draft** is ready.

- Review the examples
- Read the [guide](https://example.com/guide)
"""

messages = convert_markdown_to_line_messages(markdown)
print(json.dumps(messages, ensure_ascii=False, indent=2))
```

Each item has `type: "flex"`, `altText`, and one `bubble` in `contents`. Pass these dictionaries to your LINE API integration. The library makes no network requests and does not require the LINE SDK.

The converter returns all generated messages. LINE accepts up to five message objects per [reply](https://developers.line.biz/en/reference/messaging-api/#send-reply-message) or [push](https://developers.line.biz/en/reference/messaging-api/#send-push-message) request, so your application must handle longer results and reply-token restrictions.

## API

All functions are exported from `line_markdown_parser`.

| Function | Purpose |
| --- | --- |
| `convert_markdown_to_line_messages` | Split Markdown and return a `list[dict]` of Flex Messages. |
| `build_flex_message` | Build one message without splitting; reject oversized input. |
| `build_flex_contents` | Build body components for a custom bubble, without a bubble size check. |
| `split_long_text` | Return Markdown chunks as a `list[str]`. |
| `estimate_flex_payload_size` | Measure the rendered bubble's compact UTF-8 JSON size. |

The converter defaults to 1,600 source characters and 28,000 rendered bytes per chunk. See the [API specification](https://github.com/darkgaldoggo/line-markdown-parser/blob/main/docs/spec.md) for signatures, limits, alternative text, and error behavior.

## Limitations

- Markdown tables use code-style text boxes; column alignment varies by client font.
- Images appear as labels and links, without fetching or embedding images.
- Only `http` and `https` links receive URI actions; destinations are not verified.
- Full CommonMark support, arbitrary nesting, and every code-fence style are outside the scope.
- When integrating, check the output with the [Flex Message Simulator](https://developers.line.biz/flex-simulator/) and your target LINE clients.

## Contributing

See [CONTRIBUTING.md](https://github.com/darkgaldoggo/line-markdown-parser/blob/main/CONTRIBUTING.md) for setup and checks, [SECURITY.md](https://github.com/darkgaldoggo/line-markdown-parser/blob/main/SECURITY.md) for vulnerability reporting, and [CHANGELOG.md](https://github.com/darkgaldoggo/line-markdown-parser/blob/main/CHANGELOG.md) for release history.

## License

[MIT](https://github.com/darkgaldoggo/line-markdown-parser/blob/main/LICENSE). This independent project is not an official LINE product.
