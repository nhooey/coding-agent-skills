#!/usr/bin/env python3
"""Tests for browser-check-hook.sh and browser_check_hook.py: python3 -I test_browser_check_hook.py

The end-to-end tests run the bash hook with a temporary home, project and
plugin data folder, and need `bash` on PATH.
"""

from __future__ import annotations

import functools
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import browser_check_hook as hook  # noqa: E402

HOOK = HERE / "browser-check-hook.sh"
BASH = shutil.which("bash")
NOW = 1_800_000_000.0
CHECK_COMMAND = "python3 \"${CLAUDE_SKILL_DIR}/scripts/which_browser.py\" 'which-browser-3f9a1c'"


def pre(tool: str, session: str = "s1") -> dict:
    return {
        "session_id": session,
        "hook_event_name": "PreToolUse",
        "tool_name": hook.PREFIX + tool,
        "tool_input": {},
    }


def post(tool: str, session: str = "s1") -> dict:
    return {**pre(tool, session), "hook_event_name": "PostToolUse", "tool_response": {}}


def bash_run(command: str, session: str = "s1") -> dict:
    return {
        "session_id": session,
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": {"stdout": "", "stderr": ""},
    }


def context(output: dict) -> str:
    return output["hookSpecificOutput"].get("additionalContext", "")


def denied(output: dict) -> bool:
    return output["hookSpecificOutput"].get("permissionDecision") == "deny"


def run_steps(setting: str, events: tuple, start: hook.Record = hook.Record(), step: float = 1.0) -> tuple:
    """Each event's output, deciding them in order a second apart and carrying the record."""

    def one(done: tuple, indexed: tuple) -> tuple:
        outputs, record = done
        index, event = indexed
        outcome = hook.decide(event, setting, record, NOW + index * step)
        return outputs + (outcome.output,), outcome.record

    return functools.reduce(one, enumerate(events), ((), start))[0]


class Choice(unittest.TestCase):
    def test_the_first_navigate_is_reminded_and_passes_after_the_check(self):
        first, _, after = run_steps("remind", (pre("navigate"), bash_run(CHECK_COMMAND), pre("navigate")))
        self.assertEqual(context(first), hook.REMINDER)
        self.assertFalse(denied(first))
        self.assertIsNone(after)

    def test_the_first_navigate_is_denied_at_deny_and_passes_after_the_check(self):
        first, _, after = run_steps("deny", (pre("navigate"), bash_run(CHECK_COMMAND), pre("navigate")))
        self.assertTrue(denied(first))
        self.assertEqual(first["hookSpecificOutput"]["permissionDecisionReason"], hook.DENIAL)
        self.assertIsNone(after)

    def test_a_switch_brings_the_check_back(self):
        for setting, kind in (("remind", context), ("deny", denied)):
            with self.subTest(setting=setting):
                for switch in ("switch_browser", "select_browser"):
                    events = (bash_run(CHECK_COMMAND), pre("navigate"), post(switch), pre("navigate"))
                    _, passed, _, again = run_steps(setting, events)
                    self.assertIsNone(passed)
                    self.assertTrue(kind(again))

    def test_the_finding_tools_are_never_caught(self):
        for setting in ("remind", "deny"):
            for tool in ("list_connected_browsers", "tabs_context_mcp", "select_browser", "switch_browser"):
                with self.subTest(setting=setting, tool=tool):
                    self.assertEqual(run_steps(setting, (pre(tool),)), (None,))

    def test_every_page_acting_tool_is_caught(self):
        for tool in sorted(hook.PAGE_ACTING):
            with self.subTest(tool=tool):
                (output,) = run_steps("remind", (pre(tool),))
                self.assertEqual(context(output), hook.REMINDER)

    def test_unlisted_and_other_tools_pass(self):
        self.assertEqual(run_steps("deny", (pre("read_page"),)), (None,))
        self.assertEqual(run_steps("deny", ({**pre("navigate"), "tool_name": "Read"},)), (None,))

    def test_a_second_attempt_passes_at_both_settings(self):
        for setting in ("remind", "deny"):
            with self.subTest(setting=setting):
                first, second, third = run_steps(setting, (pre("navigate"), pre("navigate"), pre("computer")))
                self.assertIsNotNone(first)
                self.assertIsNone(second)
                self.assertIsNone(third)

    def test_a_record_over_an_hour_old_is_ignored(self):
        old = NOW - hook.LIFETIME - 1
        for setting, kind in (("remind", context), ("deny", denied)):
            for start in (hook.Record(checked=old), hook.Record(caught=old)):
                with self.subTest(setting=setting, start=start):
                    (output,) = run_steps(setting, (pre("navigate"),), start=start)
                    self.assertTrue(kind(output))
        fresh = hook.Record(checked=NOW - hook.LIFETIME + 60)
        self.assertEqual(run_steps("deny", (pre("navigate"),), start=fresh), (None,))

    def test_off_says_nothing(self):
        self.assertEqual(run_steps("off", (pre("navigate"), pre("navigate"))), (None, None))

    def test_deny_with_no_record_to_keep_reminds(self):
        outcome = hook.decide(pre("navigate"), "deny", hook.Record(), NOW, counted=False)
        self.assertEqual(context(outcome.output), hook.REMINDER)

    def test_only_a_marker_run_counts_as_a_check(self):
        for command in (CHECK_COMMAND, "python3 scripts/which_browser.py abc && echo ok"):
            with self.subTest(command=command):
                self.assertTrue(hook.is_check_run(command))
        for command in (
            "python3 scripts/which_browser.py --list",
            "python3 scripts/which_browser.py --list --urls",
            "cat scripts/which_browser.py.orig",
            "ls",
        ):
            with self.subTest(command=command):
                self.assertFalse(hook.is_check_run(command))

    def test_the_setting_is_read_from_the_last_file_that_has_one(self):
        self.assertEqual(hook.setting_from(("", "")), "remind")
        self.assertEqual(hook.setting_from(("- Browser check: deny\n", "")), "deny")
        self.assertEqual(hook.setting_from(("- Browser check: deny\n", "- **Browser check:** off\n")), "off")
        self.assertEqual(hook.setting_from(("- Browser check: maybe\n",)), "remind")


