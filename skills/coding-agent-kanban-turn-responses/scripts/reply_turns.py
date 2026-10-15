#!/usr/bin/env python3
"""Find the turns of this session and pull their prompts and reply sections out of the transcript.

Why it exists: a reply names the turn it answers by id, `Blocked.2 of 0f311c94`, and
The `pending` and `reassess` commands read every earlier turn's Review, Todo and Blocked sections; doing that with
ad-hoc grep and jq over the session's JSONL was slow and drifted. This script is the one reader.

Takes: the session transcript, `~/.claude/projects/<slug>/<session>.jsonl`. The slug is the main
checkout's path with `/` and `.` turned to `-`, a `.worktrees/` or `.claude/worktrees/` suffix
stripped, taken from the working directory. The session is `CLAUDE_CODE_SESSION_ID`, overridden
by `--session`; `--transcript FILE` names the file itself. Run from the project root:
`python3 scripts/reply_turns.py <subcommand>`. Standard library only.

A turn starts at a `user` record with `turnOrigin` `human`, `peer` (an agent's `<agent-message`
report) or `task_notification`, not a sidechain and not a compaction summary: the user sees a usage line
for each, so each counts as a turn. Its reply is the `text` blocks of the `assistant` records, not
sidechain, up to the next such prompt; tool results belong to the turn under way. The global
`--human-only` flag keeps the earlier reading, where only a `human` prompt opens a turn and a peer or
task-notification record belongs to the turn under way. A turn id is the first 8
characters of the prompt's `promptId`; `find` also takes the last 6 characters of the prompt
record's `uuid`, which earlier replies printed. An id that matches no turn or several fails,
naming the candidates.

A reply section opens on a line `<glyph> **<Name>:**`, Name one of Questions, Done, Open, Logged,
Waiting, Review, Todo (once To do), Blocked, matched by name and not glyph; a line of `▔` or `¯` under it belongs to the
header. A section ends at the next header or at a line starting `Still open from earlier`.

Subcommands, each printing plain text:
  id                              the current turn's id, the last prompt's
  list [-n N] [--grep TEXT]       one line per turn, newest last: id, timestamp, prompt's first line
                                  (an agent message or task notification is a turn: its line opens `<agent-message` or `<task-notification`)
  show ID [--prompt-only] [--section NAME]
                                  the prompt then the reply, or that section from every reply text
  blocked [--since ID]            each turn's Blocked section, from turn ID inclusive
  open [--since ID]               each turn's Review, Todo and Blocked sections, from turn ID
                                  inclusive, under the turn's id; a turn with neither is left out
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, replace
from functools import reduce
from pathlib import Path

# "To do" and "Review" are the headers before the user's renames to "Todo" (2026-10-05) and "Review" (2026-10-13); earlier turns still carry them.
SECTION_NAMES = ("Questions", "Done", "Open", "Logged", "Waiting", "Review", "To review", "Todo", "To do", "Blocked")
_HEADER = re.compile(r"^\s*\S+\s+\*\*(" + "|".join(SECTION_NAMES) + r"):\*\*")
_STOP = "Still open from earlier"
_ALL_ORIGINS = frozenset({"human", "peer", "task_notification"})
_HUMAN_ORIGINS = frozenset({"human"})
_ID_LENGTH = 8
_PROMPT_WIDTH = 100


class TurnError(Exception):
    """A lookup that cannot be answered; main prints it and exits 1."""


@dataclass(frozen=True)
class Turn:
    prompt_id: str
    uuid: str
    timestamp: str
    prompt: str
    replies: tuple[str, ...] = ()
    reply_times: tuple[str, ...] = ()  # each reply text's record timestamp, parallel to replies

    @property
    def id(self) -> str:
        return self.prompt_id[:_ID_LENGTH]


# --- locating and parsing the transcript ---------------------------------------------------


def project_slug(cwd: str) -> str:
    return re.sub(r"[/.]", "-", re.sub(r"/(\.worktrees|\.claude/worktrees)/.*", "", cwd))


def transcript_path(transcript: str | None, session: str | None, cwd: str, home: str) -> Path:
    return (
        Path(transcript)
        if transcript
        else Path(home) / ".claude" / "projects" / project_slug(cwd) / f"{session}.jsonl"
    )


def read_records(path: Path) -> tuple[dict, ...]:
    return tuple(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _text_of(content: object) -> str:
    return (
        content
        if isinstance(content, str)
        else "\n".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    )


def _is_prompt(record: dict, origins: frozenset[str] = _ALL_ORIGINS) -> bool:
    return (
        record.get("type") == "user"
        and record.get("turnOrigin") in origins
        and not record.get("isSidechain")
        and not record.get("isCompactSummary")
    )


def _is_reply(record: dict) -> bool:
    return record.get("type") == "assistant" and not record.get("isSidechain")


def _step(turns: tuple[Turn, ...], record: dict, origins: frozenset[str] = _ALL_ORIGINS) -> tuple[Turn, ...]:
    text = _text_of(record.get("message", {}).get("content", ""))
    return (
        (
            *turns,
            Turn(
                prompt_id=record.get("promptId", ""),
                uuid=record.get("uuid", ""),
                timestamp=record.get("timestamp", ""),
                prompt=_text_of(record.get("message", {}).get("content", "")),
            ),
        )
        if _is_prompt(record, origins)
        else (
            (
                *turns[:-1],
                replace(
                    turns[-1],
                    replies=(*turns[-1].replies, text),
                    reply_times=(*turns[-1].reply_times, record.get("timestamp", "")),
                ),
            )
            if _is_reply(record) and turns and text.strip()
            else turns
        )
    )


def turns_of(records: tuple[dict, ...], human_only: bool = False) -> tuple[Turn, ...]:
    origins = _HUMAN_ORIGINS if human_only else _ALL_ORIGINS
    return reduce(lambda turns, record: _step(turns, record, origins), records, ())


# --- finding a turn ------------------------------------------------------------------------


def _candidates(candidates: tuple[Turn, ...]) -> str:
    return ", ".join(f"{t.id} ({t.uuid[-6:]})" for t in candidates)


def find(turns: tuple[Turn, ...], ident: str) -> Turn:
    matches = tuple(
        t for t in turns if ident and (t.prompt_id.startswith(ident) or t.uuid.endswith(ident))
    )
    if len(matches) != 1:
        raise TurnError(
            f"turn id {ident!r} is ambiguous, matching {_candidates(matches)}"
            if matches
            else f"turn id {ident!r} matches no turn of {len(turns)}"
        )
    return matches[0]


def current(turns: tuple[Turn, ...]) -> Turn:
    if not turns:
        raise TurnError("the transcript holds no turn")
    return turns[-1]


# --- sections of a reply -------------------------------------------------------------------


def _fold(state: tuple[str | None, tuple[tuple[str, tuple[str, ...]], ...]], line: str):
    open_name, done = state
    header = _HEADER.match(line)
    return (
        (header.group(1), (*done, (header.group(1), (line,))))
        if header
        else (
            (None, done)
            if line.startswith(_STOP)
            else (
                (open_name, (*done[:-1], (done[-1][0], (*done[-1][1], line))))
                if open_name is not None
                else (None, done)
            )
        )
    )


def sections(text: str) -> tuple[tuple[str, str], ...]:
    """Each (name, text) section of one reply text, in order, trailing blank lines trimmed."""
    _, found = reduce(_fold, text.splitlines(), (None, ()))
    return tuple((name, "\n".join(lines).rstrip()) for name, lines in found)


def section_of(turn: Turn, name: str) -> str:
    wanted = name.capitalize()
    return "\n\n".join(body for text in turn.replies for n, body in sections(text) if n == wanted)


# --- rendering -----------------------------------------------------------------------------


def _first_line(text: str) -> str:
    lines = text.strip().splitlines()
    first = lines[0] if lines else ""
    return first if len(first) <= _PROMPT_WIDTH else first[: _PROMPT_WIDTH - 1] + "…"


def render_list(turns: tuple[Turn, ...], count: int | None, grep: str | None) -> str:
    kept = tuple(t for t in turns if grep is None or grep.lower() in t.prompt.lower())
    shown = kept if count is None else kept[-count:] if count > 0 else ()
    return "\n".join(f"{t.id}  {t.timestamp}  {_first_line(t.prompt)}" for t in shown)


def render_show(turn: Turn, prompt_only: bool, section: str | None) -> str:
    return (
        section_of(turn, section)
        if section
        else turn.prompt.strip()
        if prompt_only
        else turn.prompt.strip() + "\n\n--- reply ---\n\n" + "\n\n".join(turn.replies)
    )


def render_sections(turns: tuple[Turn, ...], since: str | None, names: tuple[str, ...]) -> str:
    start = turns.index(find(turns, since)) if since else 0
    return "\n\n".join(
        f"== {t.id} ==\n{body}"
        for t in turns[start:]
        if (body := "\n\n".join(b for name in names if (b := section_of(t, name))))
    )


# --- command line --------------------------------------------------------------------------


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="reply_turns.py", description=__doc__.split("\n")[0])
    p.add_argument("--session", default=os.environ.get("CLAUDE_CODE_SESSION_ID"))
    p.add_argument("--transcript", help="the transcript file itself, instead of finding it")
    p.add_argument(
        "--human-only",
        action="store_true",
        help="count only a human prompt as a turn, leaving out agent messages and task notifications",
    )
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("id", help="the current turn's id")
    ls = sub.add_parser("list", help="one line per turn")
    ls.add_argument("-n", type=int, help="only the last N turns")
    ls.add_argument("--grep", help="only turns whose prompt holds TEXT, ignoring case")
    sh = sub.add_parser("show", help="a turn's prompt and reply")
    sh.add_argument("id")
    sh.add_argument("--prompt-only", action="store_true")
    sh.add_argument("--section", choices=SECTION_NAMES, type=str.capitalize)
    bl = sub.add_parser("blocked", help="every turn's Blocked section")
    bl.add_argument("--since", metavar="ID", help="start at this turn, inclusive")
    op = sub.add_parser("open", help="every turn's Review, Todo and Blocked sections")
    op.add_argument("--since", metavar="ID", help="start at this turn, inclusive")
    return p


def run(args: argparse.Namespace, turns: tuple[Turn, ...]) -> str:
    return {
        "id": lambda: current(turns).id,
        "list": lambda: render_list(turns, args.n, args.grep),
        "show": lambda: render_show(find(turns, args.id), args.prompt_only, args.section),
        "blocked": lambda: render_sections(turns, args.since, ("Blocked",)),
        "open": lambda: render_sections(turns, args.since, ("Review", "To review", "Todo", "To do", "Blocked")),
    }[args.command]()


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    try:
        if not (args.transcript or args.session):
            raise TurnError("no session: set CLAUDE_CODE_SESSION_ID or pass --session or --transcript")
        path = transcript_path(args.transcript, args.session, os.getcwd(), str(Path.home()))
        if not path.is_file():
            raise TurnError(f"no transcript at {path}")
        output = run(args, turns_of(read_records(path), args.human_only))
        print(output) if output else None
        status = 0
    except TurnError as error:
        print(f"reply_turns.py: {error}", file=sys.stderr)
        status = 1
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
