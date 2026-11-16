#!/usr/bin/env python3
"""memory_write_reminder: route a lesson about how to work into a skill.

A Claude Code PreToolUse hook on Write and Edit, run by memory-write-reminder.sh
once the written path has a `/memory/` folder in it, with the hook's input on
stdin.

When the Write or Edit's `file_path`, with `~` expanded, is under
`~/.claude/projects/<project>/memory/` (or the same under `$CLAUDE_CONFIG_DIR`
when it is set), the write goes ahead and the hook adds a reminder as context.
It gives the reminder once per session: a session reminded is kept as an empty
file `$CLAUDE_PLUGIN_DATA/memory-write-reminder/<session id>`. With no place to
keep it, the reminder comes at every memory write.

Standard library only, Python 3.9 or later. Everything above `# The shell`
is pure: it takes values and returns new ones.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Optional

SKILL = "coding-agent-route-feedback-to-skills-over-memory"
TOOLS = frozenset({"Write", "Edit"})
SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
REMINDER = (
    "If this records how to work (a correction, a standing rule, a tool gotcha), "
    f"load `{SKILL}` and route it to a skill. "
    "Identity, project state and pointers stay in memory."
)


# The choice


def expanded(path: str, home: str) -> PurePosixPath:
    """`path` with a leading `~` made `home`, and `.` and `..` resolved as text."""
    full = home + path[1:] if path == "~" or path.startswith("~/") else path
    return PurePosixPath(os.path.normpath(full))


def is_memory_file(path: str, home: str, config_dir: str) -> bool:
    """Whether `path` is a file under `<config dir>/projects/<project>/memory/`."""
    parts = expanded(path, home).parts
    projects = expanded(config_dir, home).joinpath("projects").parts
    rest = parts[len(projects) :]
    return parts[: len(projects)] == projects and len(rest) >= 3 and rest[1] == "memory"


def written_path(event: object) -> Optional[str]:
    """The `file_path` of a Write or Edit event, if it is one."""
    if not isinstance(event, dict) or event.get("tool_name") not in TOOLS:
        return None
    tool_input = event.get("tool_input")
    path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    return path if isinstance(path, str) and path else None


def decide(event: object, home: str, config_dir: str, reminded: bool) -> Optional[dict]:
    """The hook's output: the reminder for a session's first memory write, else nothing."""
    path = written_path(event)
    if reminded or path is None or not is_memory_file(path, home, config_dir):
        return None
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": REMINDER}}


# The shell


def marker_path(event: object) -> Optional[Path]:
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    session = event.get("session_id") if isinstance(event, dict) else None
    if not data or not isinstance(session, str) or not SESSION_ID.match(session):
        return None
    return Path(data) / "memory-write-reminder" / session


def mark(path: Optional[Path]) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    except OSError:
        pass


def main() -> int:
    try:
        event = json.loads(sys.stdin.read())
    except ValueError:
        return 0
    home = os.environ.get("HOME", "")
    if not home:
        return 0
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR") or f"{home}/.claude"
    marker = marker_path(event)
    result = decide(event, home, config_dir, marker is not None and marker.exists())
    if result is not None:
        mark(marker)
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