@unittest.skipUnless(BASH, "needs bash")
class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self.tmp.name))
        self.home, self.project, self.data = base / "home", base / "project", base / "data"
        self.home.mkdir()
        self.project.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def set_setting(self, setting: str) -> None:
        folder = self.project / ".agents" / "skills"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{hook.SKILL}.preferences.md").write_text(f"- Browser check: {setting}\n", encoding="utf-8")

    def run_hook(self, payload: dict, path: str = "") -> dict | None:
        env = {
            "PATH": path or os.environ.get("PATH", ""),
            "HOME": str(self.home),
            "CLAUDE_PROJECT_DIR": str(self.project),
            "CLAUDE_PLUGIN_DATA": str(self.data),
        }
        done = subprocess.run(
            [BASH, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env=env, check=True
        )
        self.assertEqual(done.stderr, "")
        return json.loads(done.stdout) if done.stdout else None

    def test_remind_is_the_default(self):
        self.assertEqual(context(self.run_hook(pre("navigate"))), hook.REMINDER)
        self.assertIsNone(self.run_hook(pre("navigate")))
        self.assertEqual(context(self.run_hook(pre("navigate", session="s2"))), hook.REMINDER)

    def test_a_session_at_each_setting(self):
        for setting, kind in (("remind", context), ("deny", denied)):
            with self.subTest(setting=setting):
                self.set_setting(setting)
                session = f"session-{setting}"
                self.assertIsNone(self.run_hook(pre("list_connected_browsers", session)))
                self.assertTrue(kind(self.run_hook(pre("navigate", session))))
                self.assertIsNone(self.run_hook(pre("navigate", session)))
                self.assertIsNone(self.run_hook(post("switch_browser", session)))
                self.assertTrue(kind(self.run_hook(pre("navigate", session))))
                self.assertIsNone(self.run_hook(bash_run(CHECK_COMMAND, session)))
                self.assertIsNone(self.run_hook(pre("navigate", session)))
                self.assertIsNone(self.run_hook(post("select_browser", session)))
                self.assertTrue(kind(self.run_hook(pre("form_input", session))))

    def test_a_check_after_the_catch_lets_calls_through(self):
        self.set_setting("deny")
        self.assertIsNone(self.run_hook(bash_run(CHECK_COMMAND)))
        self.assertIsNone(self.run_hook(pre("navigate")))

    def test_an_hour_old_record_is_ignored(self):
        self.set_setting("deny")
        self.assertIsNone(self.run_hook(bash_run(CHECK_COMMAND)))
        record = self.data / "browser-check" / "s1.json"
        old = time.time() - hook.LIFETIME - 5
        record.write_text(json.dumps({"checked": old, "caught": old}), encoding="utf-8")
        self.assertTrue(denied(self.run_hook(pre("navigate"))))

    def test_off_writes_and_says_nothing(self):
        self.set_setting("off")
        self.assertIsNone(self.run_hook(pre("navigate")))
        self.assertFalse((self.data / "browser-check" / "s1.json").exists())

    def test_a_bash_call_without_the_script_starts_no_process(self):
        stub = Path(self.tmp.name) / "bin"
        stub.mkdir()
        marker = Path(self.tmp.name) / "ran"
        (stub / "python3").write_text(f"#!/bin/sh\n: > {marker}\n")
        (stub / "python3").chmod(0o755)
        self.assertIsNone(self.run_hook(bash_run("ls -la"), path=str(stub)))
        self.assertFalse(marker.exists())
        self.run_hook(bash_run(CHECK_COMMAND), path=str(stub))
        self.assertTrue(marker.exists())

    def test_the_shell_hands_on_exactly_the_tools_python_acts_on(self):
        stub = Path(self.tmp.name) / "bin"
        stub.mkdir()
        marker = Path(self.tmp.name) / "ran"
        (stub / "python3").write_text(f"#!/bin/sh\n: > {marker}\n")
        (stub / "python3").chmod(0o755)
        tools = hook.PAGE_ACTING | hook.SWITCHING | {"list_connected_browsers", "tabs_context_mcp", "read_page"}
        for tool in sorted(tools):
            with self.subTest(tool=tool):
                self.run_hook(pre(tool), path=str(stub))
                self.assertEqual(marker.exists(), tool in hook.PAGE_ACTING | hook.SWITCHING)
                marker.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
