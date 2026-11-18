#!/usr/bin/env python3
"""Tests for which_browser.py: `skills-dev test coding-agent-browser-selection`.

Standard library only, and no osascript, open or mdfind: the parsing and output are pure
functions, main takes the platform and the running browsers' windows as arguments, and `resolve`
and `wake` take the command runner, here FakeMac, and `sleep`.
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import plistlib
import re
import tempfile
import unittest

import which_browser

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


CHROME_ID = "com.google.Chrome"


def make_app(root: pathlib.Path, name: str, info: bytes) -> pathlib.Path:
    """A fake `<name>.app` bundle under root whose Info.plist holds `info`."""
    contents = root / f"{name}.app" / "Contents"
    contents.mkdir(parents=True)
    (contents / "Info.plist").write_bytes(info)
    return root / f"{name}.app"


def info_plist(bundle_id: str) -> bytes:
    return plistlib.dumps({"CFBundleIdentifier": bundle_id, "CFBundleName": "x"})


class FakeMac:
    """Stands in for `osascript`, `open` and `mdfind`, holding one app's state.

    It fails the test when a script names any app but its own, or holds a `tell` not guarded by
    `is running` in the same script, since telling a stopped app launches it.
    """

    def __init__(
        self,
        bundle_id: str = CHROME_ID,
        running: bool = True,
        windows: tuple[str, ...] = (),
        found: tuple[str, ...] | None = (),
        launch_opens_window: bool = True,
        starts: bool = True,
        opens: bool = True,
        answers: bool = True,
        window_id: str = "300",
    ) -> None:
        self.bundle_id = bundle_id
        self.running = running
        self.windows = list(windows)
        self.found = found
        self.launch_opens_window = launch_opens_window
        self.starts = starts
        self.opens = opens
        self.answers = answers
        self.window_id = window_id
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str]) -> str | None:
        self.calls.append(argv)
        if argv[0] == "mdfind":
            return None if self.found is None else "".join(f"{path}\n" for path in self.found)
        if argv[:2] == ["open", "-g"]:
            if not self.opens:
                return None
            self.running = self.starts
            if self.starts and self.launch_opens_window:
                self.windows.append("200")
            return ""
        assert argv[:2] == ["osascript", "-e"], argv
        script = argv[2]
        target = f'application id "{self.bundle_id}"'
        assert set(re.findall(r'application id "[^"]*"', script)) == {target}, script
        if script == f"{target} is running":
            return f"{str(self.running).lower()}\n"
        expression = re.fullmatch(
            rf"if {re.escape(target)} is running then\n"
            rf"    tell {re.escape(target)} to return \((.*)\) as text\n"
            rf'else\n    return "{which_browser.STOPPED}"\nend if',
            script,
        )
        assert expression, f"an unguarded script: {script}"
        if not self.running:
            return f"{which_browser.STOPPED}\n"
        if not self.answers:
            return None
        return f"{self.evaluate(expression.group(1))}\n"

    def evaluate(self, expression: str) -> str:
        if expression == "count windows":
            return str(len(self.windows))
        if expression == "id of window 1":
            return self.windows[0]
        if expression == "id of (make new window)":
            self.windows.append(self.window_id)
            return self.window_id
        raise AssertionError(f"unexpected expression: {expression}")

    def commands(self) -> list[str]:
        return [argv[0] for argv in self.calls]

    def made_windows(self) -> int:
        return sum(1 for argv in self.calls if "(make new window)" in argv[-1])


class FakeClock:
    """A clock that moves only when slept on, recording each sleep."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class AppsTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        self.chrome = make_app(self.root, "Google Chrome", info_plist(CHROME_ID))
        self.chrome_app = which_browser.App("Google Chrome", CHROME_ID, str(self.chrome))


