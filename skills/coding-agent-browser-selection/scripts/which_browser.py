#!/usr/bin/env python3
"""Find which browser window holds a tab whose URL contains a marker, and wake the preferred browser.

Why it exists: several browsers can have the Claude in Chrome extension connected, and
`list_connected_browsers` names them only "Browser 1", "Browser 2", in no stable order. Put a
unique marker in the session's tab URL, then run this script to learn which app and window that
tab is in. When the preferred app runs with no window, its extension drops off that list; `wake`
gives it a window, so it connects again.

It asks each running Chromium-family app through AppleScript, so it works on macOS only. It checks
`application "<app>" is running` first and never launches an app, except `wake --mode launch`. An
app that isn't running, isn't installed or doesn't answer is skipped.

Usage:
    which_browser.py MARKER          print each window with a tab whose URL contains
                                     MARKER
    which_browser.py --list          print every window of every running app
    which_browser.py --list --urls   also print each tab's URL, under its window
    which_browser.py resolve --app APP
                                     print the app's name as this script prints it,
                                     its bundle id and its path
    which_browser.py wake --app APP [--mode window|launch|off] [--settle SECONDS]
                          [--never-use APP]...
                                     give APP a window if it has none; with launch,
                                     start it first if it isn't running; then wait
                                     SECONDS (15) for its extension to connect

Output is tab-separated, one window per line: app, window id, the window's given name (the name
set with "Name window..."; empty when unset), then the window's title. A tab's URL line under
`--urls` opens with a tab character. Exits 0 when MARKER is found, 1 when not, 2 on bad usage.

APP is a path to a `.app` bundle (holding a `/` or starting with `~`), or a name Spotlight finds as
`<name>.app`; it must be one of the browsers in BUNDLE_IDS. `resolve` prints its name, bundle id
and path, tab-separated. `wake` prints the app, the id of its window and what it did: `opened` a
window, `launched` the app, or `already-open` when it had a window and nothing was done. It exits
1 when it can't: the app isn't running under `window`, the mode is `off`, the name matches no app
or several, or the app doesn't answer. `--mode` defaults to `window`.

`wake` reads no preferences file: the agent, which reads the skill's preferences, passes the
`Preferred app` as `--app`, the `Wake` setting as `--mode`, and each `Never use` entry as a
`--never-use`. An app matching an entry, ignoring case and a `.app` suffix, by its name, bundle id,
path or bundle file name, or by the bundle id at an entry's path, is refused with exit 2 before any
app is asked anything. An entry naming none of the browsers in BUNDLE_IDS is ignored with a warning.
"""

from __future__ import annotations

import argparse
import collections
import plistlib
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable
from xml.parsers.expat import ExpatError

# Each browser this script reads, by bundle id, with its name as this script prints it.
BUNDLE_IDS = {
    "com.google.Chrome": "Google Chrome",
    "com.brave.Browser": "Brave Browser",
    "com.microsoft.edgemac": "Microsoft Edge",
    "org.chromium.Chromium": "Chromium",
    "com.vivaldi.Vivaldi": "Vivaldi",
    "company.thebrowser.Browser": "Arc",
}
APPS = tuple(BUNDLE_IDS.values())

WAKE_MODES = ("window", "launch", "off")
DEFAULT_WAKE_MODE = "window"
POLL_SECONDS = 0.5
LAUNCH_SECONDS = 15.0  # how long a launched app has to report a window
SETTLE_SECONDS = 15.0  # the extension was seen to connect again about 10 s after a window opened
STOPPED = "stopped"  # what a guarded script returns when its app isn't running

