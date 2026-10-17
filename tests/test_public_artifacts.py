"""Publication checks exercised with synthetic values, never real credentials."""

import io
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts import check_public_artifacts as checker


@pytest.mark.parametrize(
    "name",
    [
        "README.md",
        "README-ja.md",
        ".github/workflows/release.yml",
        "line_markdown_parser/converter.py",
        "line_markdown_parser/py.typed",
        "tests/test_renderer.py",
        "examples/basic.py",
        "examples/README.md",
        "scripts/check_public_artifacts.py",
    ],
)
def test_approved_source_paths(name):
    assert checker.allowed_tracked_file(name)


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        ".private/report.md",
        "docs/internal.md",
        "terraform.tfstate",
        "line_markdown_parser/settings.json",
        "line_markdown_parser/extra.py",
        "tests/fixture.json",
        "tests/nested/test_example.py",
        "examples/dump.log",
        "scripts/other.py",
        "../README.md",
        "docs//spec.md",
        "docs/./spec.md",
        "docs\\spec.md",
        "README.md\nextra",
    ],
)
def test_unapproved_source_paths(name):
    assert not checker.allowed_tracked_file(name)


@pytest.mark.parametrize(
    "value, rule",
    [
        ("ghp_" + "x" * 36, "github-token"),
        ("github_pat_" + "x" * 60, "github-token"),
        ("sk-" + "x" * 30, "api-secret-key"),
        ("xoxb-" + "1" * 30, "slack-token"),
        ("xapp-" + "1" * 30, "slack-token"),
        ("AIza" + "x" * 35, "google-api-key"),
        ("ya29." + "x" * 40, "google-oauth-token"),
        ("AKIA" + "A" * 16, "aws-access-key"),
        ("eyJ" + "a" * 16 + "." + "b" * 16 + "." + "c" * 16, "jwt-token"),
        ("-----BEGIN " + "PRIVATE KEY-----", "private-key"),
        ("U" + "a" * 32, "line-identifier"),
        ("C" + "b" * 32, "line-identifier"),
        ("R" + "c" * 32, "line-identifier"),
        ("T" + "A1" * 5, "slack-identifier"),
        ("C" + "A1" * 5, "slack-identifier"),
        ("author@" + "mail.unapproved", "non-example-email"),
        ("/" + "Users/example/project", "absolute-posix-path"),
        ("/" + "home/example/project", "absolute-posix-path"),
        ("C:" + "\\Users\\example\\project", "absolute-windows-path"),
        ("file:" + "///home/example/project", "local-file-url"),
        ("https:" + "//10.1.2.3/document", "private-ip-url"),
        ("http:" + "//127.0.0.1:8000/document", "private-ip-url"),
        ("http:" + "//[::1]/document", "private-ip-url"),
        ("http:" + "//localhost:8000/document", "internal-host-url"),
        ("https:" + "//service.internal/document", "internal-host-url"),
        ("api_key = " + '"' + "x" * 30 + '"', "literal-secret"),
        ('"api_key": ' + '"' + "x" * 30 + '"', "literal-secret"),
        ("LINE_CHANNEL_ACCESS_TOKEN = " + '"' + "x" * 40 + '"', "literal-secret"),
    ],
)
def test_private_content_detection_reports_rule_and_line(value, rule):
    findings = checker.scan_content("README.md", f"safe\n{value}\n".encode())

    assert checker.Finding("README.md", 2, rule) in findings
    assert all(not hasattr(finding, "matched_text") for finding in findings)


def test_reserved_examples_and_public_urls_are_allowed():
    content = (
        "reader@example.com reader@docs.example.org reader@mail.invalid\n"
        "https://example.com/path https://192.0.2.1/path\n"
        "https://198.51.100.1/path https://203.0.113.1/path\n"
        "https://[2001:db8::1]/path\n"
        "file:" + "///tmp/example.txt\n"
        "CONTRIBUTING.md line_markdown_parser/converter.py\n"
    )

    assert checker.scan_content("README.md", content.encode()) == []


