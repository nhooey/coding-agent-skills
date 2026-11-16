#!/usr/bin/env python3
"""browser_check_hook: check the browser before a session's first page action.

A Claude Code hook, run by browser-check-hook.sh with the hook's JSON input on
stdin, for three entries told apart by the event and the tool name:

- PostToolUse on Bash: a command that runs `which_browser.py` with a marker
  (not `--list`) notes that the session checked its browser.
- PostToolUse on `select_browser` and `switch_browser`: clears the session's
  record, since the session may now drive another browser.
- PreToolUse on a Claude in Chrome tool that acts on a page (`navigate`,
  `computer`, `form_input`, `javascript_tool`, `file_upload`,
  `tabs_create_mcp`) with no live check: at the setting `remind` the call runs
  and the session is told to load `coding-agent-browser-selection` and run
  `which_browser.py`; at `deny` the call is denied with that as the reason; at
  `off` nothing. Either comes once per record, so at `deny` the second attempt
  passes and a session that can't run the script isn't locked out. Every other
  Claude in Chrome tool passes.

The record is `$CLAUDE_PLUGIN_DATA/browser-check/<session id>.json`, holding
when the session last checked and when it was last caught. Each expires after
an hour, so a resumed session checks again. With no place to keep it, every
page action is caught, and `deny` reminds instead, so a denial can't repeat
forever.

The setting is the line `Browser check: deny`, `remind` or `off` in
`~/.agents/skills/coding-agent-browser-selection.preferences.md`, overridden by
the same file under `.agents/skills/` in the project; `remind` when neither has
it.

Standard library only, Python 3.9 or later. Everything above `# The shell` is
pure: it takes values and returns new ones. Every Claude in Chrome call pays
for this module's start, so it imports nothing it can do without (no
`typing`); annotations are never evaluated.
"""

from __future__ import annotations

import collections
import json
import os
import re
import sys
import time

SKILL = "coding-agent-browser-selection"
DEFAULT_SETTING = "remind"
SETTING_LINE = re.compile(r"^\W*browser check\W*(deny|remind|off)\W*$", re.IGNORECASE | re.MULTILINE)
SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
LIFETIME = 3600.0

PREFIX = "mcp__claude-in-chrome__"
PAGE_ACTING = frozenset(
    {"navigate", "computer", "form_input", "javascript_tool", "file_upload", "tabs_create_mcp", "browser_batch"}
)
SWITCHING = frozenset({"select_browser", "switch_browser"})
# The script as the command run: first in the line or after a `;`, `&`, `|` or `(`, or a Python's
# operand; never an argument of `cat`, `sed` or `grep` reading it.
CHECK_RUN = re.compile(
    r"""(?:^|[;&|(]|\bpython3?(?:\s+-\S+)*)\s*["']?[^\s"';&|()]*which_browser\.py["']?(?![\w.])""",
    re.MULTILINE,
)
LIST_RUN = re.compile(r"which_browser\.py\S*\s+(\S+\s+)*(?:--list|--help|-h)\b")

CHECK = (
    f"Browser check (`{SKILL}`): this session hasn't checked which browser it drives "
    "since it started or last switched browser. "
    f"Load `{SKILL}` and run its `which_browser.py` with a marker in this tab's URL, "
    "and switch until the browser is the one the user prefers, before acting further."
)
REMINDER = "This call goes ahead. " + CHECK
DENIAL = CHECK + " If the script can't run here, say so and retry the call: it passes the second time."


# When the session last ran `which_browser.py`, and when it was last caught; None for never.
Record = collections.namedtuple("Record", ("checked", "caught"), defaults=(None, None))

# The hook's JSON output, or None to print nothing, and the record to keep.
Outcome = collections.namedtuple("Outcome", ("output", "record"))


# The choice


def setting_from(texts: tuple) -> str:
    """The setting in the last of the preferences texts that has one, or the default."""
    found = [matches[-1].lower() for matches in (SETTING_LINE.findall(text) for text in texts) if matches]
    return found[-1] if found else DEFAULT_SETTING


def live(stamp: float | None, now: float) -> bool:
    return stamp is not None and 0 <= now - stamp < LIFETIME


def browser_tool(tool_name: object) -> str | None:
    """The Claude in Chrome tool's own name, without the server prefix, if it is one."""
    is_browser = isinstance(tool_name, str) and tool_name.startswith(PREFIX)
    return tool_name[len(PREFIX) :] if is_browser else None


def is_check_run(command: object) -> bool:
    """Whether a Bash command runs `which_browser.py` to find a marker, not to list windows."""
    return isinstance(command, str) and bool(CHECK_RUN.search(command)) and not LIST_RUN.search(command)


def caught(setting: str, counted: bool) -> dict:
    deny = setting == "deny" and counted
    decision = (
        {"permissionDecision": "deny", "permissionDecisionReason": DENIAL}
        if deny
        else {"additionalContext": REMINDER}
    )
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", **decision}}


def decide(event: dict, setting: str, record: Record, now: float, counted: bool = True) -> Outcome:
    """The output for one hook input and the session's record after it.

    `counted` is False when the record can't be kept, so a denial would repeat.
    """
    name = event.get("hook_event_name")
    tool = event.get("tool_name")
    tool_input = event.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    browser = browser_tool(tool)
    if name == "PostToolUse" and tool == "Bash" and is_check_run(command):
        return Outcome(None, Record(checked=now))
    if name == "PostToolUse" and browser in SWITCHING:
        return Outcome(None, Record())
    held = live(record.checked, now) or live(record.caught, now)
    if name != "PreToolUse" or browser not in PAGE_ACTING or setting == "off" or held:
        return Outcome(None, record)
    return Outcome(caught(setting, counted), record._replace(caught=now))


# The shell


def read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as file:
            return file.read()
    except (OSError, UnicodeDecodeError):
        return ""


def preferences_texts(event: dict) -> tuple:
    project = os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or "."
    name = f".agents/skills/{SKILL}.preferences.md"
    return (read_text(os.path.join(os.path.expanduser("~"), name)), read_text(os.path.join(project, name)))


def record_path(event: dict) -> str | None:
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    session = event.get("session_id")
    if not data or not isinstance(session, str) or not SESSION_ID.match(session):
        return None
    return os.path.join(data, "browser-check", f"{session}.json")


def stamp(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def read_record(path: str | None) -> Record:
    try:
        data = json.loads(read_text(path)) if path else {}
    except ValueError:
        data = {}
    fields = data if isinstance(data, dict) else {}
    return Record(checked=stamp(fields.get("checked")), caught=stamp(fields.get("caught")))


def write_record(path: str, record: Record) -> None:
    try:
        if record == Record():
            if os.path.lexists(path):
                os.remove(path)
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            json.dump(record._asdict(), file)
    except OSError:
        pass


def main() -> int:
    try:
        event = json.loads(sys.stdin.read())
    except ValueError:
        return 0
    if not isinstance(event, dict):
        return 0
    path = record_path(event)
    before = read_record(path)
    outcome = decide(event, setting_from(preferences_texts(event)), before, time.time(), counted=path is not None)
    if path is not None and outcome.record != before:
        write_record(path, outcome.record)
    if outcome.output is not None:
        print(json.dumps(outcome.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
