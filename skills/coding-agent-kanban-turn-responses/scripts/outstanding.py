#!/usr/bin/env python3
"""Work out the turn ids, relative indices and raised-by turns the reply's 📌 section needs, and when it prints in full.

Why it exists: the session needs to know which turn raised an item of the closing 📌 section, its index
back from the current turn, and whether this reply prints the section in full or as one count line;
working that out by hand costs many tokens. This script does it mechanically and prints compact lines. It
reads transcripts through `reply_turns.py` (imported, not copied).

The relative index counts the turns `reply_turns.py list` prints, which are every turn the user sees a usage
line for, an agent message (`<agent-message`) or a task notification included: the current turn is
0 (`₀`), the one before it -1 (`₋₁`), and so on. Items are the top-level bullet or numbered lines of
the Pending, Waiting, Authorizations, Review, Todo and Decide lists of every reply (or their aliases in older replies: Unfinished or
Open, To review, To do, Decisions or Blocked), and of the 📌 section's subsections ("Still open from earlier" or
"Outstanding from previous turns"), which carry the same list headers. An item's summary is its bold text without a trailing colon, else the line. A summary
alone on its line is joined to the line beneath it, its body.

An item is matched across turns by its list and its subject key, so a reworded summary is the same item:
`entry 1411` where the summary names a backlog entry, else `branch <name>` for its first code span shaped
like a branch name, else its first 3 words that are not articles or prepositions.

Subcommands:
  index [ID...] [--last N]   each id's index as `-3` and `₋₃`; with no id, the last N turns
  items [--since ID] [--lists L] [--latest] [--width W]
                             `id  ₋ₖ  list  summary`, one line per item
  grep PATTERN [...]         the same lines for items whose line matches the regex, ignoring case
  render [...] [--counts]    a DRAFT 📌 section, each item ending `🔖 <id>₋ₖ`, for the session to prune; by
                             default only the last 20 turns (`--last N`, or `--since ID`), and never a
                             turn before the latest `reassess` turn, whose lists replace every earlier
                             item; `--counts` prints the draft's one count line instead.
                             Which items are still open is a judgement this script cannot make
  due [--now ISO]            `full` or `counts <time left>`: full once min(30 min, 5 x the average gap
                             of the last 5 completed turns) has passed since the last reply text that
                             printed the 📌 header with its rule; a count line never resets the clock
  decide [--json]            every open Decide item with its options, one line each, or with `--json`
                             one object `{"items": [...]}`, each item its turn id, list, number,
                             summary, kind (radio, checkbox, or binary for 👍 and 👎 options in
                             earlier turns), reference, note and options (letter, name, glyph,
                             consequence, pros, cons and notes), for a tool to read.
                             Open: raised since the latest `reassess` turn, its latest restatement only, and answered by no later prompt with an option letter (a line
                             holding a question mark answers nothing)
A `reassess` turn is one whose prompt opens on `reassess`, `recheck`, `regenerate` or `recalculate`, or a
prefix of one of them that is a prefix of no other command's name, such as `regen`, bare or after
`/coding-agent-kanban-turn-responses`.
`--latest` keeps each item's latest occurrence. `render` gives each item the turn that first printed it,
or, where later replies restated it with changed substance (the text after its bold summary), the turn
that restated it: the first turn of the latest run of identical texts. A restatement in a 📌 section is a
roll-up and never counts as a change; its own `🔖` suffix names the turn it came from.
Global: `--transcript FILE` and `--session ID`, as `reply_turns.py` takes them.
"""

from __future__ import annotations

import argparse
import json
import os
import itertools
import re
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from functools import reduce
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lint_reply  # noqa: E402
import reply_turns as rt  # noqa: E402