class ResolveTest(AppsTest):
    def test_a_path_is_read_from_its_info_plist_without_spotlight(self) -> None:
        mac = FakeMac()
        self.assertEqual(which_browser.resolve(str(self.chrome), mac), (self.chrome_app, ""))
        self.assertEqual(mac.calls, [])

    def test_a_name_is_found_with_spotlight_by_its_bundle_file_name(self) -> None:
        mac = FakeMac(found=(str(self.chrome),))
        self.assertEqual(which_browser.resolve("Google Chrome", mac), (self.chrome_app, ""))
        self.assertEqual(mac.calls, [["mdfind", which_browser.app_query("Google Chrome")]])
        self.assertIn('kMDItemFSName == "Google Chrome.app"', mac.calls[0][1])

    def test_an_unknown_name_stops(self) -> None:
        app, why = which_browser.resolve("Nowhere Browser", FakeMac())
        self.assertIsNone(app)
        self.assertIn("no app named Nowhere Browser.app", why)

    def test_a_name_matching_several_apps_stops_and_lists_them(self) -> None:
        other = make_app(self.root / "nix", "Google Chrome", info_plist(CHROME_ID))
        app, why = which_browser.resolve("Google Chrome", FakeMac(found=(str(self.chrome), str(other))))
        self.assertIsNone(app)
        self.assertIn("2 apps named Google Chrome.app", why)
        self.assertIn(str(other), why)

    def test_a_name_spotlight_lists_twice_is_one_app(self) -> None:
        mac = FakeMac(found=(str(self.chrome), str(self.chrome)))
        self.assertEqual(which_browser.resolve("Google Chrome", mac)[0], self.chrome_app)

    def test_an_app_that_is_no_browser_this_script_reads_stops(self) -> None:
        other = make_app(self.root, "Calculator", info_plist("com.apple.calculator"))
        app, why = which_browser.resolve(str(other), FakeMac())
        self.assertIsNone(app)
        self.assertIn("com.apple.calculator", why)

    def test_a_bundle_without_a_readable_bundle_id_stops(self) -> None:
        broken = make_app(self.root, "Broken", b"<plist><dict><key>")
        no_id = make_app(self.root, "NoId", plistlib.dumps({"CFBundleName": "x"}))
        for path in (broken, no_id, self.root / "Missing.app"):
            with self.subTest(path=path):
                app, why = which_browser.resolve(str(path), FakeMac())
                self.assertIsNone(app)
                self.assertIn("has no bundle id", why)

    def test_a_name_spotlight_cannot_quote_is_refused_without_asking_it(self) -> None:
        for name in ('Bad"Name', "Wild*", "Back\\slash", ""):
            with self.subTest(name=name):
                mac = FakeMac()
                self.assertIsNone(which_browser.resolve(name, mac)[0])
                self.assertEqual(mac.calls, [])

    def test_a_bare_bundle_name_is_a_name_not_a_relative_path(self) -> None:
        mac = FakeMac(found=(str(self.chrome),))
        self.assertEqual(which_browser.resolve("Google Chrome.app", mac)[0], self.chrome_app)
        self.assertEqual(mac.calls, [["mdfind", which_browser.app_query("Google Chrome")]])

    def test_a_path_from_home_is_expanded(self) -> None:
        home = pathlib.Path.home()
        app, why = which_browser.resolve("~/no-such-dir/Google Chrome.app", FakeMac())
        self.assertIsNone(app)
        self.assertIn(str(home / "no-such-dir"), why)

    def test_a_failed_spotlight_stops(self) -> None:
        app, why = which_browser.resolve("Google Chrome", FakeMac(found=None))
        self.assertIsNone(app)
        self.assertIn("mdfind", why)


class WakeTest(AppsTest):
    def wake(self, mac: FakeMac, mode: str) -> tuple[int, str]:
        self.clock = FakeClock()
        return which_browser.wake(self.chrome_app, mode, mac, self.clock.sleep, self.clock, settle=9.0)

    def test_window_opens_one_in_a_running_app_with_none_then_settles(self) -> None:
        mac = FakeMac(running=True)
        self.assertEqual(self.wake(mac, "window"), (0, "Google Chrome\t300\topened"))
        self.assertEqual((mac.made_windows(), mac.windows), (1, ["300"]))
        self.assertEqual(self.clock.sleeps, [9.0])

    def test_an_app_with_a_window_is_left_as_it_is_without_settling(self) -> None:
        for mode in ("window", "launch"):
            with self.subTest(mode=mode):
                mac = FakeMac(running=True, windows=("101", "102"))
                self.assertEqual(self.wake(mac, mode), (0, "Google Chrome\t101\talready-open"))
                self.assertEqual((mac.made_windows(), self.clock.sleeps), (0, []))

    def test_window_never_launches_a_stopped_app(self) -> None:
        mac = FakeMac(running=False)
        status, why = self.wake(mac, "window")
        self.assertEqual(status, 1)
        self.assertIn("not running", why)
        self.assertEqual(mac.commands(), ["osascript"])
        self.assertFalse(mac.running)

    def test_launch_starts_a_stopped_app_from_its_path_in_the_background(self) -> None:
        mac = FakeMac(running=False, launch_opens_window=True)
        self.assertEqual(self.wake(mac, "launch"), (0, "Google Chrome\t200\tlaunched"))
        self.assertIn(["open", "-g", str(self.chrome)], mac.calls)
        self.assertEqual(mac.made_windows(), 0)

    def test_launch_opens_a_window_when_the_launched_app_has_none_by_the_deadline(self) -> None:
        mac = FakeMac(running=False, launch_opens_window=False)
        self.assertEqual(self.wake(mac, "launch"), (0, "Google Chrome\t300\tlaunched"))
        self.assertEqual(mac.made_windows(), 1)
        polls = self.clock.sleeps[:-1]
        self.assertEqual(sum(polls), which_browser.LAUNCH_SECONDS)
        self.assertEqual(self.clock.sleeps[-1], 9.0)

    def test_launch_that_cannot_open_the_app_stops(self) -> None:
        mac = FakeMac(running=False, opens=False)
        status, why = self.wake(mac, "launch")
        self.assertEqual(status, 1)
        self.assertIn("could not launch", why)

    def test_an_empty_window_id_is_a_failure(self) -> None:
        status, why = self.wake(FakeMac(running=True, window_id=""), "window")
        self.assertEqual(status, 1)
        self.assertIn("window id", why)

    def test_an_app_that_quits_midway_is_not_relaunched(self) -> None:
        mac = FakeMac(running=True)
        first = mac.__call__

        def quits(argv: list[str]) -> str | None:
            out = first(argv)
            mac.running = False  # quits right after answering `is running`
            return out

        status, why = which_browser.wake(self.chrome_app, "window", quits, lambda _: None)
        self.assertEqual(status, 1)
        self.assertIn("quit", why)
        self.assertEqual(mac.made_windows(), 0)

    def test_launch_opens_only_a_window_in_a_running_app(self) -> None:
        mac = FakeMac(running=True)
        self.assertEqual(self.wake(mac, "launch"), (0, "Google Chrome\t300\topened"))
        self.assertNotIn("open", mac.commands())

    def test_launch_gives_up_on_an_app_that_never_starts(self) -> None:
        mac = FakeMac(running=False, starts=False)
        status, why = self.wake(mac, "launch")
        self.assertEqual(status, 1)
        self.assertIn("did not start", why)
        self.assertEqual(mac.made_windows(), 0)

    def test_an_app_that_does_not_answer_points_at_the_automation_permission(self) -> None:
        status, why = self.wake(FakeMac(running=True, answers=False), "window")
        self.assertEqual(status, 1)
        self.assertIn("Automation permission", why)

    def test_off_does_nothing(self) -> None:
        mac = FakeMac(running=False)
        self.assertEqual(self.wake(mac, "off")[0], 1)
        self.assertEqual(mac.calls, [])


