"""The skills' tests: each module under tests/<skill>/ imports its scripts from skills/<skill>/scripts/.

Before pytest imports a test module, the skill's scripts/ folder goes on sys.path, so the test imports a
script by its module name and finds the files beside it through that module's `__file__`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"


def scripts_of(path: Path) -> Path | None:
    """skills/<skill>/scripts/ for a test module in tests/<skill>/, or None for one anywhere else."""
    path = path.resolve()
    parts = path.relative_to(TESTS).parts if path.is_relative_to(TESTS) else ()
    return ROOT / "skills" / parts[0] / "scripts" if len(parts) > 1 else None


def pytest_collectstart(collector: pytest.Collector) -> None:
    if isinstance(collector, pytest.Module):
        scripts = scripts_of(collector.path)
        if scripts is not None and str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