# list key -> (reply header names, glyph, header text), in the skill's order; the later names are aliases that older
# replies carry
LISTS = {
    "pending": (("Pending", "Unfinished", "Open"), "🚧", "Pending"),
    "waiting": (("Waiting",), "⏳", "Waiting"),
    "authorizations": (("Authorizations",), "🔑", "Authorizations"),
    "review": (("Review", "To review"), "🔍", "Review"),
    "todo": (("Todo", "To do"), "👉", "Todo"),
    "decide": (("Decide", "Decisions", "Blocked"), "🧠", "Decide"),
}
# `--lists` aliases, the keys named after those older headers
_OLD_KEYS = {"open": "pending", "unfinished": "pending", "blocked": "decide", "decisions": "decide"}
_KEY_OF_NAME = {name: key for key, (names, _, _) in LISTS.items() for name in names}
_PIN = re.compile(r"^\s*📌\s+\*\*(Still open from earlier|Outstanding from previous turns):\*\*")
_ITEM = re.compile(r"^ {0,2}(?:[-*]|\d+[.)])\s+(.*)$")
_PREFIX = re.compile(r"^🔖\s*\w+[₀-₉₋]*:\s*")
_SUFFIX = re.compile(r"\s*🔖\s+([0-9a-f]{8})[₀-₉₋]*\s*$")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_RULE = re.compile(r"^\s*[━▀]{3,}\s*$")
# command -> its names, the primary one first. Any prefix of a name names its command too, where it is a
# prefix of no other command's name: `regen` and `rec` are `reassess`, `res` is `open`, `re` is neither.
COMMANDS = {
    "reassess": ("reassess", "recheck", "regenerate", "recalculate"),
    "open": ("open", "pending", "restate"),
}
_SKILL_COMMANDS = frozenset({"coding-agent-kanban-turn-responses", "reply-block"})
_WORD_END = ".,;:!"
_ENTRY = re.compile(r"\bentr(?:y|ies)\s+(\d{3,4})\b", re.IGNORECASE)
_SPAN = re.compile(r"`([^`]+)`")
_BRANCH = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")
_STOP_WORDS = frozenset("a an and at by for from in is its of on the to with".split())
_KEY_WORDS = 3
_SUB = {**{str(d): "₀₁₂₃₄₅₆₇₈₉"[d] for d in range(10)}, "-": "₋"}
_RULE_WIDTH = 35  # the skill's ━ rule, one per column of the header
_DEFAULT_WIDTH = 100
# the full roll-up's interval: min(cap, factor x the average duration of the last 5 completed turns),
# each from its prompt to the next, so the gaps between the last `window` prompts
_CAP = timedelta(minutes=30)
_FACTOR = 5
_WINDOW = 6


@dataclass(frozen=True)
class Item:
    turn_id: str
    index: int
    list_key: str
    line: str
    pinned: bool = False
    origin_id: str = ""

    @property
    def summary(self) -> str:
        text = _PREFIX.sub("", self.line)
        bold = _BOLD.search(text)
        return (bold.group(1) if bold else text).strip().rstrip(":").strip()

    @property
    def subject(self) -> str:
        return subject_key(self.summary)

    @property
    def body(self) -> str:
        """The text after its bold summary, on its line or the one beneath: what a restatement compares, so a reworded summary alone is no change."""
        text = _PREFIX.sub("", self.line)
        bold = _BOLD.search(text)
        return text[bold.end() :] if bold else text


def subject_key(summary: str) -> str:
    """The key that matches an item across rewordings of its summary: `entry 1411` where the summary names a
    backlog entry, else `branch atomic-reload` for its first code span shaped like a branch name (lowercase
    words joined by hyphens), else its first 3 words that are not articles or prepositions, lowercased."""
    entry = _ENTRY.search(summary)
    branch = next((span for span in _SPAN.findall(summary) if _BRANCH.match(span)), None)
    words = tuple(w for w in re.findall(r"[a-z0-9]+", summary.lower()) if w not in _STOP_WORDS)
    return (
        f"entry {entry.group(1)}"
        if entry
        else f"branch {branch}"
        if branch
        else " ".join(words[:_KEY_WORDS])
        if words
        else _normal(summary)
    )