def test_non_text_and_oversized_files_are_rejected(monkeypatch):
    assert checker.scan_content("README.md", b"\xff")[0].rule == "non-utf8-content"
    assert checker.scan_content("README.md", b"a\x00b")[0].rule == "binary-content"
    monkeypatch.setattr(checker, "MAX_FILE_BYTES", 5)
    assert checker.scan_content("README.md", b"x" * 6)[0].rule == "file-too-large"


def test_checker_and_its_synthetic_tests_pass_content_scan():
    for filename in (Path(checker.__file__), Path(__file__)):
        assert checker.scan_content(filename.name, filename.read_bytes()) == []


@pytest.fixture
def git_repository(tmp_path):
    subprocess.run(
        ["git", "-c", "init.templateDir=", "init", "--quiet"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    return tmp_path


def _stage(root, name, content):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    subprocess.run(
        ["git", "add", "--", name], cwd=root, check=True, capture_output=True
    )


def test_git_scan_rejects_unapproved_tracked_files_but_ignores_untracked(
    git_repository,
):
    root = git_repository
    _stage(root, "README.md", "Public example\n")
    (root / "local-notes.txt").write_text("Local only")
    assert checker.check_tracked_files(root) == []

    _stage(root, ".env", "not a public file")
    assert checker.Finding(
        ".env", 0, "unapproved-tracked-path"
    ) in checker.check_tracked_files(root)


def test_git_scan_catches_staged_secret_after_working_copy_is_cleaned(git_repository):
    root = git_repository
    _stage(root, "README.md", "ghp_" + "x" * 36)
    (root / "README.md").write_text("Sanitized working copy")

    assert checker.Finding(
        "README.md", 1, "github-token"
    ) in checker.check_tracked_files(root)


def test_git_scan_catches_unstaged_secret_in_tracked_file(git_repository):
    root = git_repository
    _stage(root, "README.md", "Safe public text")
    (root / "README.md").write_text("sk-" + "x" * 30)

    assert checker.Finding(
        "README.md", 1, "api-secret-key"
    ) in checker.check_tracked_files(root)


def test_git_scan_rejects_symlinks(git_repository):
    root = git_repository
    (root / "README.md").symlink_to("target.md")
    subprocess.run(
        ["git", "add", "README.md"], cwd=root, check=True, capture_output=True
    )

    assert checker.Finding(
        "README.md", 0, "non-regular-or-unmerged-index-entry"
    ) in checker.check_tracked_files(root)


def test_empty_git_index_is_not_a_success(git_repository):
    assert checker.check_tracked_files(git_repository) == [
        checker.Finding("<git-index>", 0, "no-tracked-files")
    ]


def _wheel(directory, files):
    path = directory / "line_markdown_parser-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return path


def _sdist(directory, files):
    path = directory / "line_markdown_parser-0.1.0.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        for name, content in files.items():
            data = content.encode()
            member = tarfile.TarInfo("line_markdown_parser-0.1.0/" + name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return path


def test_distribution_scan_accepts_package_and_standard_generated_metadata(tmp_path):
    _wheel(
        tmp_path,
        {
            "line_markdown_parser/__init__.py": '"""Public API."""',
            "line_markdown_parser/py.typed": "",
            "line_markdown_parser-0.1.0.dist-info/METADATA": "Name: line-markdown-parser\n",
            "line_markdown_parser-0.1.0.dist-info/WHEEL": "Wheel-Version: 1.0\n",
            "line_markdown_parser-0.1.0.dist-info/RECORD": "",
            "line_markdown_parser-0.1.0.dist-info/licenses/LICENSE": "MIT License\n",
        },
    )
    _sdist(
        tmp_path,
        {
            "README.md": "Public documentation\n",
            "docs/spec.md": "Public specification\n",
            "line_markdown_parser/converter.py": '"""Converter."""',
            "line_markdown_parser.egg-info/SOURCES.txt": "README.md\n",
            "line_markdown_parser.egg-info/PKG-INFO": "Name: line-markdown-parser\n",
            "PKG-INFO": "Name: line-markdown-parser\n",
            "setup.cfg": "[egg_info]\n",
        },
    )

    assert checker.check_distributions(tmp_path) == []


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
def test_distributions_reject_unapproved_files_and_private_metadata(tmp_path, kind):
    private_text = "Author-email: author@" + "mail.unapproved\n"
    if kind == "wheel":
        path = _wheel(
            tmp_path,
            {
                "line_markdown_parser/settings.json": "{}",
                "line_markdown_parser-0.1.0.dist-info/METADATA": private_text,
            },
        )
    else:
        path = _sdist(tmp_path, {"tests/test_example.py": "", "PKG-INFO": private_text})

    findings = checker.check_distributions(tmp_path)
    assert {finding.rule for finding in findings} == {
        "unapproved-archive-path",
        "non-example-email",
    }
    assert all(finding.filename.startswith(path.name) for finding in findings)


def test_wheel_rejects_traversal_without_extracting_files(tmp_path):
    _wheel(tmp_path, {"../outside.txt": "private content"})

    findings = checker.check_distributions(tmp_path)
    assert findings[0].rule == "invalid-or-duplicate-archive-path"
    assert not (tmp_path.parent / "outside.txt").exists()


def test_sdist_rejects_links_without_reading_link_targets(tmp_path):
    path = tmp_path / "line_markdown_parser-0.1.0.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        member = tarfile.TarInfo("line_markdown_parser-0.1.0/README.md")
        member.type = tarfile.SYMTYPE
        member.linkname = "../target.md"
        archive.addfile(member)

    assert checker.check_distributions(tmp_path)[0].rule == "non-regular-archive-entry"


def test_sdist_rejects_local_owner_and_unapproved_metadata(tmp_path):
    path = tmp_path / "line_markdown_parser-0.1.0.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        member = tarfile.TarInfo("line_markdown_parser-0.1.0/README.md")
        member.uname = "example-user"
        member.gname = "example-group"
        member.uid = 500
        member.gid = 500
        member.pax_headers = {"comment": "local build note"}
        archive.addfile(member, io.BytesIO())

    assert {finding.rule for finding in checker.check_distributions(tmp_path)} == {
        "archive-owner-metadata",
        "unapproved-archive-metadata",
    }


def test_wheel_rejects_archive_comments(tmp_path):
    path = _wheel(tmp_path, {"line_markdown_parser/py.typed": ""})
    with zipfile.ZipFile(path, "a") as archive:
        archive.comment = b"local build note"

    assert checker.check_distributions(tmp_path)[0].rule == "archive-comment"


def test_empty_archives_are_not_a_success(tmp_path):
    _wheel(tmp_path, {})
    _sdist(tmp_path, {})

    assert [finding.rule for finding in checker.check_distributions(tmp_path)] == [
        "empty-distribution",
        "empty-distribution",
    ]


def test_empty_missing_or_corrupt_distribution_input_fails(tmp_path):
    assert checker.check_distributions(tmp_path)[0].rule == "no-distributions"
    assert (
        checker.check_distributions(tmp_path / "missing")[0].rule
        == "missing-distribution-directory"
    )
    (tmp_path / "line_markdown_parser-0.1.0-py3-none-any.whl").write_bytes(b"broken")
    assert checker.check_distributions(tmp_path)[0].rule == "unreadable-distribution"


def test_archive_size_limit_is_enforced_before_reading_content(tmp_path, monkeypatch):
    monkeypatch.setattr(checker, "MAX_FILE_BYTES", 5)
    _wheel(tmp_path, {"line_markdown_parser/__init__.py": "x" * 6})

    assert checker.check_distributions(tmp_path)[0].rule == "archive-size-limit"


def test_cli_reports_location_and_rule_without_leaking_matched_text(tmp_path, capsys):
    secret = "ghp_" + "x" * 36
    _sdist(tmp_path, {"README.md": "Safe line\n" + secret + "\n"})

    assert checker.main(["--dist", str(tmp_path)]) == 1
    output = capsys.readouterr()
    assert secret not in output.out + output.err
    assert "README.md':2: github-token" in output.err


def test_cli_success_and_git_error_codes(tmp_path, monkeypatch, capsys):
    _sdist(tmp_path, {"README.md": "Public documentation"})
    assert checker.main(["--dist", str(tmp_path)]) == 0
    assert "passed" in capsys.readouterr().out

    def unavailable_git(*args):
        raise FileNotFoundError

    monkeypatch.setattr(checker, "_git", unavailable_git)
    assert checker.main([]) == 2
    assert "Unable to inspect" in capsys.readouterr().err
