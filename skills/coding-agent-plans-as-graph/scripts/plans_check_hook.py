#!/usr/bin/env python3
"""plans_check_hook: the plan graph's check after an edit to a plan node.

A Claude Code PostToolUse hook on Write and Edit, run by plans-check-hook.sh
once the written path is known to be a node under a plan folder:

  plans_check_hook.py <project root> <plan folder> <node path within it>

with the hook's input on stdin.

Runs plans.py's check on the plan folder and, when it finds problems, adds
them as context beside the edit's result. It never blocks and never writes the
overview.

While a plan is being written as several nodes, each write would report the
links not yet made. So a write reports the findings that name the file just
written, every time; the findings about other files only when the written file
is clean, and each of those once per session. What was reported is kept in
`$CLAUDE_PLUGIN_DATA/plans-check/<session id>`, one finding per line; with no
place to keep it, the other files' findings come at every clean write.

Standard library only, Python 3.9 or later. Everything above `# The shell`
is pure: it takes values and returns new ones.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import FrozenSet, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plans  # noqa: E402

SKILL = "coding-agent-plans-as-graph"
SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
CYCLE = re.compile(r"^`[a-z-]+` cycle: (.*)$")


# The choice


def names_file(problem: str, rest: str) -> bool:
    """Whether a finding is about the node at `rest`: it opens on its path, or its id is in a cycle."""
    cycle = CYCLE.match(problem)
    node_id = Path(rest).stem
    return problem.startswith(f"{rest}:") or bool(cycle and node_id in cycle.group(1).split(" → "))


def choose(problems: plans.Problems, rest: str, reported: FrozenSet[str]) -> Tuple[plans.Problems, plans.Problems]:
    """The findings to report: the written file's own, and the others not yet reported, if it has none."""
    own = tuple(p for p in problems if names_file(p, rest))
    others = () if own else tuple(p for p in problems if not names_file(p, rest) and p not in reported)
    return own, others


def remembered(problems: plans.Problems, reported: FrozenSet[str], shown: plans.Problems) -> FrozenSet[str]:
    """What counts as reported after this write: only findings still standing, so one that returns is shown again."""
    return frozenset(p for p in problems if p in reported or p in shown)


def message(folder: str, rest: str, own: plans.Problems, others: plans.Problems) -> Optional[str]:
    if not own and not others:
        return None
    lines = (
        (f"Plans check (`{SKILL}`) after writing {folder}/{rest}, which the edit leaves inconsistent:",)
        + tuple(f"- {p}" for p in own)
        + ((f"Elsewhere in {folder}/:",) if others else ())
        + tuple(f"- {p}" for p in others)
        + (
            "The edit went ahead. Fix these, or carry on if later nodes will; once the graph is done, "
            "run `plans.py check`, then `plans.py overview`.",
        )
    )
    return "\n".join(lines)


def output(text: Optional[str]) -> Optional[dict]:
    return None if text is None else {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}


# The shell


def reported_path(session: object) -> Optional[Path]:
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if not data or not isinstance(session, str) or not SESSION_ID.match(session):
        return None
    return Path(data) / "plans-check" / session


def read_reported(path: Optional[Path]) -> FrozenSet[str]:
    try:
        return frozenset(line for line in path.read_text(encoding="utf-8").splitlines() if line) if path else frozenset()
    except (OSError, UnicodeDecodeError):
        return frozenset()


def write_reported(path: Optional[Path], reported: FrozenSet[str]) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(f"{p}\n" for p in sorted(reported)), encoding="utf-8")
    except OSError:
        pass


def main(argv: list) -> int:
    if len(argv) != 4:
        return 0
    root, folder, rest = argv[1:]
    try:
        event = json.loads(sys.stdin.read())
    except ValueError:
        event = {}
    store = reported_path(event.get("session_id") if isinstance(event, dict) else None)
    try:
        graph, load_problems = plans.build(plans.read_plan(Path(root) / folder))
    except (OSError, UnicodeDecodeError):
        return 0
    problems = load_problems + plans.check(graph)
    reported = read_reported(store)
    own, others = choose(problems, rest, reported)
    after = remembered(problems, reported, own + others)
    if after != reported:
        write_reported(store, after)
    result = output(message(folder, rest, own, others))
    if result is not None:
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
