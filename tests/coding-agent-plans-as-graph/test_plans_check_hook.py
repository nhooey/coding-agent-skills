#!/usr/bin/env python3
"""Tests for plans-check-hook.sh and plans_check_hook.py: skills-dev test coding-agent-plans-as-graph

The end-to-end tests run the bash hook with real files, a temporary home and
plugin data folder, and need `bash` on PATH.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import plans_check_hook as hook

HERE = Path(hook.__file__).resolve().parent
HOOK = HERE / "plans-check-hook.sh"
BASH = shutil.which("bash")


class Choice(unittest.TestCase):
    MISSING = "open/a.md: `part-of` names `gone`, which has no node"
    OTHER = "open/b.md: missing `kind`"

    def test_the_written_files_findings_come_alone(self):
        own, others = hook.choose((self.MISSING, self.OTHER), "open/a.md", frozenset())
        self.assertEqual((own, others), ((self.MISSING,), ()))

    def test_a_clean_write_brings_the_others_not_yet_reported(self):
        later = "open/c.md: missing `title`"
        own, others = hook.choose((self.OTHER, later), "open/a.md", frozenset({self.OTHER}))
        self.assertEqual((own, others), ((), (later,)))

    def test_a_cycle_names_each_of_its_nodes(self):
        cycle = "`needs` cycle: a → b → a"
        self.assertTrue(hook.names_file(cycle, "gating/open/b.md"))
        self.assertFalse(hook.names_file(cycle, "open/c.md"))
        self.assertFalse(hook.names_file("open/ab.md: missing `kind`", "open/a.md"))

    def test_a_fixed_finding_is_forgotten(self):
        self.assertEqual(hook.remembered((self.OTHER,), frozenset({self.MISSING, self.OTHER}), ()), {self.OTHER})


@unittest.skipUnless(BASH, "needs bash")
class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self.tmp.name))
        self.home, self.data, self.project = base / "home", base / "data", base / "project"
        self.home.mkdir()
        self.plans = self.project / "agents" / "plans"
        (self.plans / "open").mkdir(parents=True)
        (self.plans / "closed").mkdir()
        self.path = os.environ.get("PATH", "")

    def tearDown(self):
        self.tmp.cleanup()

    def node(self, rel: str, **meta) -> Path:
        meta.setdefault("title", "T")
        meta.setdefault("state", "approved")
        meta.setdefault("kind", "implementation")
        path = self.plans / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("---\n" + "".join(f"{k}: {v}\n" for k, v in meta.items()) + "---\n\n# T\n")
        return path

    def run_hook(self, path: Path, session: str = "s1", tool: str = "Write") -> str:
        event = {
            "session_id": session,
            "hook_event_name": "PostToolUse",
            "tool_name": tool,
            "tool_input": {"file_path": str(path), "content": "x"},
        }
        env = {
            "PATH": self.path,
            "HOME": str(self.home),
            "CLAUDE_PLUGIN_DATA": str(self.data),
            "CLAUDE_PROJECT_DIR": str(self.project),
        }
        done = subprocess.run(
            [BASH, str(HOOK)], input=json.dumps(event), capture_output=True, text=True, env=env, check=True
        )
        self.assertEqual(done.stderr, "")
        return done.stdout

    def context(self, out: str) -> str:
        output = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "PostToolUse")
        return output["additionalContext"]

    def test_a_node_whose_parent_is_missing_gives_the_finding(self):
        path = self.node("open/child.md", **{"part-of": "nowhere"})
        text = self.context(self.run_hook(path, tool="Edit"))
        self.assertIn("open/child.md: `part-of` names `nowhere`, which has no node", text)
        self.assertIn("agents/plans/open/child.md", text)

    def test_a_clean_graph_gives_nothing(self):
        self.node("open/parent.md", kind="end-state")
        path = self.node("open/child.md", **{"part-of": "parent"})
        self.assertEqual(self.run_hook(path), "")
        self.assertFalse((self.plans / "README.md").exists())

    def test_a_file_outside_the_plan_folder_runs_no_check(self):
        stub = Path(self.tmp.name) / "bin"
        stub.mkdir()
        marker = Path(self.tmp.name) / "ran"
        (stub / "python3").write_text(f"#!/bin/sh\ntouch {marker}\n")
        (stub / "python3").chmod(0o755)
        self.path = str(stub)
        self.node("open/child.md", **{"part-of": "nowhere"})
        for outside in (self.project / "docs" / "notes.md", self.project / "agents" / "plans.py", self.plans / "README.md"):
            self.assertEqual(self.run_hook(outside), "")
        self.assertFalse(marker.exists())
        self.path = os.environ.get("PATH", "")
        self.assertNotEqual(self.run_hook(self.plans / "open" / "child.md"), "")

    def test_no_yq_on_path_runs_no_check(self):
        stub = Path(self.tmp.name) / "bin"
        stub.mkdir()
        marker = Path(self.tmp.name) / "ran"
        (stub / "python3").write_text(f"#!/bin/sh\ntouch {marker}\n")
        (stub / "python3").chmod(0o755)
        self.path = str(stub)
        self.assertEqual(self.run_hook(self.node("open/child.md", **{"part-of": "nowhere"})), "")
        self.assertFalse(marker.exists())

    def test_a_finding_about_another_file_is_given_once(self):
        self.node("open/broken.md", needs="[gone]")
        self.node("open/parent.md", kind="end-state")
        first = self.node("open/first.md", **{"part-of": "parent"})
        self.assertIn("open/broken.md: `needs` names `gone`", self.context(self.run_hook(first)))
        self.assertEqual(self.run_hook(first), "")
        self.assertEqual(self.run_hook(self.node("open/second.md", **{"part-of": "parent"})), "")
        own = self.context(self.run_hook(self.node("open/third.md", **{"part-of": "missing"})))
        self.assertNotIn("broken.md", own)
        self.assertIn("broken.md", self.context(self.run_hook(first, session="s2")))

    def test_a_plan_folder_from_the_projects_preferences(self):
        prefs = self.project / ".agents" / "skills" / "coding-agent-plans-as-graph.preferences.md"
        prefs.parent.mkdir(parents=True)
        prefs.write_text("- Plan folder: `docs/plans/`\n")
        self.plans = self.project / "docs" / "plans"
        (self.plans / "open").mkdir(parents=True)
        path = self.node("open/x.md", needs="[gone]")
        self.assertIn("docs/plans/open/x.md", self.context(self.run_hook(path)))
        self.assertEqual(self.run_hook(self.project / "agents" / "plans" / "open" / "y.md"), "")


if __name__ == "__main__":
    unittest.main()