def merge_repeats(turns: tuple[rt.Turn, ...]) -> tuple[rt.Turn, ...]:
    """One turn per prompt id: a prompt record a continuation repeats folds its replies into the first."""
    first = {t.prompt_id: t for t in reversed(turns)}
    return tuple(
        replace(
            first[t.prompt_id],
            replies=tuple(r for u in turns if u.prompt_id == t.prompt_id for r in u.replies),
            reply_times=tuple(r for u in turns if u.prompt_id == t.prompt_id for r in u.reply_times),
        )
        for n, t in enumerate(turns)
        if turns.index(first[t.prompt_id]) == n
    )


def subscript(index: int) -> str:
    """`-3` as `₋₃`, `0` as `₀`."""
    return "".join(_SUB[c] for c in str(index))


def index_of(turns: tuple[rt.Turn, ...], turn: rt.Turn) -> int:
    return turns.index(turn) - (len(turns) - 1)


def _awaits_body(item_text: str) -> bool:
    """Whether an item line is its bold summary alone, its sentence on the line beneath."""
    bold = _BOLD.match(item_text)
    return bool(bold) and not item_text[bold.end() :].strip()


def _scan(
    state: tuple[str | None, bool, tuple[str, ...], bool], line: str
) -> tuple[str | None, bool, tuple[str, ...], bool]:
    key, pinned, found, awaiting = state
    header = rt._HEADER.match(line)
    item = _ITEM.match(line)
    body = line.strip()
    return (
        (_KEY_OF_NAME.get(header.group(1)), pinned, found, False)
        if header
        else (None, True, found, False)
        if _PIN.match(line)
        # A topic header's rule ends the list above it, and a blank line ends any list, so neither the
        # topic header nor prose after a list is read as an item's body.
        else (None, pinned, found, False)
        if rt.is_topic_rule(line)
        else (key, pinned, found, False)
        if not body
        else (key, pinned, (*found, f"{key}\t{int(pinned)}\t{item.group(1).strip()}"), _awaits_body(item.group(1).strip()))
        if key and item
        # The summary's own line holds no sentence, so the line beneath it is the item's body.
        else (key, pinned, (*found[:-1], f"{found[-1]} {body}"), False)
        if awaiting and body and body != lint_reply.SEPARATOR
        else state
    )


def items_of_text(text: str) -> tuple[tuple[str, bool, str], ...]:
    """Each (list key, inside a 📌 section, item line) of one reply text, a summary alone on its line joined to the line beneath."""
    _, _, found, _ = reduce(_scan, text.splitlines(), (None, False, (), False))
    return tuple((k, p == "1", line) for k, p, line in (f.split("\t", 2) for f in found))


def all_items(turns: tuple[rt.Turn, ...]) -> tuple[Item, ...]:
    return tuple(
        Item(
            t.id,
            index_of(turns, t),
            key,
            _SUFFIX.sub("", line),
            pinned,
            m.group(1) if (m := _SUFFIX.search(line)) else "",
        )
        for t in turns
        for text in t.replies
        for key, pinned, line in items_of_text(text)
    )


def _normal(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.lower())


def latest_only(items: tuple[Item, ...]) -> tuple[Item, ...]:
    last = {(i.list_key, i.subject): n for n, i in enumerate(items)}
    return tuple(i for n, i in enumerate(items) if last[(i.list_key, i.subject)] == n)


def command_named(word: str) -> str | None:
    """The command a word names: one of its names, or a prefix of them that no other command's name shares."""
    lowered = word.lower()
    found = frozenset(
        command for command, names in COMMANDS.items() if lowered and any(n.startswith(lowered) for n in names)
    )
    return next(iter(found)) if len(found) == 1 else None


def _between(text: str, opening: str, closing: str) -> str | None:
    """The text between the first `opening` tag and the `closing` tag after it; None where `opening` is absent."""
    _, found, rest = text.partition(opening)
    return rest.partition(closing)[0] if found else None


def _command_words(prompt: str) -> tuple[str, ...]:
    """The words a command is read from: the `<command-args>` of the skill's own slash command, else the prompt's
    words after `/coding-agent-kanban-turn-responses` where it opens on it, else the prompt's words."""
    name = _between(prompt, "<command-name>", "</command-name>")
    words = tuple(prompt.split())
    return (
        tuple((_between(prompt, "<command-args>", "</command-args>") or "").split())
        if name is not None and name.strip().lstrip("/") in _SKILL_COMMANDS
        else ()
        if name is not None
        else words[1:]
        if words and words[0].startswith("/") and words[0][1:] in _SKILL_COMMANDS
        else words
    )


