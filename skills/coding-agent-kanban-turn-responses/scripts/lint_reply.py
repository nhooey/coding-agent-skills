#!/usr/bin/env python3
"""Check a draft final response's list separators, item summary lines, Decisions options and
header underlines before it is sent.

Why it exists: a multi-line item is parted from the next item of its list by a line holding the
list's indent and one separator character, SEPARATOR below, and nothing else, with no blank line
on either side. An empty line between items renders no gap, and a line of spaces renders one or
none depending on its width; a U+00A0 typed there reaches the terminal as a plain space, so it is
no better. A blank line beside the separator renders a double gap, and a separator between
one-line items, or under a header's underline, is a gap that should not be there. Reading for
these by eye misses them. A numbered item opens on its bold summary alone, ending in a hard line
break, 2 trailing spaces, with its sentence on the line beneath; without the break the 2 lines run
together into one. An option's lines are plain lines of its item's paragraph, not a list, so a
`-` or `1.` list among them starts a real list, and every line after it, the later options among
them, joins its last entry and prints at its indent. A header's underline holds one character per
column of the header as it renders, its emoji counting 2.

Takes: the response on stdin, or in the FILE given. Prints one line per finding, `LINE: [k]
message`, and exits 1 if there is any, else 0:

    [a] a multi-line item followed by the next item of its list with no separator line
    [b] a separator line between 2 one-line items, or right under a header's underline
    [c] a line holding only spaces, tabs or U+00A0, but not empty, inside a list
    [d] a separator line whose indent is not its list's indent, the item's text column
    [e] a blank line directly above or below a separator line
    [f] a numbered item with text after its bold summary on the same line
    [g] a numbered item's summary line with lines under it but no hard line break
    [h] a list line among a Decisions item's options, after its first option line
    [i] a header underline whose width is not the header's

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
_UNDERLINE = re.compile(r"^\s*[▔━]+\s*$")
_FENCE = re.compile(r"^ *(```|~~~)")
_OPTION = re.compile(r"^( *)(🔘|🔲|👍|👎) [A-Z]\. ")


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
    options: int | None = None  # the indent of the open Decisions item's option lines

    def grow() -> None:
        for open_item in stack:
            open_item.lines += 1
            open_item.sep_after = None

    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip("\r")
        if fence:
            if line.lstrip(" ").startswith(fence):
                fence = None
            continue
        if not line or _SPACES.match(line):
            last_text = ""
            if line and stack:
                findings.append(
                    (number, "c", f"a line of only whitespace; a gap between items is the indent then U+{ord(SEPARATOR):04X}")
                )
            if previous == "sep":
                findings.append((number, "e", "blank line under a separator line renders a double gap"))
            previous = "blank"
            continue
        sep = _SEP.match(line)
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
            continue
        option = _OPTION.match(line)
        if option:
            options = len(option.group(1))
        item = _ITEM.match(line)
        if item:
            indent = len(item.group(1))
            if options is not None:
                if indent >= options:
                    findings.append(
                        (number, "h", "a list among a Decisions item's options captures every line after it; write the note as plain lines")
                    )
                else:
                    options = None
            while stack and stack[-1].indent > indent:
                stack.pop()
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
