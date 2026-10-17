"""Check public Git files and distributions against allowlists and content rules.

This is a conservative allowlist and pattern check, not a guarantee that every
secret or private fact is detected. It does not inspect Git history. Findings
contain only filenames, rule names, and line numbers; matched text is not printed.
Archives are inspected in memory and are never extracted.
"""

from __future__ import annotations

import argparse
import ipaddress
import re
import stat
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

MAX_FILE_BYTES = 2_000_000
MAX_ARCHIVE_BYTES = 20_000_000

TRACKED_FILES = frozenset(
    {
        "pyproject.toml",
        "MANIFEST.in",
        "_build_backend.py",
        ".gitignore",
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
        ".github/dependabot.yml",
        "README.md",
        "README-ja.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "SECURITY.md",
        "docs/spec.md",
        "scripts/check_public_artifacts.py",
    }
)
PACKAGE_FILES = frozenset(
    f"line_markdown_parser/{name}"
    for name in ("__init__.py", "_renderer.py", "converter.py", "py.typed")
)
SDIST_FILES = frozenset(
    {
        "README.md",
        "README-ja.md",
        "LICENSE",
        "CHANGELOG.md",
        "docs/spec.md",
        "pyproject.toml",
        "MANIFEST.in",
        "_build_backend.py",
        "PKG-INFO",
        "setup.cfg",
    }
)
EGG_INFO_FILES = frozenset(
    {
        "PKG-INFO",
        "SOURCES.txt",
        "dependency_links.txt",
        "entry_points.txt",
        "requires.txt",
        "top_level.txt",
        "not-zip-safe",
        "zip-safe",
    }
)
DIST_INFO_FILES = frozenset(
    {
        "METADATA",
        "WHEEL",
        "RECORD",
        "entry_points.txt",
        "top_level.txt",
        "LICENSE",
        "licenses/LICENSE",
    }
)

# Each expression describes a shape, without embedding a real identifier.
CONTENT_RULES = (
    (
        "private-key",
        re.compile(
            r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"
        ),
    ),
    (
        "github-token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    ),
    ("api-secret-key", re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}\b")),
    ("slack-token", re.compile(r"\b(?:xox[baprs]|xapp)-[A-Za-z0-9-]{15,}\b")),
    ("google-api-key", re.compile(r"\bAIza[A-Za-z0-9_-]{35}\b")),
    ("google-oauth-token", re.compile(r"\bya29\.[A-Za-z0-9_-]{20,}\b")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    (
        "jwt-token",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
        ),
    ),
    ("line-identifier", re.compile(r"\b[UCR][a-fA-F0-9]{32}\b")),
    (
        "slack-identifier",
        re.compile(r"\b[TCGD](?=[A-Z0-9]{8,20}\b)(?=[A-Z0-9]*[0-9])[A-Z0-9]{8,20}\b"),
    ),
    (
        "literal-secret",
        re.compile(
            r"(?i)\b(?:[a-z][a-z0-9_]*_)?"
            r"(?:api[_-]?key|secret[_-]?key|access[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|token|secret|password)"
            r"[\"']?\s*[=:]\s*[\"'][A-Za-z0-9_./+=-]{12,}[\"']"
        ),
    ),
    (
        "absolute-posix-path",
        re.compile(
            r"(?<![A-Za-z0-9_:/.-])/(?:Users|home|root|opt|private|data|mnt|media|srv|Volumes)/"
            r"[A-Za-z0-9_.-]+(?:/[^\s\"'<>()\[\]{},;]*)?"
        ),
    ),
    (
        "absolute-windows-path",
        re.compile(r"\b[A-Za-z]:[\\/](?:[^\s\"'<>:]+[\\/])*[^\s\"'<>:]+"),
    ),
)
EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}\b"
)
URL_PATTERN = re.compile(r"\bhttps?://[^\s<>\"'`]+")
FILE_URL_PATTERN = re.compile("file:" + r"//[^\s<>\"'`]+", re.IGNORECASE)
# One published regression uses this deliberately fictitious attachment URI.
SYNTHETIC_FILE_URLS = frozenset({"file:" + "///tmp/example.txt"})
DOCUMENTATION_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "2001:db8::/32")
)


