#!/usr/bin/env python3
"""Check a draft final response's list separators, item summary lines, Decide options and
header underlines before it is sent.

Why it exists: a multi-line item is parted from the next item of its list by a line holding the
list's indent and one separator character, SEPARATOR below, and nothing else, with no blank line
on either side, but one: a list ends at a blank line. A header, or any line of prose,
written directly under a list's last line, its separator line included, is read by Markdown as
more text of that last item (a lazy continuation), so the header lands inside the item and the
next list continues the same numbering; a blank line before it ends the list. An empty line
between items renders no gap, and a line of spaces renders one or
none depending on its width; a U+00A0 typed there reaches the terminal as a plain space, so it is
no better. A blank line beside the separator renders a double gap, and a separator between
one-line items, or under a header's underline, is a gap that should not be there. Reading for
these by eye misses them. A numbered item opens on its bold summary alone, ending in a hard line
break, 2 trailing spaces, with its sentence on the line beneath; without the break the 2 lines run
together into one. An option's lines are plain lines of its item's paragraph, not a list, so a
`-` or `1.` list among them starts a real list, and every line after it, the later options among
them, joins its last entry and prints at its indent. A header's underline holds one character per
column of the header as it renders, its emoji counting 2: `▔` under a list's header, `━` under the
📌 roll-up's and `═` under a topic header, which groups the lists of a `reassess` or `open` reply by
topic. Under topic headers each list numbers on from where the same list ended in the topics before,
so `Decide.4` still names one item; a list that starts again at 1 gives 2 items one reference. A
table indented under a list item is
never drawn: its rows print as raw pipe text. A line of text directly under a table's last row is
read as one more row, and a table directly under a line of text can be read as part of it, so a
table has a blank line above and below it. An option is 🔘 radio or 🔲 checkbox, lettered from `A`; a
yes-or-no question is a radio item with `A` and `B`, so a 👍 or 👎 option, or one lettered `Y` or
`N`, is a finding.

Takes: the response on stdin, or in the FILE given. Prints one line per finding, `LINE: [k]
message`, and exits 1 if there is any, else 0:

    [a] a multi-line item followed by the next item of its list with no separator line
    [b] a separator line between 2 one-line items, or right under a header's underline
    [c] a line holding only spaces, tabs or U+00A0, but not empty, inside a list
    [d] a separator line whose indent is not its list's indent, the item's text column
    [e] a blank line directly above a separator line, or below one where the list goes on
    [f] a numbered item with text after its bold summary on the same line
    [g] a numbered item's summary line with lines under it but no hard line break
    [h] a list line among a Decide item's options, after its first option line
    [i] a header underline whose width is not the header's
    [j] a header or line of prose directly under a list, with no blank line to end the list
    [k] a table inside a list item, indented to its text
    [l] a table with no blank line above it, or a line directly under its last row
    [m] a list under a topic header that does not number on from the same list in the topics before
    [n] a Decide option with a 👍 or 👎 glyph, or lettered `Y` or `N`

A list is a run of items, `-`, `*`, `+`, `1.` or `1)`, at one indent: every list of the response,
the 📌 roll-up's groups and an item's own numbered steps among them. An item is multi-line when
any line other than its first belongs to it. Lines inside ``` or ~~~ fences are not read.

    python3 -I scripts/lint_reply.py draft.md

Standard library only.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass

# The one place the separator character is set: U+2800 BRAILLE PATTERN BLANK, which neither the
# model's output nor the terminal treats as whitespace.
SEPARATOR = chr(0x2800)
NBSP = chr(0xA0)

_SEP = re.compile(r"^( *)" + re.escape(SEPARATOR) + r" *$")
_SPACES = re.compile(r"^[ \t" + NBSP + r"]+$")
_ITEM = re.compile(r"^( *)([-*+]|\d{1,9}[.)])( +)(?=\S)")
_SUMMARY = re.compile(r"\*\*.+?\*\*")
_UNDERLINE = re.compile(r"^\s*[▔━═]+\s*$")
TOPIC_RULE = "═"  # U+2550, under a topic header; ▔ goes under a list's header and ━ under the 📌 roll-up's
_LIST_NAME = re.compile(r"\*\*([^*]+?):\*\*")
_FENCE = re.compile(r"^ *(```|~~~)")
# An option line; 👍 and 👎 are matched only to be reported, since an option is 🔘 or 🔲 lettered from A.
_OPTION = re.compile(r"^( *)(🔘|🔲|👍|👎) ([A-Z])\. ")
_YES_NO = frozenset({"👍", "👎", "Y", "N"})
_ROW = re.compile(r"^ *\|")


@dataclass
class Item:
    line: int
    indent: int
    column: int
    lines: int = 1
    prev: Item | None = None
    sep_before: int | None = None
    sep_after: int | None = None
    unbroken: bool = False  # a summary alone on its line, with no hard line break after it


def _indent(text: str) -> int:
    return len(text) - len(text.lstrip(" "))


def _width(text: str) -> int:
    """Terminal columns of `text` as it renders: `**` markers dropped, wide characters counting 2."""
    width = 0
    for char in text.replace("**", ""):
        if unicodedata.combining(char) or unicodedata.category(char) in ("Mn", "Me", "Cf") or 0xFE00 <= ord(char) <= 0xFE0F:
            continue
        width += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
    return width


def lint(text: str) -> list[tuple[int, str, str]]:
    """Return the findings as (line number, kind letter, message), in line order."""
    findings: list[tuple[int, str, str]] = []
    items: list[Item] = []
    stack: list[Item] = []
    fence: str | None = None
    after_underline = False
    previous = "text"  # the kind of the line before: "text", "blank" or "sep"
    last_text = ""  # the line before, when it held text
    options: int | None = None  # the indent of the open Decide item's option lines
    blank_under_sep: int | None = None  # a blank line under a separator, fine only if the list ends
    above = "blank"  # the line before, for tables: "blank" (or none), "row" or "text"
    topics = 0  # topic headers seen so far
    list_name: str | None = None  # the list under way, once a topic header has been seen
    first_item = False  # whether the list under way has yet to reach its first numbered item
    last_number: dict[str, int] = {}  # each list's last number, across the topics before

    def grow() -> None:
        for open_item in stack:
            open_item.lines += 1
            open_item.sep_after = None

    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip("\r")
        if fence:
            if line.lstrip(" ").startswith(fence):
                fence = None
            above = "text"
            continue
        row = bool(_ROW.match(line))
        if row and above == "text":
            findings.append((number, "l", "a table directly under a line of text; put a blank line above it"))
        elif not row and above == "row" and line.strip():
            findings.append((number, "l", "directly under a table, this line is read as one more row; put a blank line above it"))
        above = "row" if row else "text" if line.strip() else "blank"
        if not line or _SPACES.match(line):
            last_text = ""
            if line and stack:
                findings.append(
                    (number, "c", f"a line of only whitespace; a gap between items is the indent then U+{ord(SEPARATOR):04X}")
                )
            if previous == "sep":
                blank_under_sep = number
            previous = "blank"
            continue
        sep = _SEP.match(line)
        ends_list = bool(stack) and not _ITEM.match(line) and _indent(line) < stack[0].column
        if blank_under_sep is not None and not (ends_list and not sep):
            findings.append((blank_under_sep, "e", "blank line under a separator line, inside the list, renders a double gap"))
        blank_under_sep = None
        if row and stack and not ends_list and not (previous == "text" and _ROW.match(last_text)):
            findings.append(
                (number, "k", "a table inside a list item prints as raw pipe rows; end the list and put the table after it")
            )
        if ends_list and not sep and previous != "blank":
            findings.append(
                (number, "j", "directly under a list, Markdown reads this as more of its last item; put a blank line before it")
            )
        if sep:
            if previous == "blank":
                findings.append((number, "e", "blank line above a separator line renders a double gap"))
            previous = "sep"
            last_text = ""
            indent = len(sep.group(1))
            if options is not None and indent <= options:
                options = None
            if after_underline:
                findings.append((number, "b", "separator right under a header's underline"))
                continue
            while stack and stack[-1].indent >= indent:
                stack.pop()
            if not stack:
                findings.append((number, "d", f"separator at indent {indent} outside any list item"))
                continue
            owner = stack[-1]
            if owner.column != indent:
                findings.append(
                    (number, "d", f"separator at indent {indent}; its list's items, from line {owner.line}, are at {owner.column}")
                )
            owner.sep_after = number
            continue
        previous = "text"
        after_underline = False
        header, last_text = last_text, line
        if _UNDERLINE.match(line):
            stack.clear()
            options = None
            after_underline = True
            want, got = _width(header.rstrip()), len(line.strip())
            if header and got != want:
                findings.append((number, "i", f"underline of {got}; the header above it is {want} columns wide"))
            rule = line.strip()[0]
            topics += rule == TOPIC_RULE
            named = _LIST_NAME.search(header) if rule == "▔" and topics else None
            list_name, first_item = (named.group(1), True) if named else (None, False)
            continue
        option = _OPTION.match(line)
        if option:
            options = len(option.group(1))
            if _YES_NO & {option.group(2), option.group(3)}:
                findings.append(
                    (number, "n", "an option is 🔘 or 🔲 lettered from A; write a yes-or-no question as 🔘 A. and 🔘 B.")
                )
        item = _ITEM.match(line)
        if item:
            indent = len(item.group(1))
            if options is not None:
                if indent >= options:
                    findings.append(
                        (number, "h", "a list among a Decide item's options captures every line after it; write the note as plain lines")
                    )
                else:
                    options = None
            while stack and stack[-1].indent > indent:
                stack.pop()
            if list_name and item.group(2)[0].isdigit() and all(s.indent >= indent for s in stack):
                count = int(item.group(2)[:-1])
                want = last_number.get(list_name, 0) + 1
                if first_item and list_name in last_number and count != want:
                    findings.append(
                        (number, "m", f"{list_name} numbers on across topics; this list starts at {want}, not {count}")
                    )
                first_item = False
                last_number[list_name] = count
            new = Item(number, indent, indent + len(item.group(2)) + len(item.group(3)))
            summary = _SUMMARY.match(line, item.end()) if item.group(2)[0].isdigit() else None
            if summary and line[summary.end() :].strip():
                findings.append((number, "f", "text after the bold summary; it goes on the line beneath"))
            new.unbroken = bool(summary) and not line[summary.end() :].strip() and not line.endswith("  ")
            if stack and stack[-1].indent == indent:
                prev = stack.pop()
                new.prev, new.sep_before = prev, prev.sep_after
            grow()
            stack.append(new)
            items.append(new)
            continue
        indent = _indent(line)
        if options is not None and indent < options:
            options = None
        while stack and indent <= stack[-1].indent:
            stack.pop()
        grow()
        fence_open = _FENCE.match(line)
        if fence_open:
            fence = fence_open.group(1)

    for new in items:
        if new.unbroken and new.lines > 1:
            findings.append((new.line, "g", "summary line needs a hard line break, 2 trailing spaces"))
        prev = new.prev
        if prev is None:
            continue
        multi = prev.lines > 1 or new.lines > 1
        if multi and new.sep_before is None:
            which = f"item at line {prev.line}" if prev.lines > 1 else "this item"
            findings.append((new.line, "a", f"no separator line before this item; the {which} is multi-line"))
        elif not multi and new.sep_before is not None:
            findings.append((new.sep_before, "b", f"separator between one-line items at lines {prev.line} and {new.line}"))
    return sorted(findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("file", nargs="?", help="the draft response; stdin when left out")
    args = parser.parse_args(argv)
    if args.file:
        with open(args.file, encoding="utf-8") as handle:
            text = handle.read()
    else:
        text = sys.stdin.read()
    findings = lint(text)
    for number, kind, message in findings:
        print(f"{number}: [{kind}] {message}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
