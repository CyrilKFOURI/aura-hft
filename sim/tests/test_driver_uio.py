"""
Pytest integration runner for AURA-HFT C++20 Linux UIO Driver.
Builds and executes the native C++ unit test suite.
"""

import subprocess
from pathlib import Path
import pytest


def test_cpp20_uio_driver():
    """Builds and runs driver/tests/test_uio_driver to verify UIO register mapping."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    driver_dir = repo_root / "driver"

    # Run make test in driver/
    res = subprocess.run(
        ["make", "test"],
        cwd=str(driver_dir),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"C++20 UIO driver tests failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "All C++20 UIO driver tests PASSED successfully!" in res.stdout
