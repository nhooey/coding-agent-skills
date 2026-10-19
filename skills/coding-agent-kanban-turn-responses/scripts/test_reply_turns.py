#!/usr/bin/env python3
"""Tests for reply_turns.py's transcript lookup, run from anywhere: `python3 -I scripts/test_reply_turns.py`.

Standard library only.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import reply_turns  # noqa: E402

SESSION = "8907a830-6e25-4a1b-ab2b-80ec191e55ac"


class TranscriptPathTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = tempfile.TemporaryDirectory()
        self.projects = pathlib.Path(self.home.name) / ".claude" / "projects"

    def tearDown(self) -> None:
        self.home.cleanup()

    def write(self, slug: str, session: str = SESSION) -> pathlib.Path:
        path = self.projects / slug / f"{session}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        return path

    def lookup(self, cwd: str, transcript: str | None = None) -> pathlib.Path:
        return reply_turns.transcript_path(transcript, SESSION, cwd, self.home.name)

    def test_project_root_names_its_own_project(self) -> None:
        path = self.write("-Users-a-repo")
        self.assertEqual(self.lookup("/Users/a/repo"), path)

    def test_worktree_names_the_main_checkout(self) -> None:
        path = self.write("-Users-a-repo")
        self.assertEqual(self.lookup("/Users/a/repo/.worktrees/branch"), path)

    def test_any_other_directory_finds_the_one_project_holding_the_session(self) -> None:
        path = self.write("-Users-a-repo")
        self.write("-Users-a-other", session="another-session")
        self.assertEqual(self.lookup("/nix/store/abc-skill/share/scripts"), path)

    def test_a_session_in_two_projects_is_not_guessed(self) -> None:
        self.write("-Users-a-repo")
        self.write("-Users-a-other")
        self.assertEqual(self.lookup("/tmp"), self.projects / "-tmp" / f"{SESSION}.jsonl")

    def test_no_transcript_anywhere_names_the_working_directory_s_path(self) -> None:
        self.assertEqual(self.lookup("/tmp"), self.projects / "-tmp" / f"{SESSION}.jsonl")

    def test_transcript_flag_wins(self) -> None:
        self.write("-Users-a-repo")
        self.assertEqual(self.lookup("/Users/a/repo", "/x/y.jsonl"), pathlib.Path("/x/y.jsonl"))


if __name__ == "__main__":
    unittest.main()
