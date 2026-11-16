#!/usr/bin/env python3
"""Tests for memory-write-reminder.sh and memory_write_reminder.py: python3 -I test_memory_write_reminder.py

fixtures/memory-write.json is a Write of a memory file at the path Claude Code
uses, `~/.claude/projects/<project>/memory/`. When that layout changes, change
the fixture, and these tests fail until the hook follows it.

The end-to-end tests run the bash hook with a temporary home and plugin data
folder, and need `bash` on PATH.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import memory_write_reminder as hook  # noqa: E402

HOOK = HERE / "memory-write-reminder.sh"
FIXTURE = json.loads((HERE / "fixtures" / "memory-write.json").read_text(encoding="utf-8"))
BASH = shutil.which("bash")
HOME = "/home/me"
CONFIG = "/home/me/.claude"


def event(path: str, tool: str = "Write", session: str = "s1") -> dict:
    return {**FIXTURE, "session_id": session, "tool_name": tool, "tool_input": {**FIXTURE["tool_input"], "file_path": path}}


def under_home(path: str, home: str) -> str:
    return home + path[1:]


class Choice(unittest.TestCase):
    def test_the_fixtures_memory_write_is_reminded(self):
        output = hook.decide(FIXTURE, HOME, CONFIG, False)
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertEqual(output["hookSpecificOutput"]["additionalContext"], hook.REMINDER)
        self.assertNotIn("permissionDecision", output["hookSpecificOutput"])

    def test_the_fixtures_path_with_home_spelled_out_is_reminded(self):
        path = under_home(FIXTURE["tool_input"]["file_path"], HOME)
        self.assertIsNotNone(hook.decide(event(path, tool="Edit"), HOME, CONFIG, False))

    def test_a_session_already_reminded_gets_nothing(self):
        self.assertIsNone(hook.decide(FIXTURE, HOME, CONFIG, True))

    def test_writes_outside_the_memory_folders_get_nothing(self):
        for path in (
            "/home/me/git/project/MEMORY.md",
            "/home/me/git/project/memory/feedback.md",
            "/home/me/.claude/projects/p/notes/feedback.md",
            "/home/me/.claude/projects/p/memory",
            "/home/me/.claude/projects/memory/feedback.md",
            "/home/me/.claude/projects/p/memory/../CLAUDE.md",
            "/other/.claude/projects/p/memory/feedback.md",
        ):
            with self.subTest(path=path):
                self.assertIsNone(hook.decide(event(path), HOME, CONFIG, False))

    def test_other_tools_get_nothing(self):
        self.assertIsNone(hook.decide(event(FIXTURE["tool_input"]["file_path"], tool="Read"), HOME, CONFIG, False))
        self.assertIsNone(hook.decide({"tool_name": "Write", "tool_input": {}}, HOME, CONFIG, False))

    def test_a_config_dir_moves_the_memory_folders(self):
        self.assertIsNotNone(hook.decide(event("/cfg/projects/p/memory/a.md"), HOME, "/cfg", False))
        self.assertIsNone(hook.decide(event("/home/me/.claude/projects/p/memory/a.md"), HOME, "/cfg", False))


@unittest.skipUnless(BASH, "needs bash")
class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self.tmp.name))
        self.home, self.data = base / "home", base / "data"
        self.home.mkdir()
        self.memory = under_home(FIXTURE["tool_input"]["file_path"], str(self.home))

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, payload: dict, path: str = "") -> str:
        env = {"PATH": path or os.environ.get("PATH", ""), "HOME": str(self.home), "CLAUDE_PLUGIN_DATA": str(self.data)}
        done = subprocess.run(
            [BASH, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env=env, check=True
        )
        self.assertEqual(done.stderr, "")
        return done.stdout

    def test_a_memory_write_is_reminded_once_per_session(self):
        first = json.loads(self.run_hook(event(self.memory)))
        self.assertEqual(first["hookSpecificOutput"]["additionalContext"], hook.REMINDER)
        self.assertEqual(self.run_hook(event(self.memory, tool="Edit")), "")
        self.assertNotEqual(self.run_hook(event(self.memory, session="s2")), "")

    def test_the_fixture_as_written_is_reminded(self):
        self.assertNotEqual(self.run_hook(FIXTURE), "")

    def test_memory_md_in_a_repository_gets_nothing(self):
        repo = self.home / "git" / "project"
        for path in (repo / "MEMORY.md", repo / "memory" / "MEMORY.md"):
            with self.subTest(path=path):
                self.assertEqual(self.run_hook(event(str(path))), "")
        self.assertFalse(self.data.exists())

    def test_a_write_without_a_memory_folder_starts_no_process(self):
        stub = Path(self.tmp.name) / "bin"
        stub.mkdir()
        marker = Path(self.tmp.name) / "ran"
        (stub / "python3").write_text(f"#!/bin/sh\ntouch {marker}\n")
        (stub / "python3").chmod(0o755)
        self.assertEqual(self.run_hook(event(str(self.home / "git" / "project" / "MEMORY.md")), path=str(stub)), "")
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
