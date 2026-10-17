# Changelog

## 0.1.0 — 2026-10-18

- Initial dependency-free Python library for converting Markdown into LINE Flex Message dictionaries.
- Readable rendering for common headings, paragraphs, emphasis, lists, quotes, separators, fenced code, links, and code-style tables.
- Long-output splitting with a rendered bubble JSON byte budget.
- Intact-link splitting and a 200,000-byte UTF-8 input limit.
- Alternative text bounded by UTF-16 code units.
- Public APIs for complete messages, body components, text splitting, and rendered-size estimation.
- Automated conversion tests and package checks. Live LINE delivery and client rendering have not been verified for this release.
- GitHub Release automation for wheel and source distribution assets. PyPI publication is not configured.
- Public-file and distribution allowlists, private-content checks, and anonymous source-archive ownership metadata.
