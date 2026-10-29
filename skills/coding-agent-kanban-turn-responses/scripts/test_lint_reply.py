#!/usr/bin/env python3
"""Tests for lint_reply.py, run from anywhere: `python3 -I scripts/test_lint_reply.py`.

Standard library only.
"""

from __future__ import annotations

import io
import pathlib
import re
import sys
import unittest
from contextlib import redirect_stdout

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lint_reply  # noqa: E402

S = lint_reply.SEPARATOR
NBSP = lint_reply.NBSP


def decisions(gap: str) -> str:
    """A 2-item Decisions list whose items are parted by the line `gap`."""
    return (
        "🧠 **Decisions:**  \n"
        "▔▔▔▔▔▔▔▔▔▔▔▔▔\n"
        "1. **How the stock counts are stored**  \n"
        "   By store and day.\n"
        "   🔘 A. **One row per product per store**: the counts table grows by store.\n"
        "      ➕ Queries stay simple.\n"
        "      ➖ About 131 rows per product, roughly 10 million in all.\n"
        f"{gap}\n"
        "2. **Which other fast-changing data moves into rows of its own**  \n"
        "   Prices.\n"
        "   👍 Y. **Move prices too**: one migration.\n"
        "      ➕ One pattern for both.\n"
        "      ➖ A second migration to review.\n"
    )


ONE_LINE_RUN = (
    "✅ **Done:**  \n"
    "▔▔▔▔▔▔▔▔\n"
    "1. **Tokenizer fix in commit `a1b2c3d`**\n"
    "2. **Test suite, 412 passed and 0 failed**\n"
    "3. **Lint, 0 warnings**\n"
    "\n"
    "📌 **Outstanding from previous turns:**  \n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "🤔 **Waiting:**  \n"
    "- **Landing `atomic-reload`.** 🔖 0f311c94₋₃\n"
    "- **The nightly import.** 🔖 18e77cb3₋₁₇\n"
)


def kinds(text: str) -> list[tuple[int, str]]:
    return [(line, kind) for line, kind, _ in lint_reply.lint(text)]


def fenced_block(path: pathlib.Path, heading: str) -> str:
    """The first ```text block after `heading` in a Markdown file."""
    text = path.read_text(encoding="utf-8")
    after = text[text.index(heading) :]
    return re.search(r"```text\n(.*?)```", after, re.DOTALL).group(1)


