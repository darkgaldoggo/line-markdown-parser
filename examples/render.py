"""Print a synthetic Flex payload; no credentials, network, or delivery needed."""

import json

from line_markdown_parser import convert_markdown_to_line_messages

MARKDOWN = """# Weekly update

**Search** is ready; *navigation* is in progress.

- [x] Add keyboard shortcuts
- [ ] Review accessibility
  - Check screen-reader labels

> Try the new workflow and share feedback.

```python
def greet(name):
    return f"Hello, {name}!"
```

| Feature | Status |
| --- | --- |
| Search | Ready |
| Navigation | In progress |

[Documentation](https://example.com/docs)
"""

if __name__ == "__main__":
    print(
        json.dumps(
            convert_markdown_to_line_messages(MARKDOWN), ensure_ascii=False, indent=2
        )
    )