# One line per window: id, given name, title, then the window's tab URLs, all tab-separated.
# The app name is spliced in from APPS only; the marker never enters the script text. Inside a
# `tell` block a browser's dictionary makes `tab` mean a browser tab, so the separators are set
# before it.
WINDOWS_SCRIPT = """
on safeText(v)
    try
        if v is missing value then return ""
        return v as text
    on error
        return ""
    end try
end safeText

set sep to character id 9
set eol to character id 10
tell application "{app}"
    set out to ""
    repeat with w in windows
        set wid to ""
        set gname to ""
        set wname to ""
        set urls to {{}}
        try
            set wid to (id of w) as text
        end try
        try
            set gname to my safeText(given name of w)
        end try
        try
            set wname to my safeText(name of w)
        end try
        try
            set urls to URL of tabs of w
        end try
        set out to out & wid & sep & gname & sep & wname
        repeat with u in urls
            set out to out & sep & my safeText(contents of u)
        end repeat
        set out to out & eol
    end repeat
    return out
end tell
"""


Run = Callable[[list[str]], "str | None"]


def command(argv: list[str]) -> str | None:
    """Run a command, returning its output, or None if it failed."""
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def osascript(script: str, run: Run = command) -> str | None:
    """Run an AppleScript, returning its output, or None if it failed."""
    return run(["osascript", "-e", script])


def is_running(app: str) -> bool:
    return (osascript(f'application "{app}" is running') or "").strip() == "true"


Window = tuple[str, str, str, list[str]]  # id, given name, title, tab URLs


def parse_windows(out: str) -> list[Window]:
    """Each window of WINDOWS_SCRIPT's output: one tab-separated line per window, blank lines skipped."""
    rows = []
    for line in out.splitlines():
        if not line:
            continue
        fields = line.split("\t")
        fields += [""] * (3 - len(fields))
        rows.append((fields[0], fields[1], fields[2], fields[3:]))
    return rows


def windows(app: str) -> list[Window] | None:
    """Return (id, given name, title, tab URLs) for each window of a running app."""
    out = osascript(WINDOWS_SCRIPT.format(app=app))
    return None if out is None else parse_windows(out)


def running_apps() -> list[tuple[str, list[Window]]]:
    found = []
    for app in APPS:
        if not is_running(app):
            continue
        rows = windows(app)
        if rows is None:
            print(f"which_browser: {app} is running but did not answer; skipped", file=sys.stderr)
            continue
        found.append((app, rows))
    return found


def list_lines(found: list[tuple[str, list[Window]]], urls: bool) -> list[str]:
    """`--list` output: one line per window, and under `--urls` each tab's URL after a tab."""
    return [
        line
        for app, rows in found
        for wid, gname, title, tabs in rows
        for line in (f"{app}\t{wid}\t{gname}\t{title}", *((f"\t{url}" for url in tabs) if urls else ()))
    ]


def marker_lines(found: list[tuple[str, list[Window]]], marker: str) -> list[str]:
    """One line per window holding a tab whose URL contains the marker."""
    return [
        f"{app}\t{wid}\t{gname}\t{title}"
        for app, rows in found
        for wid, gname, title, tabs in rows
        if any(marker in url for url in tabs)
    ]


# An app resolved from a path or a name: its name as this script prints it, bundle id and path.
App = collections.namedtuple("App", ("name", "bundle_id", "path"))


def bundle_id_at(path: Path) -> str | None:
    """The bundle id in an app bundle's Info.plist, or None if it has none."""
    try:
        with open(path / "Contents" / "Info.plist", "rb") as plist:
            info = plistlib.load(plist)
    except (OSError, ValueError, ExpatError):
        return None
    bundle_id = info.get("CFBundleIdentifier") if isinstance(info, dict) else None
    return bundle_id if isinstance(bundle_id, str) and bundle_id else None


def app_query(name: str) -> str:
    """The Spotlight query for application bundles named `<name>.app`."""
    return f'kMDItemContentType == "com.apple.application-bundle" && kMDItemFSName == "{name}.app"'