class LintReplyTest(unittest.TestCase):
    def test_correct_decisions_list(self) -> None:
        self.assertEqual(kinds(decisions(f"   {S}")), [])

    def test_one_space_runs_items_together(self) -> None:
        self.assertEqual(kinds(decisions(" ")), [(8, "c"), (9, "a")])

    def test_spaces_where_the_separator_belongs(self) -> None:
        self.assertEqual(kinds(decisions("    ")), [(8, "c"), (9, "a")])

    def test_nbsp_separator(self) -> None:
        self.assertEqual(kinds(decisions(f"   {NBSP}")), [(8, "c"), (9, "a")])

    def test_empty_line_is_no_separator(self) -> None:
        self.assertEqual(kinds(decisions("")), [(9, "a")])

    def test_no_line_at_all(self) -> None:
        text = decisions("X").replace("X\n", "")
        self.assertEqual(kinds(text), [(8, "a")])

    def test_blank_lines_around_separator(self) -> None:
        self.assertEqual(kinds(decisions(f"\n   {S}\n")), [(9, "e"), (10, "e")])

    def test_one_line_items_sit_together(self) -> None:
        self.assertEqual(kinds(ONE_LINE_RUN), [])

    def test_separator_between_one_line_items(self) -> None:
        text = f"1. **One**\n   {S}\n2. **Two**\n"
        self.assertEqual(kinds(text), [(2, "b")])

    def test_separator_under_underline(self) -> None:
        text = f"✅ **Done:**  \n▔▔▔▔▔▔▔▔\n{S}\n1. **One**\n"
        self.assertEqual(kinds(text), [(3, "b")])

    def test_separator_at_wrong_indent(self) -> None:
        text = f"1. **One**  \n   a.\n  {S}\n2. **Two**\n"
        self.assertEqual(kinds(text), [(3, "d")])

    def test_multi_line_item_after_one_line_item(self) -> None:
        text = "1. **One**\n2. **Two**  \n   b.\n"
        self.assertEqual(kinds(text), [(2, "a")])

    def test_loose_item_with_blank_lines_inside(self) -> None:
        text = (
            "1. **One**  \n"
            "   a.\n"
            "\n"
            "   🔘 A. **First**: a.\n"
            "\n"
            "   🔘 B. **Second**: b.\n"
            f"   {S}\n"
            "2. **Two**\n"
        )
        self.assertEqual(kinds(text), [])

    def test_item_ending_in_nested_bullets(self) -> None:
        text = f"1. **One**  \n   a.\n   - first\n   - second\n   {S}\n2. **Two**\n"
        self.assertEqual(kinds(text), [])

    def test_nested_steps_are_their_own_list(self) -> None:
        text = (
            "1. **Rotate the keys**  \n"
            "   In the console.\n"
            "   1. Open the console,\n"
            "      then the keys page.\n"
            f"      {S}\n"
            "   2. Rotate `deploy-bot`.\n"
            f"   {S}\n"
            "2. **Rerun CI on master**\n"
        )
        self.assertEqual(kinds(text), [])

    def test_nested_steps_without_separator(self) -> None:
        text = "1. **Rotate the keys**  \n   In the console.\n   1. Open the console,\n      then the keys page.\n   2. Rotate.\n"
        self.assertEqual(kinds(text), [(5, "a")])

    def test_text_after_the_summary(self) -> None:
        self.assertEqual(kinds("1. **One:** a.\n"), [(1, "f")])

    def test_summary_line_without_hard_break(self) -> None:
        self.assertEqual(kinds("1. **One**\n   a.\n"), [(1, "g")])

    def test_bullets_and_plain_steps_keep_their_line(self) -> None:
        text = "- **Landing `atomic-reload`:** with 4 others. 🔖 0f311c94₋₃\n\n1. Open the console.\n2. Rotate the keys.\n"
        self.assertEqual(kinds(text), [])

    def test_fenced_content_is_not_read(self) -> None:
        text = f"```text\n1. **One:** a,\n   wrapped.\n   \n2. **Two:** b.\n{NBSP}\n```\n"
        self.assertEqual(kinds(text), [])

    def test_lists_parted_by_a_header_are_not_neighbours(self) -> None:
        text = "✅ **Done:**  \n▔▔▔▔▔▔▔▔\n1. **One**  \n   a.\n\n👉 **Todo:**  \n▔▔▔▔▔▔▔▔\n1. **Two**\n"
        self.assertEqual(kinds(text), [])

    def test_list_among_options_captures_the_later_options(self) -> None:
        text = (
            "1. **Which findings to fix**  \n"
            "   🔲 A. **The rebase claim**: drop \"current\".\n"
            "      ➕ True again.\n"
            "      ➖ A reviewer may still ask.\n"
            "   🔲 B. **The Cost claim**: one graph breaks it.\n"
            "   - The fix adds a clause.\n"
            "   - It also rewords the count.\n"
            "      ➕ Closes the counterexample.\n"
            "      ➖ A longer claim.\n"
            "   🔲 C. **The trigger**: needs the lock file.\n"
            "      ➕ Reproducible.\n"
            "      ➖ One more clause.\n"
        )
        self.assertEqual(kinds(text), [(6, "h"), (7, "a"), (7, "h")])

    def test_list_in_an_option_note_and_numbered_option_note(self) -> None:
        text = "1. **One**  \n   🔘 A. **First**: a.\n      - why\n      1. how\n      ➕ a.\n      ➖ b.\n"
        self.assertEqual(kinds(text), [(3, "h"), (4, "h")])

    def test_list_before_the_options_and_after_the_item(self) -> None:
        text = (
            "1. **One**  \n"
            "   - a fact\n"
            "   🔘 A. **First**: a.\n"
            "      ➕ a.\n"
            "      ➖ b.\n"
            f"   {S}\n"
            "2. **Two**  \n"
            "   - a fact\n"
        )
        self.assertEqual(kinds(text), [])

    def test_underline_widths(self) -> None:
        headers = {
            "✅ **Done:**": 8,
            "🚧 **Unfinished:**": 14,
            "📝 **Logged:**": 10,
            "🤔 **Waiting:**": 11,
            "❓ **Answers:**": 11,
            "🔍 **Review:**": 10,
            "👉 **Todo:**": 8,
            "🧠 **Decisions:**": 13,
            "📌 **Outstanding from previous turns:**": 35,
        }
        for header, width in headers.items():
            rule = "━" if header.startswith("📌") else "▔"
            with self.subTest(header=header):
                self.assertEqual(kinds(f"{header}  \n{rule * width}\n"), [])
                self.assertEqual(kinds(f"{header}  \n{rule * (width + 1)}\n"), [(2, "i")])

    def test_skill_examples_are_clean(self) -> None:
        skill = HERE.parent
        for path, heading in [(skill / "examples.md", "## A Decisions list"), (skill / "README.md", "The final response:")]:
            with self.subTest(path=path.name):
                if not path.exists():  # README.md stays in the repo, out of the installed skill
                    continue
                self.assertEqual(kinds(fenced_block(path, heading)), [])

    def test_main_exit_codes(self) -> None:
        for text, code in [(decisions(f"   {S}"), 0), (decisions(" "), 1)]:
            sys.stdin = io.StringIO(text)
            try:
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(lint_reply.main([]), code)
            finally:
                sys.stdin = sys.__stdin__


if __name__ == "__main__":
    unittest.main()