def command_of(prompt: str) -> str | None:
    """The command a prompt runs, `reassess` or `open`, by its first word, bare or after the skill's slash command;
    None where the first word names no command or more than one."""
    first = next(iter(_command_words(prompt)), "").rstrip(_WORD_END)
    return command_named(first) if first.isalpha() else None


def reassess_start(turns: tuple[rt.Turn, ...]) -> int:
    """The position of the latest `reassess` turn, whose lists replace every item before it; else 0."""
    return next((n for n in reversed(range(len(turns))) if command_of(turns[n].prompt) == "reassess"), 0)


def raised_by(turns: tuple[rt.Turn, ...], occurrences: tuple[Item, ...]) -> tuple[str, int]:
    """The (turn id, index) that raised an item: the first turn of the latest run of identical lines among
    the replies' own lists, else the turn a 📌 roll-up's suffix names, else the earliest occurrence."""
    own = tuple(i for i in occurrences if not i.pinned)
    run = tuple(
        i for n, i in enumerate(own) if all(_normal(j.body) == _normal(own[-1].body) for j in own[n:])
    )
    named = next((t for i in occurrences if i.origin_id for t in turns if t.id == i.origin_id), None)
    return (
        (run[0].turn_id, run[0].index)
        if run
        else (named.id, index_of(turns, named))
        if named
        else (occurrences[0].turn_id, occurrences[0].index)
    )


def select(
    turns: tuple[rt.Turn, ...],
    since: str | None,
    lists: tuple[str, ...],
    latest: bool,
    pattern: str | None,
    floor: int = 0,
) -> tuple[Item, ...]:
    start = max(turns.index(rt.find(turns, since)) if since else 0, floor)
    first = turns[start].id if turns else ""
    ids = {t.id for t in turns[start:]}
    rx = re.compile(pattern, re.IGNORECASE) if pattern else None
    chosen = tuple(
        i for i in all_items(turns) if i.turn_id in ids and i.list_key in lists and (rx is None or rx.search(i.line))
    )
    return latest_only(chosen) if latest and first else chosen


def _cut(text: str, width: int) -> str:
    return text if len(text) <= width else text[: max(width - 1, 0)] + "…"


def parse_lists(text: str) -> tuple[str, ...]:
    keys = tuple(_OLD_KEYS.get(k.strip(), k.strip()) for k in text.split(",") if k.strip())
    unknown = tuple(k for k in keys if k not in LISTS)
    if unknown:
        raise rt.TurnError(f"unknown list {', '.join(unknown)}; choose from {','.join(LISTS)}")
    return keys


# --- rendering -----------------------------------------------------------------------------


def render_index(turns: tuple[rt.Turn, ...], ids: tuple[str, ...], last: int) -> str:
    chosen = tuple(rt.find(turns, i) for i in ids) if ids else turns[-last:] if last > 0 else ()
    return "\n".join(
        f"{t.id}  {index_of(turns, t)}  {subscript(index_of(turns, t))}"
        + ("" if ids else "  " + " ".join(t.prompt.split()[:8]))
        for t in chosen
    )


def render_items(items: tuple[Item, ...], width: int) -> str:
    return "\n".join(
        f"{i.turn_id}  {subscript(i.index)}  {i.list_key}  {_cut(i.summary, width)}" for i in items
    )


def with_origins(turns: tuple[rt.Turn, ...], items: tuple[Item, ...]) -> tuple[Item, ...]:
    """One item per (list, summary), carrying the turn that raised it, in order of first appearance."""
    keys = tuple(dict.fromkeys((i.list_key, i.subject) for i in items))
    return tuple(
        replace(group[-1], turn_id=origin[0], index=origin[1])
        for key in keys
        for group in [tuple(i for i in items if (i.list_key, i.subject) == key)]
        for origin in [raised_by(turns, group)]
    )


