# Contributing

Bug reports, fixes, tests, and documentation improvements are welcome in English or Japanese.

## Development

Use Python 3.10 or later:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Run these checks before opening a pull request:

```bash
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python scripts/check_public_artifacts.py
python -m build
python -m twine check dist/*
python scripts/check_public_artifacts.py --dist dist
```

## Issues and pull requests

Open pull requests against `main` and describe the user-visible change and checks performed. Bug reports should include a minimal Markdown input, expected and actual output, and Python version. For appearance issues, include the LINE client and version.

Use synthetic examples, such as `example.com` links, with no credentials, personal information, or real conversations. Add regression coverage for parsing and size-handling fixes. Keep the English and Japanese READMEs consistent and update [the specification](docs/spec.md) when changing the public API.

Required CI checks must pass before merging. Ordinary changes do not need a version bump.

## Releases

1. Merge a release pull request with matching versions in `pyproject.toml` and `line_markdown_parser/__init__.py` and a dated changelog entry.
2. After CI passes, create an annotated `vX.Y.Z` tag on that commit in `main`.
3. The release workflow validates and builds the package, then publishes a GitHub Release with wheel and source distribution assets. Verify the assets and installation instructions.