@dataclass(frozen=True, order=True)
class Finding:
    filename: str
    line: int
    rule: str


def _valid_relative_path(name: str) -> bool:
    if not name or "\\" in name or any(ord(char) < 32 for char in name):
        return False
    parts = name.split("/")
    return all(part not in {"", ".", ".."} for part in parts)


def allowed_tracked_file(name: str) -> bool:
    if not _valid_relative_path(name):
        return False
    if name in TRACKED_FILES or name in PACKAGE_FILES:
        return True
    return bool(
        re.fullmatch(r"tests/[A-Za-z0-9_][A-Za-z0-9_.-]*\.py", name)
        or re.fullmatch(r"examples/[A-Za-z0-9_][A-Za-z0-9_.-]*\.(?:py|md)", name)
    )


def allowed_distribution_file(name: str, kind: str) -> bool:
    if not _valid_relative_path(name):
        return False
    if name in PACKAGE_FILES:
        return True
    parts = PurePosixPath(name).parts
    if kind == "sdist":
        if name in SDIST_FILES:
            return True
        return (
            len(parts) == 2
            and parts[0] == "line_markdown_parser.egg-info"
            and parts[1] in EGG_INFO_FILES
        )
    if kind == "wheel" and len(parts) >= 2:
        return bool(
            re.fullmatch(r"line_markdown_parser-[A-Za-z0-9.+!-]+\.dist-info", parts[0])
            and "/".join(parts[1:]) in DIST_INFO_FILES
        )
    return False


def _allowed_distribution_directory(name: str, kind: str) -> bool:
    if not _valid_relative_path(name):
        return False
    if name == "line_markdown_parser":
        return True
    if kind == "sdist":
        return name in {"docs", "line_markdown_parser.egg-info"}
    return bool(
        re.fullmatch(
            r"line_markdown_parser-[A-Za-z0-9.+!-]+\.dist-info(?:/licenses)?", name
        )
    )


def _reserved_email(address: str) -> bool:
    domain = address.rsplit("@", 1)[1].lower()
    return domain in {"example.com", "example.org", "example.net"} or domain.endswith(
        (
            ".example.com",
            ".example.org",
            ".example.net",
            ".example",
            ".invalid",
            ".test",
        )
    )


def scan_content(filename: str, content: bytes) -> list[Finding]:
    if len(content) > MAX_FILE_BYTES:
        return [Finding(filename, 0, "file-too-large")]
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return [Finding(filename, 0, "non-utf8-content")]
    if "\x00" in text:
        return [Finding(filename, 0, "binary-content")]

    findings = set()
    for number, line in enumerate(text.splitlines(), 1):
        for rule, pattern in CONTENT_RULES:
            if pattern.search(line):
                findings.add(Finding(filename, number, rule))
        if any(
            not _reserved_email(match.group()) for match in EMAIL_PATTERN.finditer(line)
        ):
            findings.add(Finding(filename, number, "non-example-email"))
        for match in FILE_URL_PATTERN.finditer(line):
            if match.group() not in SYNTHETIC_FILE_URLS:
                findings.add(Finding(filename, number, "local-file-url"))
        for match in URL_PATTERN.finditer(line):
            try:
                hostname = urlsplit(match.group()).hostname
            except ValueError:
                continue
            if not hostname:
                continue
            if hostname.lower() == "localhost" or hostname.lower().endswith(
                (".localhost", ".local", ".internal")
            ):
                findings.add(Finding(filename, number, "internal-host-url"))
                continue
            try:
                address = ipaddress.ip_address(hostname)
            except ValueError:
                continue
            if any(
                address.version == network.version and address in network
                for network in DOCUMENTATION_NETWORKS
            ):
                continue
            if not address.is_global:
                findings.add(Finding(filename, number, "private-ip-url"))
    return sorted(findings)