def tag(item: Item) -> str:
    """The 🔖 suffix: a space, the turn id, then the subscript index right beside it."""
    return f"🔖 {item.turn_id}{subscript(item.index)}"


def render_draft(items: tuple[Item, ...], width: int) -> str:
    groups = tuple(
        (key, tuple(i for i in items if i.list_key == key)) for key in LISTS if any(i.list_key == key for i in items)
    )
    # A blank line before every group but the first ends the group above: without it Markdown
    # reads the next header as more of the last bullet's text.
    body = tuple(
        line
        for n, (key, members) in enumerate(groups)
        for line in (
            *([""] if n else []),
            f"{LISTS[key][1]} **{LISTS[key][2]}:**  ",
            *(f"- **{_cut(i.summary, width)}** {tag(i)}" for i in members),
        )
    )
    return "\n".join(("📌 **Outstanding from previous turns:**  ", "━" * _RULE_WIDTH, *body)) if body else ""


def render_counts(items: tuple[Item, ...]) -> str:
    """The one count line a reply closes on between full roll-ups, the lists in the skill's order, an empty one left out."""
    counts = tuple((LISTS[key][1], sum(1 for i in items if i.list_key == key)) for key in LISTS)
    shown = tuple(f"{glyph} {n}" for glyph, n in counts if n)
    return "📌 Outstanding: " + " · ".join(shown) if shown else ""


# --- when the full roll-up is due ----------------------------------------------------------


def instant(stamp: str) -> datetime:
    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def prints_full(text: str) -> bool:
    """A reply text holding the full roll-up: the 📌 header with its rule on the next line, never the count line."""
    lines = text.splitlines()
    return any(_PIN.match(head) and _RULE.match(rule) for head, rule in zip(lines, lines[1:]))


def interval(turns: tuple[rt.Turn, ...]) -> timedelta:
    """min(30 min, 5 x the average duration of the last 5 completed turns, the 5 gaps between the last 6
    prompts); 30 min where there is no gap yet."""
    times = tuple(instant(t.timestamp) for t in turns[-_WINDOW:] if t.timestamp)
    gaps = tuple(later - earlier for earlier, later in zip(times, times[1:]))
    return min(_CAP, _FACTOR * sum(gaps, timedelta()) / len(gaps)) if gaps else _CAP


def last_full(turns: tuple[rt.Turn, ...]) -> tuple[datetime, str] | None:
    """The (time, turn id) of the latest reply text that printed the full roll-up."""
    return max(
        (
            (instant(stamp), t.id)
            for t in turns
            for text, stamp in zip(t.replies, t.reply_times)
            if stamp and prints_full(text)
        ),
        default=None,
    )


def duration(span: timedelta) -> str:
    """`45sec`, `12min`, `1h 5min`, by the skill's unit set, rounded to the minute from 1 min up."""
    seconds = max(round(span.total_seconds()), 0)
    minutes = round(seconds / 60)
    return (
        f"{seconds}sec"
        if seconds < 60
        else f"{minutes // 60}h {minutes % 60}min"
        if minutes >= 60
        else f"{minutes}min"
    )


def render_due(turns: tuple[rt.Turn, ...], now: datetime) -> str:
    """`full` or `counts <time left>`, then the interval and the last full roll-up behind the verdict."""
    every = interval(turns)
    last = last_full(turns)
    left = last[0] + every - now if last else timedelta()
    reason = (
        f"interval {duration(every)}, last full roll-up {duration(now - last[0])} ago in {last[1]}"
        if last
        else f"interval {duration(every)}, no full roll-up yet"
    )
    return f"counts {duration(left)}  {reason}" if left > timedelta() else f"full  {reason}"


# --- open Decide items with their options --------------------------------------------------

