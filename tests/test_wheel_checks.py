"""Prevent new package contract tests from silently missing the wheel check."""

import importlib.util
from pathlib import Path


def test_wheel_contract_manifest_covers_non_packaging_tests():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "wheel_check", root / "scripts/check_wheel.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    repository_only = {
        "test_build_backend.py",
        "test_public_artifacts.py",
        "test_wheel_checks.py",
    }
    expected = {path.name for path in (root / "tests").glob("*.py")} - repository_only
    assert set(module.CONTRACT_FILES) == expected