def resolve(app: str, run: Run = command) -> tuple[App | None, str]:
    """The app a path or a name stands for, or None and why not.

    A path is read as it is; a name is looked up with Spotlight, and must match exactly one app.
    """
    name = app.removesuffix(".app")
    if "/" in app or app.startswith("~"):
        paths = [Path(app).expanduser()]
    elif not name or any(c in name for c in '"\\*'):
        return None, f"not an app name: {app!r}"
    else:
        app = name
        out = run(["mdfind", app_query(app)])
        if out is None:
            return None, f"Spotlight (mdfind) failed looking up {app}; set its path instead"
        paths = [Path(line) for line in dict.fromkeys(out.splitlines()) if line]
        if not paths:
            return None, f"no app named {app}.app found by Spotlight; set its path instead"
        if len(paths) > 1:
            found = ", ".join(str(path) for path in paths)
            return None, f"{len(paths)} apps named {app}.app: {found}; set the path of the one to use"
    path = paths[0]
    bundle_id = bundle_id_at(path)
    if bundle_id is None:
        return None, f"{path} has no bundle id; is it an app?"
    browser = BUNDLE_IDS.get(bundle_id)
    if browser is None:
        return None, f"{path} ({bundle_id}) is none of the browsers this script reads: {', '.join(APPS)}"
    return App(browser, bundle_id, str(path)), ""


def entry_keys(entry: str) -> set[str]:
    """A `--never-use` entry folded to lower case, with and without a `.app` suffix, as `resolve`
    takes a name either way."""
    folded = entry.casefold()
    return {folded, folded.removesuffix(".app")}


def entry_bundle_id(entry: str) -> str | None:
    """The bundle id a `--never-use` entry stands for: a browser's bundle id or name, in any case,
    or the bundle id of the app at an entry's path; else None."""
    known = {key.casefold(): bundle_id for bundle_id, name in BUNDLE_IDS.items() for key in (bundle_id, name)}
    named = next((known[key] for key in entry_keys(entry) if key in known), None)
    if named is not None or not ("/" in entry or entry.startswith("~")):
        return named
    try:
        return bundle_id_at(Path(entry).expanduser())
    except RuntimeError:  # `~user` naming no user
        return None


def never_to_use(app: App, entries: list[str]) -> str | None:
    """The first `--never-use` entry the app matches, ignoring case and a `.app` suffix: by its name,
    bundle id, path or bundle file name, or by the bundle id at an entry's path; else None."""
    own = {key.casefold() for key in (app.name, app.bundle_id, app.path, Path(app.path).name.removesuffix(".app"))}
    return next((e for e in entries if entry_keys(e) & own or entry_bundle_id(e) == app.bundle_id), None)


def guarded(target: str, expression: str) -> str:
    """An AppleScript that evaluates `expression` in the app only if it is running, else returns
    STOPPED. Checking and acting in one script leaves no gap in which the app could quit and a
    `tell` launch it again."""
    return (
        f"if {target} is running then\n"
        f"    tell {target} to return ({expression}) as text\n"
        "else\n"
        f'    return "{STOPPED}"\n'
        "end if"
    )


def wake(
    app: App,
    mode: str,
    run: Run = command,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    settle: float = SETTLE_SECONDS,
) -> tuple[int, str]:
    """Give the app a window if it has none, launching it first only under `launch`.

    Returns the exit status and a line: on 0, the app, its window id and what was done; else why
    not. It addresses the app by bundle id, and acts on no other app. After opening a window or
    launching the app it waits `settle` seconds, for the extension to connect again.
    """
    target = f'application id "{app.bundle_id}"'

    def ask(expression: str) -> str | None:
        out = osascript(guarded(target, expression), run)
        return None if out is None else out.strip()

    def has_window() -> bool:
        return ask("count windows") not in (None, STOPPED, "0")

    if mode == "off":
        return 1, f"wake is off; {app.name} left as it is"
    launched = (osascript(f"{target} is running", run) or "").strip() != "true"
    if launched:
        if mode != "launch":
            return 1, f"{app.name} is not running, and wake --mode window never launches it"
        if run(["open", "-g", app.path]) is None:
            return 1, f"could not launch {app.path}"
        deadline = clock() + LAUNCH_SECONDS
        while not has_window() and clock() < deadline:
            sleep(POLL_SECONDS)
    count = ask("count windows")
    if count == STOPPED:
        return 1, f"{app.name} did not start within {LAUNCH_SECONDS:g} s" if launched else f"{app.name} quit"
    if count is None or not count.isdigit():
        return 1, f"{app.name} did not answer; the terminal may lack Automation permission for it"
    opening = count == "0"
    window = ask("id of (make new window)" if opening else "id of window 1")
    if not window or window == STOPPED:
        return 1, f"{app.name} did not give a window id"
    action = "launched" if launched else "opened" if opening else "already-open"
    if action != "already-open":
        sleep(settle)
    return 0, f"{app.name}\t{window}\t{action}"


