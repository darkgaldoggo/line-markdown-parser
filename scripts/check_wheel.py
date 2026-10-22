"""Run the core contract suite against an installed wheel outside the checkout."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
import venv
from pathlib import Path

# These tests depend only on pytest and the installed package. Packaging tests
# exercise the checkout separately and are deliberately not copied here.
CONTRACT_FILES = (
    "flex_assertions.py",
    "test_converter.py",
    "test_renderer.py",
    "test_parser_performance.py",
    "test_inline_contexts.py",
    "test_flex_structure.py",
    "test_inline_html.py",
    "test_render_session.py",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    arguments = parser.parse_args()
    wheel = arguments.wheel.resolve(strict=True)
    if wheel.suffix != ".whl":
        parser.error("expected one wheel file")
    root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME", "PYTEST_ADDOPTS", "PYTEST_PLUGINS"):
        environment.pop(name, None)
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    with tempfile.TemporaryDirectory(prefix="line-parser-wheel-") as temporary:
        directory = Path(temporary)
        venv.EnvBuilder(with_pip=True).create(directory / "venv")
        python = (
            directory
            / "venv"
            / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        )

        def run(*command: str) -> None:
            subprocess.run(
                [str(python), "-I", *command],
                cwd=directory,
                env=environment,
                check=True,
            )

        run(
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-deps",
            str(wheel),
        )
        run("-m", "pip", "install", "--disable-pip-version-check", "pytest>=8")
        # Do not let an editable install or the checkout satisfy the import.
        run(
            "-c",
            "import sys; from pathlib import Path; import line_markdown_parser as p; assert Path(p.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()), p.__file__",
        )
        tests = directory / "tests"
        tests.mkdir()
        for filename in CONTRACT_FILES:
            shutil.copyfile(root / "tests" / filename, tests / filename)
        run("-m", "pytest", "-q", "tests")


if __name__ == "__main__":
    main()
