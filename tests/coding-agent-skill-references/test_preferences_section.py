"""The "Your preferences" section: its command line reads both preferences files from an installed skill.

An installed skill's folder is often a symlink into the Nix store, `~/.claude/skills/<skill> ->
/nix/store/…/<skill>`, with the user's `<skill>.preferences.md` beside the link. Claude Code puts the
link's path in place of `${CLAUDE_SKILL_DIR}`, so the line must find the user's file through that path
as written, not through the folder the link points to.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS = ROOT / "skills"
TEMPLATE = SKILLS / "coding-agent-skill-references" / "preferences-section.md"
PLACEHOLDER = "<skill-name>"


def command_line(path: Path) -> str:
    """The command in the file's `!` line: the line that is an exclamation mark and one code span."""
    lines = [
        line[2:-1]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("!`") and line.endswith("`") and line.count("`") == 2
    ]
    assert len(lines) == 1, f"{path} has {len(lines)} preferences command lines"
    return lines[0]


SECTIONS = sorted(
    path
    for path in SKILLS.glob("*/SKILL.md")
    if "## Your preferences" in path.read_text(encoding="utf-8").splitlines()
)
CASES = [(TEMPLATE, "some-skill")] + [(path, path.parent.name) for path in SECTIONS]


def run(line: str, skill_dir: Path, project: Path) -> str:
    """The line's output, after Claude Code's textual substitution of the two variables."""
    script = line.replace("${CLAUDE_SKILL_DIR}", str(skill_dir)).replace("${CLAUDE_PROJECT_DIR}", str(project))
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True).stdout


@pytest.mark.parametrize(("path", "skill"), CASES, ids=[str(path.relative_to(SKILLS)) for path, _ in CASES])
def test_the_line_reads_both_files_through_a_symlinked_skill_folder(
    path: Path, skill: str, tmp_path: Path
) -> None:
    store = tmp_path / "nix" / "store" / "hash-skill" / "share" / "claude-skills" / skill
    store.mkdir(parents=True)
    skills = tmp_path / "home dir" / ".claude" / "skills"
    skills.mkdir(parents=True)
    (skills / skill).symlink_to(store, target_is_directory=True)
    (skills / f"{skill}.preferences.md").write_text("- Never use: Brave Browser\n", encoding="utf-8")
    project = tmp_path / "the project"
    (project / ".agents" / "skills").mkdir(parents=True)
    (project / ".agents" / "skills" / f"{skill}.preferences.md").write_text("- Project: yes\n", encoding="utf-8")

    line = command_line(path).replace(PLACEHOLDER, skill)

    assert run(line, skills / skill, project) == "- Never use: Brave Browser\n- Project: yes\n"


def test_the_line_prints_nothing_when_neither_file_exists(tmp_path: Path) -> None:
    (tmp_path / "skills" / "some-skill").mkdir(parents=True)
    line = command_line(TEMPLATE).replace(PLACEHOLDER, "some-skill")
    assert run(line, tmp_path / "skills" / "some-skill", tmp_path / "project") == ""


@pytest.mark.parametrize("path", SECTIONS, ids=lambda path: path.parent.name)
def test_a_skill_copies_the_template_line(path: Path) -> None:
    assert command_line(path) == command_line(TEMPLATE).replace(PLACEHOLDER, path.parent.name)