_DECIDE_ITEM = re.compile(r"^ {0,3}(\d+)[.)]\s+\*\*(.+?)\*\*", re.MULTILINE)
# 👍 and 👎 are read so an open yes-or-no item an earlier turn printed with them stays open; lint_reply.py
# reports them in a new reply, where a yes-or-no question is a 🔘 radio item lettered A and B.
_DECIDE_OPTION = re.compile(r"^\s*(🔘|🔲|👍|👎)\s+([A-Z])\.\s+\*\*(.+?)\*\*", re.MULTILINE)
_KIND_OF_GLYPH = {"🔘": "radio", "🔲": "checkbox", "👍": "binary", "👎": "binary"}
# What follows an item's reference in an answer: its letters after a dot, `.B` or `.A,C`, a note or
# not after them; its letters after a colon or a space, `: B` or ` A, C`, only where they end the line
# or another reference or `of <turn>` follows, so `Decide.2: A red one` is not option A; or, after a
# colon, words, `Decide.2: I'd rather wait`, an answer in the user's own words.
_LETTERS = r"[A-Z](?:\s*,\s*[A-Z])*"
_AFTER_REF = (
    rf"(?:\.{_LETTERS}(?!\w)"
    rf"|(?::\s*|\s+){_LETTERS}(?=\s*$|\s+(?:of|from)\s|\s+(?:[0-9a-f]{{6,8}}\.)?Decide\.)"
    r"|:\s*(?=\S))"
)
# An answer naming its turn: `9efb08a1.Decide.2.B`, `9efb08a.Decide.2: B,C`, `9efb08a1.Decide.2: <words>`,
# or `Decide.2.B of 9efb08a1`.
_ANSWER_WITH_ID = re.compile(rf"\b([0-9a-f]{{6,8}})\.Decide\.(\d+){_AFTER_REF}")
_ANSWER_ID_AFTER = re.compile(rf"\bDecide\.(\d+)(?:\.|:\s*|\s+){_LETTERS}\s+(?:of|from)\s+([0-9a-f]{{6,8}})\b")
# An answer to the last final response, naming no turn: `Decide.2.B`, `Decide.2: B`, `Decide.2: <words>`,
# or `2. B` opening a line. Whatever `_ANSWER_ID_AFTER` matches is turned away first, so `Decide.2: B,C of
# 9efb08a1` can't also pass as words after the colon, or as `.A` stopping partway through `.A, C from 9efb08a1`.
_ANSWER_BARE = re.compile(
    rf"(?<![0-9a-f]\.)\bDecide\.(\d+)"
    rf"(?!(?:\.|:\s*|\s+){_LETTERS}\s+(?:of|from)\s+[0-9a-f]{{6,8}}\b)"
    rf"{_AFTER_REF}(?!\s+(?:of|from)\s)"
)
_ANSWER_NUMBER = re.compile(r"^\s*(\d+)[.:]\s*[A-Z](?:\s*,\s*[A-Z])*\s*$")


@dataclass(frozen=True)
class DecideOption:
    letter: str
    name: str
    glyph: str = ""
    consequence: str = ""
    pros: tuple[str, ...] = ()
    cons: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecideItem:
    turn_id: str
    number: int
    summary: str
    kind: str
    options: tuple[DecideOption, ...]
    note: tuple[str, ...] = ()

    @property
    def ref(self) -> str:
        """The reference an answer names it by, `<turn id>.Decide.<n>`; the option letter follows it."""
        return f"{self.turn_id}.Decide.{self.number}"

    def as_json(self) -> dict:
        return {
            "turn": self.turn_id,
            "list": "Decide",
            "number": self.number,
            "summary": self.summary,
            "kind": self.kind,
            "ref": self.ref,
            "note": list(self.note),
            "options": [
                {
                    "letter": o.letter,
                    "name": o.name,
                    "glyph": o.glyph,
                    "consequence": o.consequence,
                    "pros": list(o.pros),
                    "cons": list(o.cons),
                    "notes": list(o.notes),
                }
                for o in self.options
            ],
        }


def _kind(glyphs: tuple[str, ...]) -> str:
    kinds = frozenset(_KIND_OF_GLYPH[g] for g in glyphs)
    return "checkbox" if "checkbox" in kinds else "binary" if "binary" in kinds else "radio"


def _plain_lines(lines: tuple[str, ...]) -> tuple[str, ...]:
    """Text lines with their indent and hard-break spaces gone, separator and blank lines dropped."""
    return tuple(s for s in (line.strip().strip("\u2800").strip() for line in lines) if s)


