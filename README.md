# line-markdown-parser

Convert Markdown from LLMs into readable LINE Flex Message dictionaries, with no runtime dependencies.

[日本語](README-ja.md)

The library turns headings, paragraphs, lists, quotes, and code into a compact chat layout. It splits long output into separate messages and keeps sending, credentials, and delivery policy in your application.

## Installation

Requires Python 3.10 or later. Version 0.1.0 is not yet published on PyPI.

Install from a local checkout:

```bash
python -m pip install .
```

Install the versioned release directly from GitHub:

```bash
python -m pip install 'line-markdown-parser @ git+https://github.com/darkgaldragon/line-markdown-parser.git@v0.1.0'
```

## Quick start

```python
import json

from line_markdown_parser import convert_markdown_to_line_messages

markdown = """# Project update

The **first draft** is ready.

- Review the examples
- Read the [guide](https://example.com/guide)

| Item | Status |
| --- | --- |
| Documentation | Ready |
| Examples | In progress |
"""

messages = convert_markdown_to_line_messages(markdown)
print(json.dumps(messages, ensure_ascii=False, indent=2))
```

Each returned item is a message object with `type: "flex"`, `altText`, and one `bubble` in `contents`. Pass these dictionaries to your application's LINE API integration. This package makes no network requests and does not require the LINE SDK.

LINE reply and push requests accept up to five message objects. The converter returns every generated message, including when there are more than five. Your application must choose an appropriate delivery strategy; it must not silently send only `messages[:5]`. Reply tokens cannot be treated as a general mechanism for sending successive batches. See the [reply](https://developers.line.biz/en/reference/messaging-api/#send-reply-message) and [push](https://developers.line.biz/en/reference/messaging-api/#send-push-message) API references.

## Public API

All five functions are available from `line_markdown_parser`.

| Function | Result |
| --- | --- |
| `convert_markdown_to_line_messages(text, *, alt_text=None, max_length=1600, max_payload_bytes=28000)` | A `list[dict]` of separate Flex Messages, split to fit the configured limits. |
| `build_flex_message(text, *, alt_text=None)` | One Flex Message dictionary, without automatic splitting. Oversized input raises `ValueError`. |
| `build_flex_contents(text)` | A `list[dict]` of body components for a custom bubble; no splitting or bubble size check. |
| `split_long_text(text, max_length=1600, max_payload_bytes=28000)` | A `list[str]` of Markdown chunks for rendering. |
| `estimate_flex_payload_size(text)` | The generated bubble's compact JSON size in UTF-8 bytes. |

The main converter, `split_long_text`, and `build_flex_contents` return `[]` for empty or whitespace-only input. `build_flex_message` requires nonempty content. `alt_text` provides notification and chat-list text; it is shortened to at most 1,500 UTF-16 code units without cutting a Unicode character in half. If omitted, each message uses its source chunk as alternative text. An explicit alternative text must be nonempty and is reused for every generated message.

`max_length` limits each source chunk's length in Python characters; it is not a LINE API character limit. `max_payload_bytes` measures the bubble's compact JSON, not the entire HTTP request. The default 28,000-byte budget leaves room below LINE's documented 30 KB bubble limit. The single-message builder enforces a 30,000-byte bubble limit. An invalid or impossible split budget raises `ValueError`. See [Flex Message reference](https://developers.line.biz/en/reference/messaging-api/#flex-message).

All public functions reject text inputs larger than 200,000 UTF-8 bytes with `ValueError`. Outside fenced code, splitting keeps recognized URLs and Markdown links intact. If one link cannot fit the configured source-length or rendered-byte limit, conversion raises `ValueError` instead of creating a partial link. Increase the limits within the supported range or shorten the link at the application level.

## Rendering and scope

- Common Markdown constructs receive a readable Flex layout, including headings, lists, emphasis, quotes, separators, and fenced code.
- Markdown tables appear in a code-style text box. They are not native interactive tables, and exact column alignment depends on the client font.
- Markdown images appear as labels and links. The library does not fetch or embed remote images.
- URI actions use `http` and `https`. Other Markdown link schemes retain their label without a URI action. Rendering a link does not verify or endorse its destination.
- Splitting aims to retain readable boundaries. Full CommonMark fidelity, arbitrary nesting, and every fence style are outside the initial scope.
- No sending, credentials, SDK objects, conversation state, deployment configuration, or LLM API calls are included.

See [the behavior specification](docs/spec.md) for the API contract and limitations.

## Validation status

The initial release is validated with automated tests for conversion and size handling. Real LINE API delivery and visual checks on LINE clients have not been performed for this release. The same Flex Message can render differently across devices; use the [Flex Message Simulator](https://developers.line.biz/flex-simulator/) and your target clients when integrating it. See LINE's [Flex Message guide](https://developers.line.biz/en/docs/messaging-api/using-flex-messages/) for client behavior.

## Development

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python scripts/check_public_artifacts.py
python -m build
python -m twine check dist/*
python scripts/check_public_artifacts.py --dist dist
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution, publication checks, and release policy, and [CHANGELOG.md](CHANGELOG.md) for version history.

## License

[MIT](LICENSE). This is an independent project and is not an official LINE product.
