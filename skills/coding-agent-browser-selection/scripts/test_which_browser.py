#!/usr/bin/env python3
"""Tests for which_browser.py, run from anywhere: `python3 -I scripts/test_which_browser.py`.

Standard library only, and no osascript: the parsing and output are pure functions, and main takes
the platform and the running browsers' windows as arguments.
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import which_browser  # noqa: E402

# WINDOWS_SCRIPT's output for two windows: one named, with two tabs; one unnamed, with none.
OSASCRIPT_OUT = (
    "101\tWork\tInbox - Mail\thttps://mail.example.com/\thttps://x.example.com/?m=abc123\n"
    "\n"
    "102\t\tNew Tab\n"
)

FOUND = [
    ("Google Chrome", which_browser.parse_windows(OSASCRIPT_OUT)),
    ("Brave Browser", [("7", "", "Docs", ["https://docs.example.com/abc123"])]),
]


class ParseWindowsTest(unittest.TestCase):
    def test_each_line_is_id_given_name_title_then_urls(self) -> None:
        self.assertEqual(
            which_browser.parse_windows(OSASCRIPT_OUT),
            [
                ("101", "Work", "Inbox - Mail", ["https://mail.example.com/", "https://x.example.com/?m=abc123"]),
                ("102", "", "New Tab", []),
            ],
        )

    def test_a_short_line_is_padded_to_three_fields(self) -> None:
        self.assertEqual(which_browser.parse_windows("5\n"), [("5", "", "", [])])

    def test_no_output_is_no_window(self) -> None:
        self.assertEqual(which_browser.parse_windows(""), [])


class LinesTest(unittest.TestCase):
    def test_marker_names_every_window_holding_it_across_apps(self) -> None:
        self.assertEqual(
            which_browser.marker_lines(FOUND, "abc123"),
            ["Google Chrome\t101\tWork\tInbox - Mail", "Brave Browser\t7\t\tDocs"],
        )

    def test_marker_matches_urls_not_titles(self) -> None:
        self.assertEqual(which_browser.marker_lines(FOUND, "Inbox"), [])

    def test_list_without_urls_is_one_line_per_window(self) -> None:
        self.assertEqual(
            which_browser.list_lines(FOUND, urls=False),
            ["Google Chrome\t101\tWork\tInbox - Mail", "Google Chrome\t102\t\tNew Tab", "Brave Browser\t7\t\tDocs"],
        )

    def test_list_with_urls_puts_each_under_its_window(self) -> None:
        self.assertEqual(
            which_browser.list_lines(FOUND, urls=True),
            [
                "Google Chrome\t101\tWork\tInbox - Mail",
                "\thttps://mail.example.com/",
                "\thttps://x.example.com/?m=abc123",
                "Google Chrome\t102\t\tNew Tab",
                "Brave Browser\t7\t\tDocs",
                "\thttps://docs.example.com/abc123",
            ],
        )


class MainTest(unittest.TestCase):
    def run_main(self, *args: str, platform: str = "darwin") -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = which_browser.main(["which_browser.py", *args], platform, lambda: FOUND)
        return status, out.getvalue(), err.getvalue()

    def test_a_found_marker_exits_0_and_prints_its_windows(self) -> None:
        status, out, _ = self.run_main("abc123")
        self.assertEqual((status, out.splitlines()), (0, which_browser.marker_lines(FOUND, "abc123")))

    def test_a_missing_marker_exits_1_and_prints_nothing(self) -> None:
        self.assertEqual(self.run_main("nowhere")[:2], (1, ""))

    def test_list_exits_0(self) -> None:
        status, out, _ = self.run_main("--list", "--urls")
        self.assertEqual((status, out.splitlines()), (0, which_browser.list_lines(FOUND, urls=True)))

    def test_bad_usage_exits_2_with_the_usage(self) -> None:
        for args in ((), ("a", "b"), ("-x",), ("",)):
            with self.subTest(args=args):
                status, out, err = self.run_main(*args)
                self.assertEqual((status, out), (2, ""))
                self.assertIn("which_browser.py MARKER", err)

    def test_off_macos_exits_2_without_asking_any_app(self) -> None:
        def apps() -> list:
            raise AssertionError("no app may be asked off macOS")

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            status = which_browser.main(["which_browser.py", "abc123"], "linux", apps)
        self.assertEqual(status, 2)
        self.assertIn("macOS only", err.getvalue())


if __name__ == "__main__":
    unittest.main()
