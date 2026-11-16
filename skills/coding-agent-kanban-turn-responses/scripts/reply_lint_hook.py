#!/usr/bin/env python3
"""Run lint_reply.py on the main session's final response, as a Stop hook.

Why it exists: the skill tells the session to lint a draft before sending it, and sessions skip
that step. As a Stop hook this runs on every final response of a session that has loaded the
skill, and by the `Reply lint` preference either shows what it finds or sends the session back
to rewrite. It ships in the coding-agent-skills-hooks plugin, run by reply-lint-hook.sh.

Takes: the Stop hook's input, JSON on stdin. The session's transcript (`transcript_path`) must
show the skill loaded, by a Skill tool call naming it or the "Base directory for this skill:"
line of its text; otherwise nothing happens. The response is the input's
`last_assistant_message`, or, where that is missing, the last reply text of the current turn in
the transcript, read with reply_turns.py. Prints the hook's JSON output, or nothing, and always
exits 0:

    off      nothing
    remind   the findings as a `systemMessage`, shown to the user; the turn ends (the default)
    block    `decision: "block"` with the findings as the `reason`, so the session rewrites the
             response; once per turn: when `stop_hook_active` says the session is already
             continuing from a Stop hook, a second failure is shown as at `remind` instead

A response with no findings, or with no status list at all (no list header and no 📌 roll-up),
gets nothing at any setting. The setting is the last `Reply lint:` line of the user's preferences
file, `~/.agents/skills/coding-agent-kanban-turn-responses.preferences.md`, and then the
project's, the same file under `.agents/skills/` in CLAUDE_PROJECT_DIR or else the hook's cwd,
so the project's wins:

    - Reply lint: remind

Standard library only. Everything above `# --- the shell` is pure.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lint_reply  # noqa: E402
import reply_turns  # noqa: E402

SKILL = "coding-agent-kanban-turn-responses"
SETTINGS = ("block", "remind", "off")
DEFAULT = "remind"
_SETTING = re.compile(r"^[^\w\n]*reply lint[^\w\n]*(\w+)", re.IGNORECASE | re.MULTILINE)
_ROLL_UP = re.compile(r"^📌 \*\*Outstanding", re.MULTILINE)
_BASE_DIRECTORY = re.compile(r"^Base directory for this skill: (\S+?)/?$", re.MULTILINE)


# --- the core --------------------------------------------------------------------------------


def setting_of(texts: tuple[str, ...]) -> str:
    """The last valid `Reply lint:` value across the preferences texts, in order, else DEFAULT."""
    values = tuple(
        value for text in texts for value in (m.group(1).lower() for m in _SETTING.finditer(text)) if value in SETTINGS
    )
    return values[-1] if values else DEFAULT


def _record(line: str) -> dict | None:
    try:
        record = json.loads(line)
    except ValueError:
        return None
    return record if isinstance(record, dict) else None


def records_of(text: str) -> tuple[dict, ...]:
    """A transcript's records, skipping a line that isn't a JSON object, such as one half written."""
    return tuple(record for record in map(_record, text.splitlines()) if record is not None)


def _names_skill(name: object) -> bool:
    return isinstance(name, str) and (name == SKILL or name.endswith(":" + SKILL))


def _blocks(record: dict) -> tuple[dict, ...]:
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    return (
        ({"type": "text", "text": content},)
        if isinstance(content, str)
        else tuple(block for block in content if isinstance(block, dict))
        if isinstance(content, list)
        else ()
    )


def _marks_skill(block: dict) -> bool:
    return (
        block.get("type") == "tool_use"
        and block.get("name") == "Skill"
        and isinstance(block.get("input"), dict)
        and _names_skill(block["input"].get("skill"))
    ) or (
        block.get("type") == "text"
        and isinstance(block.get("text"), str)
        and any(path.rsplit("/", 1)[-1] == SKILL for path in _BASE_DIRECTORY.findall(block["text"]))
    )


def skill_loaded(records: tuple[dict, ...]) -> bool:
    """Whether the transcript's records show this skill loaded, by the Skill tool or a slash command."""
    return any(_marks_skill(block) for record in records for block in _blocks(record))


def has_status_list(text: str) -> bool:
    return bool(reply_turns.sections(text)) or bool(_ROLL_UP.search(text))


def findings_of(text: str) -> tuple[str, ...]:
    """The linter's findings on a final response, one `LINE: [k] message` each; none without a status list."""
    return (
        tuple(f"{number}: [{kind}] {message}" for number, kind, message in lint_reply.lint(text))
        if has_status_list(text)
        else ()
    )


def _listing(findings: tuple[str, ...]) -> str:
    return "\n".join(findings)


def decide(findings: tuple[str, ...], setting: str, already_blocked: bool) -> dict | None:
    """The hook's JSON output for these findings, or None for no output."""
    count = f"{len(findings)} {'finding' if len(findings) == 1 else 'findings'}"
    return (
        None
        if not findings or setting == "off"
        else {
            "decision": "block",
            "reason": (
                f"scripts/lint_reply.py found {count} in your final response, by its line numbers. "
                f"Write the whole response again with every one fixed, as {SKILL} says:\n"
                + _listing(findings)
            ),
        }
        if setting == "block" and not already_blocked
        else {"systemMessage": f"Reply lint: {count} in the final response, by its line numbers:\n" + _listing(findings)}
    )


def response_of(hook_input: dict, records: tuple[dict, ...]) -> str:
    """The final response: the input's `last_assistant_message`, else the current turn's last reply."""
    message = hook_input.get("last_assistant_message")
    if isinstance(message, str) and message.strip():
        return message
    try:
        replies = reply_turns.current(reply_turns.turns_of(records)).replies
    except reply_turns.TurnError:
        return ""
    return replies[-1] if replies else ""


# --- the shell -------------------------------------------------------------------------------


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def preferences_texts(home: Path, project_dir: str | None) -> tuple[str, ...]:
    name = Path(".agents") / "skills" / f"{SKILL}.preferences.md"
    return (_read(home / name), *((_read(Path(project_dir) / name),) if project_dir else ()))


def transcript_records(hook_input: dict) -> tuple[dict, ...]:
    transcript = hook_input.get("transcript_path")
    return records_of(_read(Path(transcript))) if isinstance(transcript, str) else ()


def run(raw: str, home: Path, project_dir: str | None) -> str:
    """The text to print for the hook input `raw`."""
    try:
        hook_input = json.loads(raw)
    except ValueError:
        return ""
    if not isinstance(hook_input, dict):
        return ""
    setting = setting_of(preferences_texts(home, project_dir or hook_input.get("cwd")))
    records = () if setting == "off" else transcript_records(hook_input)
    output = (
        decide(findings_of(response_of(hook_input, records)), setting, bool(hook_input.get("stop_hook_active")))
        if skill_loaded(records)
        else None
    )
    return json.dumps(output, ensure_ascii=False) if output else ""


def main() -> int:
    output = run(sys.stdin.read(), Path.home(), os.environ.get("CLAUDE_PROJECT_DIR"))
    if output:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
