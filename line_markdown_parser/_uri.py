"""URI policy and escaping, independent of syntax recognition and Flex layout."""

import re
import urllib.parse
from dataclasses import dataclass

from ._syntax import _InlineLink

LINE_ACTION_URI_MAX_LENGTH = 1000


@dataclass(frozen=True)
class LinkTarget:
    text: str
    uri: str | None = None
    parse_label: bool = True


def resolve_link(link: _InlineLink) -> LinkTarget:
    uri = link.url.strip()
    if link.kind == "markdown" and uri.startswith("<") and uri.endswith(">"):
        uri = uri[1:-1].strip()
    if not uri.startswith(("http://", "https://")):
        # Keep the label when possible. An empty label retains the source;
        # this is display fallback, not a mechanism for redacting destinations.
        return LinkTarget(link.label or link.text)
    try:
        parsed = urllib.parse.urlsplit(uri)
        if not parsed.scheme or not parsed.hostname:
            raise ValueError("Missing scheme or hostname")
        if not re.fullmatch(r"[a-zA-Z0-9.\-:]+", parsed.netloc):
            raise ValueError("Unsupported hostname")
        _ = parsed.port
        if re.search(r"%(?![0-9A-Fa-f]{2})", uri):
            raise ValueError("Invalid percent escape")
        # RFC 3986 pchar, preserving existing escapes and empty ?/# components.
        path_safe = "/:@!$&'()*+,;=%"
        sanitized = f"{parsed.scheme}://{parsed.netloc}" + urllib.parse.quote(
            parsed.path, safe=path_safe
        )
        if "?" in uri.partition("#")[0]:
            sanitized += "?" + urllib.parse.quote(parsed.query, safe=path_safe + "?")
        if "#" in uri:
            sanitized += "#" + urllib.parse.quote(parsed.fragment, safe=path_safe + "?")
    except ValueError:
        return LinkTarget(link.text)
    if len(sanitized) > LINE_ACTION_URI_MAX_LENGTH:
        return LinkTarget(link.text)
    if link.kind == "markdown" and link.label and link.label.strip():
        return LinkTarget(link.label.strip(), sanitized)
    return LinkTarget(sanitized, sanitized, parse_label=False)
