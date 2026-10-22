# Changelog

## 0.1.5 — 2026-10-22

- Avoid repeated suffix scans for unclosed inline HTML emphasis tags.
- Make heading links clickable through shared inline parsing.
- Keep multiline emphasis intact when an inline code span contains delimiter characters.
- Preserve adjacent links and links following multiline inline code; share code-fence body parsing with the splitter.
- Separate syntax, URI policy, and Flex layout; reuse candidate layouts within each conversion.
- Add strict type checking, cross-context and output-structure tests, and installed-wheel contract checks.
- GitHubアカウント名変更に伴いプロジェクトURLを更新（#10）。

## 0.1.4 — 2026-10-18

- Clarify the conversion logic's use in a running LINE bot and integration guidance.

## 0.1.3 — 2026-10-18

- Fix documentation links in the PyPI project description.

## 0.1.2 — 2026-10-18

- Publish distributions to PyPI with Trusted Publishing and update installation instructions.

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