def _git(root: Path, *arguments: str) -> bytes:
    return subprocess.run(
        ["git", *arguments], cwd=root, check=True, capture_output=True
    ).stdout


def check_tracked_files(root: Path) -> list[Finding]:
    """Inspect both current files and staged blobs, including staged-only secrets."""
    findings = set()
    records = _git(root, "ls-files", "--stage", "-z").split(b"\x00")
    if not any(records):
        return [Finding("<git-index>", 0, "no-tracked-files")]
    for record in records:
        if not record:
            continue
        metadata, raw_name = record.split(b"\t", 1)
        mode, object_id, stage = metadata.decode("ascii").split()
        name = raw_name.decode("utf-8", errors="replace")
        if not allowed_tracked_file(name):
            findings.add(Finding(name, 0, "unapproved-tracked-path"))
            continue
        if mode not in {"100644", "100755"} or stage != "0":
            findings.add(Finding(name, 0, "non-regular-or-unmerged-index-entry"))
            continue
        file = root / name
        try:
            if file.is_symlink() or not file.is_file():
                findings.add(Finding(name, 0, "non-regular-working-file"))
            elif file.stat().st_size > MAX_FILE_BYTES:
                findings.add(Finding(name, 0, "file-too-large"))
            else:
                findings.update(scan_content(name, file.read_bytes()))
        except OSError:
            findings.add(Finding(name, 0, "unreadable-working-file"))
        blob_size = int(_git(root, "cat-file", "-s", object_id))
        if blob_size > MAX_FILE_BYTES:
            findings.add(Finding(name, 0, "index-file-too-large"))
        else:
            findings.update(
                scan_content(name, _git(root, "cat-file", "blob", object_id))
            )
    return sorted(findings)


def _archive_member_name(raw_name: str, kind: str) -> str | None:
    if not _valid_relative_path(raw_name):
        return None
    if kind == "wheel":
        return raw_name
    parts = raw_name.split("/")
    if not re.fullmatch(r"line[-_]markdown[-_]parser-[A-Za-z0-9.+!-]+", parts[0]):
        return None
    return "/".join(parts[1:])


def check_wheel(path: Path) -> list[Finding]:
    findings = []
    total = 0
    seen = set()
    with zipfile.ZipFile(path) as archive:
        if archive.comment:
            findings.append(Finding(path.name, 0, "archive-comment"))
        for member in archive.infolist():
            raw_name = (
                member.filename.rstrip("/") if member.is_dir() else member.filename
            )
            label = f"{path.name}!{raw_name}"
            name = _archive_member_name(raw_name, "wheel")
            if name is None or name in seen:
                findings.append(Finding(label, 0, "invalid-or-duplicate-archive-path"))
                continue
            seen.add(name)
            if member.comment:
                findings.append(Finding(label, 0, "archive-comment"))
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                findings.append(Finding(label, 0, "archive-link"))
                continue
            if stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}:
                findings.append(Finding(label, 0, "non-regular-archive-entry"))
                continue
            if member.is_dir():
                if not _allowed_distribution_directory(name, "wheel"):
                    findings.append(Finding(label, 0, "unapproved-archive-path"))
                continue
            if not allowed_distribution_file(name, "wheel"):
                findings.append(Finding(label, 0, "unapproved-archive-path"))
                continue
            total += member.file_size
            if member.file_size > MAX_FILE_BYTES or total > MAX_ARCHIVE_BYTES:
                findings.append(Finding(label, 0, "archive-size-limit"))
                continue
            findings.extend(scan_content(label, archive.read(member)))
    if not seen and not findings:
        findings.append(Finding(path.name, 0, "empty-distribution"))
    return findings


