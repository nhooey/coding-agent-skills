#!/usr/bin/env python3
"""Draw tab-separated rows from stdin as a table of box-drawing lines.

Why it exists: a reply's tables are drawn in a `text` block with `┌ ┬ ┐ ├ ┼ ┤ └ ┴ ┘ ─ │`, which join
with no gaps, and padding the columns by hand goes wrong on an emoji. This script is the one
drawer.

Takes: rows on stdin, cells separated by a tab, the first row the header, blank lines skipped.
Every row must have as many cells as the header, or the script exits 1 naming the row. A column
is padded to its widest cell, a character of east asian width W or F counting as 2 cells and a
combining mark as 0. `--right N,M` right-aligns those 0-based columns, for numbers.

    printf 'Run\tState\n1\t✅\n' | python3 scripts/box_table.py --right 0

Standard library only.
"""

from __future__ import annotations

import argparse
import sys
import unicodedata


class RowError(Exception):
    """A row whose cell count differs from the header's."""


def char_width(char: str) -> int:
    return 0 if unicodedata.combining(char) else 2 if unicodedata.east_asian_width(char) in "WF" else 1


def width(text: str) -> int:
    return sum(char_width(c) for c in text)


def pad(text: str, size: int, right: bool) -> str:
    gap = " " * (size - width(text))
    return gap + text if right else text + gap


def parse(text: str) -> tuple[tuple[str, ...], ...]:
    rows = tuple(tuple(line.split("\t")) for line in text.splitlines() if line.strip())
    bad = next(((i, r) for i, r in enumerate(rows) if len(r) != len(rows[0])), None)
    if bad:
        raise RowError(f"row {bad[0] + 1} has {len(bad[1])} cells, the header has {len(rows[0])}")
    return rows


def rule(sizes: tuple[int, ...], left: str, middle: str, right: str) -> str:
    return left + middle.join("─" * (s + 2) for s in sizes) + right


def draw(rows: tuple[tuple[str, ...], ...], right_columns: frozenset[int]) -> str:
    sizes = tuple(max(width(r[i]) for r in rows) for i in range(len(rows[0])))
    line = lambda row: "│ " + " │ ".join(  # noqa: E731
        pad(c, sizes[i], i in right_columns) for i, c in enumerate(row)
    ) + " │"
    return "\n".join(
        (
            rule(sizes, "┌", "┬", "┐"),
            line(rows[0]),
            rule(sizes, "├", "┼", "┤"),
            *(line(r) for r in rows[1:]),
            rule(sizes, "└", "┴", "┘"),
        )
    )


def right_columns(spec: str) -> frozenset[int]:
    return frozenset(int(n) for n in spec.split(",") if n.strip())


def main(argv: list[str], stdin: str) -> tuple[int, str]:
    args = argparse.ArgumentParser(prog="box_table.py", description=__doc__.split("\n")[0])
    args.add_argument("--right", default="", metavar="N,M", help="0-based columns to right-align")
    ns = args.parse_args(argv)
    try:
        rows = parse(stdin)
        result = (
            (0, draw(rows, right_columns(ns.right)))
            if rows
            else (1, "box_table.py: no rows on stdin")
        )
    except (RowError, ValueError) as error:
        result = (1, f"box_table.py: {error}")
    return result


if __name__ == "__main__":
    status, text = main(sys.argv[1:], sys.stdin.read())
    print(text, file=sys.stdout if status == 0 else sys.stderr)
    sys.exit(status)