def _option(match: re.Match[str], lines: tuple[str, ...]) -> DecideOption:
    """One option and the ➕, ➖ and note lines under it, up to the next option or the blank line ending the list."""
    rest = match.string[match.end() :].split("\n", 1)[0].strip()
    plain = _plain_lines(tuple(itertools.takewhile(lambda line: line.strip() != "", lines)))
    return DecideOption(
        match.group(2),
        match.group(3).strip().rstrip(":").strip(),
        match.group(1),
        rest.lstrip(":").strip(),
        tuple(s.removeprefix("➕").strip() for s in plain if s.startswith("➕")),
        tuple(s.removeprefix("➖").strip() for s in plain if s.startswith("➖")),
        tuple(s for s in plain if not s.startswith(("➕", "➖"))),
    )


def _decide_item(turn_id: str, chunk: str) -> DecideItem | None:
    """One numbered item of a Decide list, from its line to the next item's; None where it holds no option."""
    head = _DECIDE_ITEM.match(chunk)
    found = tuple(_DECIDE_OPTION.finditer(chunk))
    ends = (*(m.start() for m in found[1:]), len(chunk))
    options = tuple(
        _option(m, tuple(chunk[m.end() : end].split("\n")[1:])) for m, end in zip(found, ends)
    )
    note = _plain_lines(tuple(chunk[head.end() : found[0].start()].split("\n")[1:])) if head and found else ()
    return (
        DecideItem(
            turn_id,
            int(head.group(1)),
            head.group(2).strip().rstrip(":").strip(),
            _kind(tuple(o.glyph for o in options)),
            options,
            note,
        )
        if head and options
        else None
    )


def decide_items_of_text(turn_id: str, text: str) -> tuple[DecideItem, ...]:
    """The Decide items of one reply text that carry options; a 📌 roll-up's bullets are not numbered and carry none."""
    bodies = tuple(body for name, body in rt.sections(text) if name in rt.DECISIONS)
    starts = tuple((body, tuple(m.start() for m in _DECIDE_ITEM.finditer(body))) for body in bodies)
    chunks = tuple(
        body[start:end] for body, found in starts for start, end in zip(found, (*found[1:], len(body)))
    )
    return tuple(item for item in (_decide_item(turn_id, c) for c in chunks) if item)


def _answers_of_line(line: str, previous_id: str) -> frozenset[tuple[str, int]]:
    """The (turn id or prefix, item number) pairs one prompt line answers; none where the line asks a question."""
    return (
        frozenset()
        if "?" in line
        else frozenset(
            (
                *((m.group(1), int(m.group(2))) for m in _ANSWER_WITH_ID.finditer(line)),
                *((m.group(2), int(m.group(1))) for m in _ANSWER_ID_AFTER.finditer(line)),
                *((previous_id, int(m.group(1))) for m in _ANSWER_BARE.finditer(line)),
                *((previous_id, int(m.group(1))) for m in _ANSWER_NUMBER.finditer(line)),
            )
        )
    )


def answered(turns: tuple[rt.Turn, ...]) -> frozenset[tuple[str, int]]:
    """Every (turn id or prefix, item number) a prompt, or a message sent while its turn ran, answers with an option
    or in words; a bare answer means the turn before it."""
    return frozenset(
        pair
        for previous, turn in zip(turns, turns[1:])
        for text in (turn.prompt, *turn.asides)
        for line in text.splitlines()
        for pair in _answers_of_line(line, previous.id)
    )


def _is_answered(item: DecideItem, answers: frozenset[tuple[str, int]]) -> bool:
    return any(item.turn_id.startswith(ident) and number == item.number for ident, number in answers)


def open_decide_items(turns: tuple[rt.Turn, ...]) -> tuple[DecideItem, ...]:
    """The open Decide items, oldest first: raised since the latest `reassess` turn, each subject's latest
    restatement only, none a later prompt answered with an option."""
    kept = turns[reassess_start(turns) :]
    raised = tuple(item for t in kept for text in t.replies for item in decide_items_of_text(t.id, text))
    last = {subject_key(item.summary): n for n, item in enumerate(raised)}
    answers = answered(turns)
    return tuple(
        item
        for n, item in enumerate(raised)
        if last[subject_key(item.summary)] == n and not _is_answered(item, answers)
    )


