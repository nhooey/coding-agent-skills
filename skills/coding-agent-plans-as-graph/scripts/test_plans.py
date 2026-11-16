#!/usr/bin/env python3
"""Tests for plans.py: python3 -I test_plans.py"""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plans  # noqa: E402


class Plan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "agents" / "plans"
        (self.root / "open").mkdir(parents=True)
        (self.root / "closed").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def node(self, folder: str, id: str, **meta):
        meta.setdefault("title", id.replace("-", " ").capitalize())
        meta.setdefault("kind", "implementation")
        lines = ["---"]
        for k, v in meta.items():
            key = k.replace("_", "-")
            lines.append(f"{key}: [{', '.join(v)}]" if isinstance(v, list) else f"{key}: {v}")
        lines += ["---", "", f"# {meta['title']}", "", "Body."]
        (self.root / folder / f"{id}.md").write_text("\n".join(lines) + "\n")

    def run_cmd(self, command: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = plans.main([command, "--plans", str(self.root)])
        return code, out.getvalue(), err.getvalue()

    def test_a_valid_graph_checks_clean(self):
        self.node("open", "uniform-skills", kind="end-state", state="approved")
        self.node("closed", "skill-lists", state="implemented", part_of="uniform-skills")
        self.node("open", "lock-wave", state="approved", part_of="uniform-skills", needs=["skill-lists"])
        self.assertEqual(self.run_cmd("check"), (0, "", ""))

    def test_ready_lists_approved_nodes_whose_needs_are_implemented(self):
        self.node("closed", "a", state="implemented")
        self.node("open", "b", state="in-progress")
        self.node("open", "c", state="approved", needs=["a"])
        self.node("open", "d", state="approved", needs=["a", "b"])
        self.node("open", "e", state="proposed")
        code, out, _ = self.run_cmd("ready")
        self.assertEqual((code, out.split()), (0, ["c"]))

    def test_state_must_match_its_folder(self):
        self.node("open", "done-already", state="implemented")
        code, _, err = self.run_cmd("check")
        self.assertEqual(code, 1)
        self.assertIn("doesn't belong in open/; move it to closed/", err)

    def test_links_must_name_existing_nodes(self):
        self.node("open", "x", state="approved", needs=["nowhere"])
        self.assertIn("`needs` names `nowhere`, which has no node", self.run_cmd("check")[2])

    def test_needs_cycles_are_reported(self):
        self.node("open", "x", state="approved", needs=["y"])
        self.node("open", "y", state="approved", needs=["x"])
        self.assertIn("`needs` cycle: x → y → x", self.run_cmd("check")[2])

    def test_after_is_only_for_schedule_nodes(self):
        self.node("open", "x", state="approved")
        self.node("open", "y", state="approved", after=["x"])
        self.node("open", "wave-2", kind="schedule", state="approved", after=["x"])
        err = self.run_cmd("check")[2]
        self.assertIn("open/y.md: `after` is run order", err)
        self.assertNotIn("wave-2", err)

    def test_superseded_names_its_replacement(self):
        self.node("open", "new", state="approved")
        self.node("closed", "old", state="superseded")
        self.assertIn("names its replacement in `superseded-by`", self.run_cmd("check")[2])

    def test_unknown_keys_and_missing_fields_are_reported(self):
        self.node("open", "x", state="approved", colour="red")
        (self.root / "open" / "bare.md").write_text("# No frontmatter\n")
        err = self.run_cmd("check")[2]
        self.assertIn("unknown key `colour`", err)
        self.assertIn("open/bare.md: no frontmatter", err)

    def test_overview_groups_open_nodes_and_counts_closed(self):
        self.node("closed", "a", state="implemented")
        self.node("closed", "z", state="rejected")
        self.node("open", "b", state="in-progress", owner="headless/wave-1")
        self.node("open", "c", state="approved", needs=["a"])
        self.node("open", "d", state="approved", needs=["b"])
        self.node("open", "e", state="proposed")
        self.assertEqual(self.run_cmd("overview")[0], 0)
        text = (self.root / "README.md").read_text()
        self.assertIn("## In progress (1)\n\n- [B](open/b.md) `b`, headless/wave-1", text)
        self.assertIn("## Ready (1)\n\n- [C](open/c.md) `c`", text)
        self.assertIn("## Blocked (1)\n\n- [D](open/d.md) `d`, waiting on `b`", text)
        self.assertIn("## Proposed (1)", text)
        self.assertIn("2 in [closed/](closed/): 1 implemented, 1 rejected, 0 abandoned, 0 superseded.", text)

    def test_overview_is_not_written_when_check_fails(self):
        self.node("open", "x", state="approved", needs=["missing"])
        self.assertEqual(self.run_cmd("overview")[0], 1)
        self.assertFalse((self.root / "README.md").exists())

    def test_a_node_at_the_plan_root_is_reported(self):
        (self.root / "stray.md").write_text("---\ntitle: S\n---\n")
        self.assertIn("stray.md: a node goes in an open/ or closed/ folder", self.run_cmd("check")[2])

    def test_a_plans_folder_holds_its_own_open_and_closed_nodes(self):
        (self.root / "gating" / "open").mkdir(parents=True)
        (self.root / "gating" / "closed").mkdir()
        self.node("open", "no-oversubscription", kind="end-state", state="proposed")
        self.node("gating/closed", "nix-limits", state="implemented", part_of="no-oversubscription")
        self.node("gating/open", "admission", state="approved", part_of="no-oversubscription", needs=["nix-limits"])
        self.assertEqual(self.run_cmd("check"), (0, "", ""))
        self.assertEqual(self.run_cmd("ready")[1].split(), ["admission"])
        self.run_cmd("overview")
        self.assertIn("(gating/open/admission.md)", (self.root / "README.md").read_text())

    def test_a_node_loose_in_a_plans_folder_is_reported(self):
        (self.root / "gating" / "open").mkdir(parents=True)
        (self.root / "gating" / "stray.md").write_text("---\ntitle: x\n---\n")
        self.assertIn("gating/stray.md: a node goes in an open/ or closed/ folder", self.run_cmd("check")[2])

    def test_an_id_is_unique_across_plans(self):
        (self.root / "gating" / "open").mkdir(parents=True)
        self.node("open", "same", state="proposed")
        self.node("gating/open", "same", state="proposed")
        self.assertIn("id `same` is also", self.run_cmd("check")[2])

    def test_a_list_wrapped_onto_an_indented_line_is_read_whole(self):
        (self.root / "open" / "wrapped.md").write_text(
            "---\ntitle: Wrapped\nstate: approved\nkind: implementation\nneeds:\n  [a, b]\n---\n"
        )
        self.node("closed", "a", state="implemented")
        self.node("closed", "b", state="implemented")
        self.assertEqual(self.run_cmd("check"), (0, "", ""))
        self.assertEqual(self.run_cmd("ready")[1].split(), ["wrapped"])

    def test_an_indented_comment_joins_no_line(self):
        (self.root / "open" / "commented.md").write_text(
            "---\ntitle: Commented\nstate: approved\nkind: implementation\nneeds: [a]\n"
            "  # a is the parser rewrite\n---\n"
        )
        self.node("closed", "a", state="implemented")
        self.assertEqual(self.run_cmd("check"), (0, "", ""))

if __name__ == "__main__":
    unittest.main()