def check_sdist(path: Path) -> list[Finding]:
    findings = []
    total = 0
    seen = set()
    roots = set()
    with tarfile.open(path, "r:gz") as archive:
        if set(archive.pax_headers) - {"mtime"}:
            findings.append(Finding(path.name, 0, "unapproved-archive-metadata"))
        for member in archive:
            raw_name = member.name.rstrip("/") if member.isdir() else member.name
            label = f"{path.name}!{raw_name}"
            name = _archive_member_name(raw_name, "sdist")
            if name is None or raw_name in seen:
                findings.append(Finding(label, 0, "invalid-or-duplicate-archive-path"))
                continue
            seen.add(raw_name)
            roots.add(raw_name.split("/")[0])
            if len(roots) > 1:
                findings.append(Finding(label, 0, "multiple-sdist-roots"))
                continue
            if (
                member.uid != 0
                or member.gid != 0
                or member.uname not in {"", "root"}
                or member.gname not in {"", "root"}
            ):
                findings.append(Finding(label, 0, "archive-owner-metadata"))
            if set(member.pax_headers) - {"mtime", "path"}:
                findings.append(Finding(label, 0, "unapproved-archive-metadata"))
            if member.isdir():
                if name and not _allowed_distribution_directory(name, "sdist"):
                    findings.append(Finding(label, 0, "unapproved-archive-path"))
                continue
            if not member.isfile():
                findings.append(Finding(label, 0, "non-regular-archive-entry"))
                continue
            if not allowed_distribution_file(name, "sdist"):
                findings.append(Finding(label, 0, "unapproved-archive-path"))
                continue
            total += member.size
            if member.size > MAX_FILE_BYTES or total > MAX_ARCHIVE_BYTES:
                findings.append(Finding(label, 0, "archive-size-limit"))
                continue
            stream = archive.extractfile(member)
            if stream is None:
                findings.append(Finding(label, 0, "unreadable-archive-entry"))
                continue
            with stream:
                findings.extend(scan_content(label, stream.read(MAX_FILE_BYTES + 1)))
    if not seen and not findings:
        findings.append(Finding(path.name, 0, "empty-distribution"))
    return findings


def check_distributions(directory: Path) -> list[Finding]:
    findings = []
    if not directory.is_dir():
        return [Finding("<dist>", 0, "missing-distribution-directory")]
    paths = sorted(directory.iterdir())
    if not paths:
        return [Finding("<dist>", 0, "no-distributions")]
    for path in paths:
        if path.is_symlink() or not path.is_file():
            findings.append(Finding(path.name, 0, "non-regular-distribution"))
            continue
        try:
            if re.fullmatch(r"line_markdown_parser-[A-Za-z0-9.+!-]+\.whl", path.name):
                findings.extend(check_wheel(path))
            elif re.fullmatch(
                r"line[-_]markdown[-_]parser-[A-Za-z0-9.+!-]+\.tar\.gz", path.name
            ):
                findings.extend(check_sdist(path))
            else:
                findings.append(Finding(path.name, 0, "unexpected-distribution-file"))
        except (
            OSError,
            ValueError,
            RuntimeError,
            EOFError,
            tarfile.TarError,
            zipfile.BadZipFile,
        ):
            findings.append(Finding(path.name, 0, "unreadable-distribution"))
    return sorted(set(findings))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dist",
        type=Path,
        help="Inspect wheel and sdist files in this directory instead of Git files.",
    )
    arguments = parser.parse_args(argv)
    try:
        if arguments.dist is not None:
            findings = check_distributions(arguments.dist)
        else:
            root = Path(
                _git(Path.cwd(), "rev-parse", "--show-toplevel").decode().strip()
            )
            findings = check_tracked_files(root)
    except (OSError, ValueError, subprocess.CalledProcessError):
        print(
            "Unable to inspect public artifacts; verify the Git repository or distribution directory.",
            file=sys.stderr,
        )
        return 2
    if findings:
        for finding in findings:
            # ascii() escapes terminal control characters in untrusted filenames.
            print(
                f"{ascii(finding.filename)}:{finding.line}: {finding.rule}",
                file=sys.stderr,
            )
        print(
            f"Public artifact check failed: {len(findings)} finding(s).",
            file=sys.stderr,
        )
        return 1
    print("Public artifact allowlist and content checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