def render_decide(items: tuple[DecideItem, ...], as_json: bool, width: int) -> str:
    return (
        json.dumps({"items": [i.as_json() for i in items]}, ensure_ascii=False)
        if as_json
        else "\n".join(
            f"{i.ref}  {i.kind}  {_cut(i.summary, width)}  "
            + " ".join(f"{o.letter}. {o.name}" for o in i.options)
            for i in items
        )
    )


# --- command line --------------------------------------------------------------------------


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="outstanding.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--session", default=os.environ.get("CLAUDE_CODE_SESSION_ID"))
    p.add_argument("--transcript", help="the transcript file itself, instead of finding it")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp: argparse.ArgumentParser, pattern: bool = False) -> None:
        sp.add_argument("pattern", metavar="PATTERN") if pattern else None
        sp.add_argument("--since", metavar="ID", help="start at this turn, inclusive")
        sp.add_argument("--lists", default=",".join(LISTS), help="comma list of pending,waiting,authorizations,review,todo,decide")
        sp.add_argument("--latest", action="store_true", help="keep each summary's latest occurrence only")
        sp.add_argument("--width", type=int, default=_DEFAULT_WIDTH, help="cut summaries to this width")

    ix = sub.add_parser("index", help="relative index of turn ids, or of the last N turns")
    ix.add_argument("ids", nargs="*", metavar="ID")
    ix.add_argument("--last", type=int, default=10, metavar="N")
    common(sub.add_parser("items", help="every item of the lists, one line each"))
    common(sub.add_parser("grep", help="items whose line matches a regex"), pattern=True)
    rd = sub.add_parser("render", help="a DRAFT Outstanding section to prune; open or settled is the session's call")
    common(rd)
    rd.add_argument("--last", type=int, default=20, metavar="N", help="without --since, only the last N turns")
    rd.add_argument("--counts", action="store_true", help="print the draft's one count line instead of its items")
    du = sub.add_parser("due", help="`full` or `counts <time left>`: whether this reply prints the full roll-up")
    du.add_argument("--now", metavar="ISO", help="the time to judge at, instead of the clock")
    de = sub.add_parser("decide", help="every open Decide item with its options")
    de.add_argument("--json", action="store_true", help='print one object, {"items": [...]}, for a tool to read')
    de.add_argument("--width", type=int, default=_DEFAULT_WIDTH, help="cut summaries to this width")
    return p


def run(args: argparse.Namespace, turns: tuple[rt.Turn, ...]) -> str:
    if args.command == "index":
        out = render_index(turns, tuple(args.ids), args.last)
    elif args.command == "due":
        out = render_due(turns, instant(args.now) if args.now else datetime.now(timezone.utc))
    elif args.command == "decide":
        out = render_decide(open_decide_items(turns), args.json, args.width)
    else:
        rendering = args.command == "render"
        since = args.since or (turns[-args.last].id if rendering and 0 < args.last <= len(turns) else None)
        found = select(
            turns,
            since,
            parse_lists(args.lists),
            args.latest and not rendering,
            getattr(args, "pattern", None),
            reassess_start(turns) if rendering else 0,
        )
        out = (
            (render_counts if args.counts else lambda items: render_draft(items, args.width))(with_origins(turns, found))
            if rendering
            else render_items(found, args.width)
        )
    return out


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    try:
        if not (args.transcript or args.session):
            raise rt.TurnError("no session: set CLAUDE_CODE_SESSION_ID or pass --session or --transcript")
        path = rt.transcript_path(args.transcript, args.session, os.getcwd(), str(Path.home()))
        if not path.is_file():
            raise rt.TurnError(f"no transcript at {path}")
        output = run(args, merge_repeats(rt.turns_of(rt.read_records(path))))
        print(output) if output else None
        status = 0
    except (rt.TurnError, re.error, ValueError) as error:
        print(f"outstanding.py: {error}", file=sys.stderr)
        status = 1
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
