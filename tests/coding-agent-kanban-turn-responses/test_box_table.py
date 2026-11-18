#!/usr/bin/env python3
"""Tests for box_table.py: `skills-dev test coding-agent-kanban-turn-responses`.

Standard library only. main takes its stdin as a string and returns its status and text.
"""

from __future__ import annotations

import unittest

import box_table


class WidthTest(unittest.TestCase):
    def test_wide_characters_count_two_and_combining_marks_none(self) -> None:
        self.assertEqual(box_table.width("ab"), 2)
        self.assertEqual(box_table.width("✅"), 2)
        self.assertEqual(box_table.width("日本"), 4)
        self.assertEqual(box_table.width("é"), 1)


class DrawTest(unittest.TestCase):
    def test_columns_pad_to_the_widest_cell_counting_an_emoji_as_two(self) -> None:
        self.assertEqual(
            box_table.main([], "Run\tState\n1\t✅\n\n22\tfailed\n"),
            (
                0,
                "\n".join(
                    (
                        "┌─────┬────────┐",
                        "│ Run │ State  │",
                        "├─────┼────────┤",
                        "│ 1   │ ✅     │",
                        "│ 22  │ failed │",
                        "└─────┴────────┘",
                    )
                ),
            ),
        )

    def test_right_names_the_columns_to_right_align(self) -> None:
        status, text = box_table.main(["--right", "0"], "Run\tState\n1\tok\n")
        self.assertEqual((status, text.splitlines()[3]), (0, "│   1 │ ok    │"))

    def test_a_header_alone_draws_an_empty_body(self) -> None:
        self.assertEqual(box_table.main([], "A\n")[1].splitlines(), ["┌───┐", "│ A │", "├───┤", "└───┘"])


class ErrorTest(unittest.TestCase):
    def test_a_row_of_the_wrong_length_exits_1_naming_it(self) -> None:
        self.assertEqual(
            box_table.main([], "a\tb\n1\t2\n3\n"), (1, "box_table.py: row 3 has 1 cells, the header has 2")
        )

    def test_no_rows_exits_1(self) -> None:
        self.assertEqual(box_table.main([], "\n  \n"), (1, "box_table.py: no rows on stdin"))

    def test_a_bad_right_spec_exits_1(self) -> None:
        status, text = box_table.main(["--right", "x"], "a\n")
        self.assertEqual(status, 1)
        self.assertTrue(text.startswith("box_table.py: "), text)


if __name__ == "__main__":
    unittest.main()
