# Security and privacy

The library creates dictionaries in memory. It does not send messages, fetch
URLs, read credentials, log input, or retain message contents in a shared cache.
Links in output are still untrusted input: applications must decide whether the
destination is appropriate for their users.

Do not include access tokens, recipient identifiers, production transcripts,
private URLs, or personal data in public issues, fixtures, logs, screenshots, or
pull requests. Use synthetic examples and reserved example domains.

Report vulnerabilities through the repository's private vulnerability reporting
feature under **Security → Report a vulnerability**. Do not post secrets in a
public issue. If that option is unavailable, request a private reporting channel
without publishing the vulnerability or sensitive material.

Before publishing, review all tracked files and Git history, run a secret
scanner, and inspect the built wheel and source archive. The repository's
allowlist/pattern check is defense in depth, not proof that all private material
has been removed. Ignoring a file does not remove it from existing Git history.

Supported security fixes target the latest release.
