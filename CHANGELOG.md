# Changelog

## 0.1.1 — 2026-10-18

- Avoid excessive parsing time for unfinished links and emphasis.
- Preserve inline code, brackets in link labels, punctuation-only text, and URL delimiters; reject malformed action URLs.
- Improve internal-URL checks, archive error reporting, and source-distribution file permissions.
- Clarify alpha status and simplify usage and contribution guides.

## 0.1.0 — 2026-10-18

- Initial dependency-free Python library for converting Markdown into LINE Flex Message dictionaries.
- Support for headings, paragraphs, emphasis, lists, quotes, separators, fenced code, links, and code-style tables.
- Long-output splitting by source length and rendered bubble size, preserving recognized links.
- UTF-16-bounded alternative text and a 200,000-byte UTF-8 input limit.
- APIs for complete messages, body components, text splitting, and rendered-size estimation.
