#!/usr/bin/env python3
"""Find which browser window holds a tab whose URL contains a marker.

Why it exists: several browsers can have the Claude in Chrome extension connected, and
`list_connected_browsers` names them only "Browser 1", "Browser 2", in no stable order. Put a
unique marker in the session's tab URL, then run this script to learn which app and window that
tab is in.

It asks each running Chromium-family app through AppleScript, so it works on macOS only. It checks
`application "<app>" is running` first and never launches an app. An app that isn't running, isn't
installed or doesn't answer is skipped.

Usage:
    which_browser.py MARKER          print each window with a tab whose URL contains
                                     MARKER
    which_browser.py --list          print every window of every running app
    which_browser.py --list --urls   also print each tab's URL, under its window

Output is tab-separated, one window per line: app, window id, the window's given name (the name
set with "Name window..."; empty when unset), then the window's title. A tab's URL line under
`--urls` opens with a tab character. Exits 0 when MARKER is found, 1 when not, 2 on bad usage.
"""

from __future__ import annotations

import subprocess
import sys

APPS = (
    "Google Chrome",
    "Brave Browser",
    "Microsoft Edge",
    "Chromium",
    "Vivaldi",
    "Arc",
)

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


def osascript(script: str) -> str | None:
    """Run an AppleScript, returning its output, or None if it failed."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
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


def is_running(app: str) -> bool:
    return (osascript(f'application "{app}" is running') or "").strip() == "true"


def windows(app: str) -> list[tuple[str, str, str, list[str]]] | None:
    """Return (id, given name, title, tab URLs) for each window of a running app."""
    out = osascript(WINDOWS_SCRIPT.format(app=app))
    if out is None:
        return None
    rows = []
    for line in out.splitlines():
        if not line:
            continue
        fields = line.split("\t")
        fields += [""] * (3 - len(fields))
        rows.append((fields[0], fields[1], fields[2], fields[3:]))
    return rows


def running_apps() -> list[tuple[str, list[tuple[str, str, str, list[str]]]]]:
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


def main(argv: list[str]) -> int:
    if sys.platform != "darwin":
        print("which_browser: macOS only (it uses AppleScript)", file=sys.stderr)
        return 2
    args = argv[1:]
    if args and args[0] == "--list":
        urls = "--urls" in args[1:]
        for app, rows in running_apps():
            for wid, gname, title, tabs in rows:
                print(f"{app}\t{wid}\t{gname}\t{title}")
                if urls:
                    for url in tabs:
                        print(f"\t{url}")
        return 0
    if len(args) != 1 or not args[0] or args[0].startswith("-"):
        print(__doc__.split("Usage:")[1].split("Output")[0].rstrip(), file=sys.stderr)
        return 2
    marker = args[0]
    hit = False
    for app, rows in running_apps():
        for wid, gname, title, tabs in rows:
            if any(marker in url for url in tabs):
                print(f"{app}\t{wid}\t{gname}\t{title}")
                hit = True
    return 0 if hit else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