class SubcommandMainTest(AppsTest):
    def run_main(self, mac: FakeMac, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            clock = FakeClock()
            status = which_browser.main(["which_browser.py", *args], "darwin", lambda: FOUND, mac, clock.sleep, clock)
        return status, out.getvalue(), err.getvalue()

    def test_wake_without_an_app_is_a_usage_error_naming_app(self) -> None:
        for args in (("wake",), ("wake", "--mode", "launch")):
            with self.subTest(args=args):
                mac = FakeMac()
                status, out, err = self.run_main(mac, *args)
                self.assertEqual((status, out, mac.calls), (2, "", []))
                self.assertIn("usage:", err)
                self.assertIn("--app", err)

    def test_wake_launch_starts_the_app_passed(self) -> None:
        mac = FakeMac(running=False)
        self.assertEqual(
            self.run_main(mac, "wake", "--app", str(self.chrome), "--mode", "launch")[:2],
            (0, "Google Chrome\t200\tlaunched\n"),
        )

    def test_wake_help_exits_0(self) -> None:
        status, out, _ = self.run_main(FakeMac(), "wake", "--help")
        self.assertEqual(status, 0)
        self.assertIn("--settle", out)

    def test_resolve_prints_name_bundle_id_and_path(self) -> None:
        status, out, _ = self.run_main(FakeMac(), "resolve", "--app", str(self.chrome))
        self.assertEqual((status, out), (0, f"Google Chrome\t{CHROME_ID}\t{self.chrome}\n"))

    def test_wake_by_name_prints_the_window(self) -> None:
        mac = FakeMac(running=True, found=(str(self.chrome),))
        self.assertEqual(self.run_main(mac, "wake", "--app", "Google Chrome")[:2], (0, "Google Chrome\t300\topened\n"))

    def test_wake_defaults_to_window(self) -> None:
        mac = FakeMac(running=False)
        status, _, err = self.run_main(mac, "wake", "--app", str(self.chrome))
        self.assertEqual(status, 1)
        self.assertIn("never launches", err)
        self.assertNotIn("open", mac.commands())

    def test_wake_off_asks_nothing_not_even_spotlight(self) -> None:
        mac = FakeMac()
        self.assertEqual(self.run_main(mac, "wake", "--app", "Google Chrome", "--mode", "off")[0], 1)
        self.assertEqual(mac.calls, [])

    def test_an_unknown_name_stops_before_any_app_is_asked(self) -> None:
        mac = FakeMac()
        status, out, err = self.run_main(mac, "wake", "--app", "Nowhere Browser", "--mode", "launch")
        self.assertEqual((status, out), (1, ""))
        self.assertIn("no app named", err)
        self.assertEqual(mac.commands(), ["mdfind"])

    def test_bad_subcommand_usage_exits_2(self) -> None:
        for args in (
            ("wake", "--app"),
            ("wake", "--app", "x", "--mode", "sometimes"),
            ("wake", "--app", "x", "--project-dir", "."),
            ("resolve",),
        ):
            with self.subTest(args=args):
                mac = FakeMac()
                status, out, err = self.run_main(mac, *args)
                self.assertEqual((status, out, mac.calls), (2, "", []))
                self.assertIn("usage:", err)


if __name__ == "__main__":
    unittest.main()
