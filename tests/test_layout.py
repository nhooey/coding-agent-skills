"""The repository's layout: a skill holds only what it runs, and its tests live under tests/<skill>/.

An installed skill is its folder under skills/, scripts/ and all, so a test left there ships with it.
The skills' scripts run wherever the skill is installed, so they import only the standard library and
each other; the tests, run only here, may use the libraries the dev shell provides.
"""

from __future__ import annotations

import ast
import collections
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
SCRIPTS = sorted(path for path in SKILLS.glob("*/scripts/**/*.py") if "__pycache__" not in path.parts)


def is_test(path: Path) -> bool:
    """Whether a path under skills/ is a test file or a folder of tests."""
    if path.is_dir():
        return path.name in {"tests", "test"}
    stem = path.name.split(".", 1)[0]
    return path.name.startswith("test_") or stem.endswith("_test") or path.suffix == ".bats"


def imported_modules(path: Path) -> set[str]:
    """The top-level names of the modules a Python file imports, relative imports as written."""
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add("." * node.level + (node.module or "").split(".")[0])
    return names


def test_no_test_sits_under_skills() -> None:
    found = sorted(
        str(path.relative_to(ROOT))
        for path in SKILLS.rglob("*")
        if "__pycache__" not in path.parts and is_test(path)
    )
    assert found == [], "tests go in tests/<skill>/, not in the skill: " + ", ".join(found)


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda path: str(path.relative_to(SKILLS)))
def test_a_script_imports_only_the_standard_library_and_its_siblings(script: Path) -> None:
    siblings = {path.stem for path in script.parent.glob("*.py")}
    allowed = set(sys.stdlib_module_names) | siblings
    assert sorted(imported_modules(script) - allowed) == []


def test_no_two_skills_scripts_share_a_module_name() -> None:
    """The tests import each skill's scripts by name from one sys.path, so a name means one script."""
    folders = collections.defaultdict(set)
    for script in SCRIPTS:
        folders[script.stem].add(str(script.parent.relative_to(ROOT)))
    assert {name: sorted(f) for name, f in folders.items() if len(f) > 1} == {}
