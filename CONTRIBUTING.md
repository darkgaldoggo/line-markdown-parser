# Contributing

Bug reports, small fixes, tests, and documentation improvements are welcome in English or Japanese.

## Development setup

Use Python 3.10 or later:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

Before opening a pull request, run:

```bash
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python scripts/check_public_artifacts.py
python -m build
python -m twine check dist/*
python scripts/check_public_artifacts.py --dist dist
```

Keep parser tests focused on observable behavior and representative Markdown. Include regression coverage when fixing a parsing or size-handling bug. Examples and fixtures must be synthetic and reproducible without private services or credentials.

## Issues and pull requests

Use a short-lived branch and open a pull request against `main`. Describe the user-visible change and relevant validation. Include a small Markdown input, expected output, actual output, and Python version in bug reports. If the issue concerns appearance, include the LINE client and version, with personal information removed.

Keep the English and Japanese READMEs consistent. Update `docs/spec.md` when changing the public contract. Internal names beginning with `_` are not public APIs. Keep new public APIs small and document their inputs, output shape, and failure behavior.

CI uses Ruff for lint and formatting, runs tests on Python 3.10 through 3.14, checks package builds and public artifact contents, and installs the wheel outside the checkout. The required aggregate check is named `test`. Prefer squash merges after required checks pass and review feedback is resolved. A normal code change does not require a version bump or a release tag.

## Public repository and package hygiene

Treat every tracked file, commit, issue attachment, release asset, and package artifact as public material.

- Never include credentials, access tokens, private keys, real message content, or personal contact information.
- Use synthetic examples and reserved example domains such as `example.com`.
- Exclude local configuration, credentials, environment-specific identifiers, absolute filesystem paths, private operational notes, and ad hoc validation exports.
- Do not import a private application's Git history or copy its configuration, deployment scripts, logs, screenshots, or internal documentation into this project.
- A directory named `internal` or a package exclusion rule does not make tracked files private. GitHub visibility and distribution contents must be checked separately.
- Before first public publication, inspect the complete tracked tree and commit history, then inspect both the source distribution and wheel. Confirm that the intended package files and public documentation are the only distributed content.
- Repeat targeted leakage checks for changed files and generated artifacts before each release. Automated scanners support review; they do not replace reviewing examples and documentation.

Public reproductions should explain how a contributor can observe a behavior with synthetic input. Keep account-specific test results and operational history outside this repository.

The build backend normalizes source-archive ownership and timestamps, so local
account names and IDs are not carried into release assets. The artifact check
also rejects unexpected owner metadata. Use `python -m build` so this hook runs.

## Release policy

The first release is version 0.1.0. The current release workflow publishes GitHub Release assets only. There is no PyPI publishing workflow. A public GitHub repository or GitHub Release does not imply that the package is on PyPI.

For a package release:

1. Prepare a release pull request with the package version and dated changelog entry. Keep every version declaration consistent.
2. Run the required CI and review the source tree, history, source distribution, and wheel for unwanted content.
3. Merge the release pull request into `main`.
4. Create an annotated `vX.Y.Z` tag on the merged release commit. Check that its version matches the built artifacts.
5. The tag triggers GitHub Actions to verify version consistency, run lint, formatting and tests, audit public content, and build and validate the wheel and source distribution.
6. After those checks pass, the workflow creates a GitHub Release with the wheel and source distribution as assets. Verify the release, assets, and installation instructions.

Use the minimum workflow permissions needed for publication. Do not publish a tag from an unmerged feature branch. Treat publishing a new version as a separate action from merging ordinary changes.

If maintainers explicitly configure PyPI publishing in the future, use GitHub Actions with PyPI Trusted Publishing through OIDC and a protected release environment. Add and review that workflow as a separate change. Its normal publishing path should not require a long-lived PyPI token on a maintainer's computer. Until then, install from the Git tag or local checkout as described in the README.

When documenting validation, distinguish automated tests, LINE API validation, actual delivery, and client appearance. Report only the checks performed; do not turn a local test result into a claim of live LINE verification.