def subcommand(
    args: list[str], run: Run, sleep: Callable[[float], None], clock: Callable[[], float]
) -> int:
    """`resolve` and `wake`, parsed with argparse, which prints usage and returns 2 on bad usage."""
    parser = argparse.ArgumentParser(prog="which_browser.py")
    commands = parser.add_subparsers(dest="command", required=True)
    resolving = commands.add_parser("resolve", help="print an app's name, bundle id and path")
    resolving.add_argument("--app", required=True, help="a path to a .app bundle, or an app name")
    waking = commands.add_parser("wake", help="give the app a window if it has none")
    waking.add_argument("--app", required=True, help="a path to a .app bundle, or an app name")
    waking.add_argument(
        "--mode", choices=WAKE_MODES, default=DEFAULT_WAKE_MODE, help=f"what wake may do (default: {DEFAULT_WAKE_MODE})"
    )
    waking.add_argument(
        "--settle",
        type=float,
        default=SETTLE_SECONDS,
        metavar="SECONDS",
        help="how long to wait after opening a window, for the extension to connect",
    )
    waking.add_argument(
        "--never-use",
        action="append",
        default=[],
        metavar="APP",
        help="an app never to act in, by name, bundle id or path; repeatable. wake refuses the app it"
        " would act in, with exit 2, when it matches one of them",
    )
    try:
        parsed = parser.parse_args(args)
    except SystemExit as exit_:
        return exit_.code if isinstance(exit_.code, int) else 2
    if parsed.command == "resolve":
        app, why = resolve(parsed.app, run)
        if app is None:
            print(f"which_browser: {why}", file=sys.stderr)
            return 1
        print(f"{app.name}\t{app.bundle_id}\t{app.path}")
        return 0
    if parsed.mode == "off":
        print("which_browser: wake is off; nothing done", file=sys.stderr)
        return 1
    app, why = resolve(parsed.app, run)
    if app is None:
        print(f"which_browser: {why}", file=sys.stderr)
        return 1
    refused = never_to_use(app, parsed.never_use)
    if refused is not None:
        print(f"which_browser: refusing to wake {app.name}: it matches --never-use {refused}", file=sys.stderr)
        return 2
    for entry in parsed.never_use:
        if entry_bundle_id(entry) is None:
            print(f"which_browser: --never-use {entry} names no browser this script reads; ignored", file=sys.stderr)
    status, line = wake(app, parsed.mode, run, sleep, clock, parsed.settle)
    if status == 0:
        print(line)
    else:
        print(f"which_browser: {line}", file=sys.stderr)
    return status


def main(
    argv: list[str],
    platform: str = sys.platform,
    apps: Callable[[], list[tuple[str, list[Window]]]] = running_apps,
    run: Run = command,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    """The command line; `platform`, `apps` (the running browsers' windows), `run` (every command
    `resolve` and `wake` run), `sleep` and `clock` are passed in by tests."""
    if platform != "darwin":
        print("which_browser: macOS only (it uses AppleScript)", file=sys.stderr)
        return 2
    args = argv[1:]
    if args and args[0] in ("resolve", "wake"):
        return subcommand(args, run, sleep, clock)
    if args and args[0] == "--list":
        for line in list_lines(apps(), "--urls" in args[1:]):
            print(line)
        return 0
    if len(args) != 1 or not args[0] or args[0].startswith("-"):
        print(__doc__.split("Usage:")[1].split("Output")[0].rstrip(), file=sys.stderr)
        return 2
    hits = marker_lines(apps(), args[0])
    for line in hits:
        print(line)
    return 0 if hits else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
