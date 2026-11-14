#!/usr/bin/env python3
"""Tests for fan_out.py: the pieces, then whole runs against a fake `claude`.

Run with `python3 -I test_fan_out.py`. Needs `git` on PATH; uses no network
and no real Claude Code.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fan_out  # noqa: E402

FAKE_CLAUDE = textwrap.dedent(
    """\
    #!{python}
    # Records how it was called, then behaves as FAKE_CLAUDE_MODE says.
    import json, os, sys
    cwd = os.getcwd()
    name = os.path.basename(os.path.dirname(cwd)) + "_" + os.path.basename(cwd)
    record = os.path.join(os.environ["FAKE_CLAUDE_RECORD"], name + ".json")
    with open(record, "w") as f:
        json.dump({{"argv": sys.argv[1:], "cwd": os.getcwd()}}, f)
    mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
    if mode == "limit":
        print(json.dumps({{"type": "result", "is_error": True, "result": "Claude usage limit reached"}}))
        sys.exit(1)
    print(json.dumps({{"type": "system", "subtype": "init"}}))
    print(json.dumps({{"type": "result", "is_error": False, "result": "done in " + os.getcwd(),
                       "session_id": "sess-1", "num_turns": 3}}))
    """
)


def git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def make_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    git("init", "-q", "-b", "main", cwd=path)
    (path / "README.md").write_text("hello\n")
    git("add", ".", cwd=path)
    git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "init", cwd=path)
    return path.resolve()


class Pieces(unittest.TestCase):
    def test_project_key_matches_claude_codes_folder_names(self):
        self.assertEqual(fan_out.project_key(Path("/Users/me/git/github-config")),
                         "-Users-me-git-github-config")
        self.assertEqual(fan_out.project_key(Path("/a/Shane - Investing/x.y_z")),
                         "-a-Shane---Investing-x-y-z")

    def test_newest_session_picks_latest_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, checkout = Path(tmp), Path("/w/repo")
            folder = root / fan_out.project_key(checkout)
            folder.mkdir()
            self.assertIsNone(fan_out.newest_session(checkout, root))
            old, new = folder / "old.jsonl", folder / "new.jsonl"
            old.write_text("{}\n")
            new.write_text("{}\n")
            os.utime(old, (time.time() - 100, time.time() - 100))
            (folder / "memory").mkdir()
            self.assertEqual(fan_out.newest_session(checkout, root), new)

    def test_command_continues_in_checkout_and_resumes_by_path_in_worktree(self):
        resume = Path("/s/abc.jsonl")
        in_checkout = fan_out.claude_command("p", "n", where="checkout", resume=resume)
        self.assertIn("--continue", in_checkout)
        self.assertNotIn("--resume", in_checkout)
        in_worktree = fan_out.claude_command("p", "n", where="worktree", resume=resume)
        i = in_worktree.index("--resume")
        self.assertEqual(in_worktree[i + 1], str(resume))
        for cmd in (in_checkout, in_worktree):
            self.assertIn("--fork-session", cmd)
            self.assertEqual(cmd[:3], ["claude", "-p", "p"])
            self.assertEqual(cmd[cmd.index("--permission-prompts") + 1], "none")
        fresh = fan_out.claude_command("p", "n", where="worktree", resume=None,
                                       model="m", effort="high", max_turns=5, extra=["--x"])
        self.assertNotIn("--fork-session", fresh)
        self.assertEqual(fresh[-3:], ["--max-turns", "5", "--x"])
        self.assertIn("m", fresh)

    def test_parse_result_takes_the_last_result_event(self):
        stream = "\n".join([
            "not json",
            json.dumps({"type": "assistant"}),
            json.dumps({"type": "result", "result": "first"}),
            "{broken",
            json.dumps({"type": "result", "result": "last", "session_id": "s"}),
        ])
        self.assertEqual(fan_out.parse_result(stream)["result"], "last")
        self.assertIsNone(fan_out.parse_result("nothing here"))

    def test_usage_limit_detection(self):
        self.assertTrue(fan_out.is_usage_limit("Claude usage limit reached; resets at 5pm"))
        self.assertTrue(fan_out.is_usage_limit("", "API Error: 429"))
        self.assertFalse(fan_out.is_usage_limit("tests failed", "exit 1"))

    def test_unique_labels(self):
        paths = [Path("/a/app"), Path("/b/app"), Path("/c/lib"), Path("/d/app")]
        self.assertEqual(fan_out.unique_labels(paths), ["app", "app-2", "lib", "app-3"])


class WholeRuns(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name).resolve()
        self.repos = [make_repo(base / "src" / name) for name in ("alpha", "beta")]
        self.projects = base / "projects"
        self.record = base / "record"
        self.record.mkdir()
        self.logs = base / "logs"
        bin_dir = base / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "claude"
        fake.write_text(FAKE_CLAUDE.format(python=sys.executable))
        fake.chmod(0o755)
        self.env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                    "FAKE_CLAUDE_RECORD": str(self.record)}
        # alpha has an earlier session; beta has none.
        folder = self.projects / fan_out.project_key(self.repos[0])
        folder.mkdir(parents=True)
        self.alpha_session = folder / "11111111.jsonl"
        self.alpha_session.write_text("{}\n")

    def tearDown(self):
        self.tmp.cleanup()

    def fan_out(self, *extra: str, mode: str = "ok") -> int:
        env = {**self.env, "FAKE_CLAUDE_MODE": mode}
        old = {k: os.environ.get(k) for k in [*env, "ANTHROPIC_API_KEY"]}
        os.environ.update(env)
        os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            return fan_out.main(["--prompt", "do the thing", "--job", "t1",
                                 "--projects-root", str(self.projects),
                                 "--log-dir", str(self.logs), *extra,
                                 *map(str, self.repos)])
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def recorded(self, name: str) -> dict:
        return json.loads((self.record / f"{name}.json").read_text())

    def test_worktree_runs_resume_the_checkouts_session_and_leave_it_untouched(self):
        self.assertEqual(self.fan_out("--parallel", "2"), 0)
        alpha = self.recorded("alpha.worktrees_fan-out-t1")
        beta = self.recorded("beta.worktrees_fan-out-t1")
        i = alpha["argv"].index("--resume")
        self.assertEqual(alpha["argv"][i + 1], str(self.alpha_session))
        self.assertIn("--fork-session", alpha["argv"])
        self.assertNotIn("--resume", beta["argv"])
        summary = json.loads((self.logs / "summary.json").read_text())
        self.assertEqual([o["status"] for o in summary], ["ok", "ok"])
        self.assertEqual(summary[0]["resumed_from"], str(self.alpha_session))
        self.assertIsNone(summary[1]["resumed_from"])
        self.assertEqual(summary[0]["session_id"], "sess-1")
        for repo in self.repos:
            wt = fan_out.worktree_path(repo, "t1")
            self.assertTrue((wt / "README.md").is_file())
            branch = subprocess.run(["git", "branch", "--show-current"], cwd=wt,
                                    capture_output=True, text=True).stdout.strip()
            self.assertEqual(branch, "fan-out/t1")
            status = subprocess.run(["git", "status", "--porcelain"], cwd=repo,
                                    capture_output=True, text=True).stdout
            self.assertEqual(status, "", "the main checkout must stay clean")

    def test_checkout_runs_use_continue_where_there_is_a_session(self):
        self.assertEqual(self.fan_out("--where", "checkout"), 0)
        alpha, beta = self.recorded("src_alpha"), self.recorded("src_beta")
        self.assertEqual(Path(alpha["cwd"]).resolve(), self.repos[0])
        self.assertIn("--continue", alpha["argv"])
        self.assertIn("--fork-session", alpha["argv"])
        self.assertNotIn("--continue", beta["argv"])
        self.assertEqual(beta["argv"][:2], ["-p", "do the thing"])

    def test_new_sessions_ignore_earlier_ones(self):
        self.assertEqual(self.fan_out("--where", "checkout", "--session", "new"), 0)
        self.assertNotIn("--continue", self.recorded("src_alpha")["argv"])

    def test_usage_limit_stops_further_runs(self):
        self.assertEqual(self.fan_out("--where", "checkout", "--parallel", "1", mode="limit"), 1)
        summary = json.loads((self.logs / "summary.json").read_text())
        self.assertEqual([o["status"] for o in summary], ["limit", "skipped"])
        self.assertFalse((self.record / "src_beta.json").exists())

    def make_alpha_dirty(self):
        (self.repos[0] / "README.md").write_text("edited, not committed\n")
        (self.repos[0] / "new.txt").write_text("untracked\n")

    def test_dirty_checkout_continues_with_a_note_naming_its_uncommitted_paths(self):
        self.make_alpha_dirty()
        self.assertEqual(self.fan_out(), 0)
        argv = self.recorded("alpha.worktrees_fan-out-t1")["argv"]
        prompt = argv[1]
        self.assertTrue(prompt.startswith("Note from the fan-out runner"), prompt)
        self.assertIn("- README.md", prompt)
        self.assertIn("- new.txt", prompt)
        self.assertTrue(prompt.endswith("do the thing"))
        self.assertIn("--resume", argv)
        self.assertEqual(self.recorded("beta.worktrees_fan-out-t1")["argv"][1], "do the thing")

    def test_dirty_new_starts_a_fresh_session(self):
        self.make_alpha_dirty()
        self.assertEqual(self.fan_out("--dirty", "new"), 0)
        argv = self.recorded("alpha.worktrees_fan-out-t1")["argv"]
        self.assertNotIn("--resume", argv)
        self.assertEqual(argv[1], "do the thing")

    def test_dirty_skip_leaves_the_checkout_out(self):
        self.make_alpha_dirty()
        self.assertEqual(self.fan_out("--dirty", "skip"), 1)
        summary = json.loads((self.logs / "summary.json").read_text())
        self.assertEqual([o["status"] for o in summary], ["skipped", "ok"])
        self.assertIn("uncommitted", summary[0]["result"])
        self.assertFalse(fan_out.worktree_path(self.repos[0], "t1").exists())

    def test_dirty_checkout_runs_in_place_untouched_by_the_note(self):
        self.make_alpha_dirty()
        self.assertEqual(self.fan_out("--where", "checkout"), 0)
        self.assertEqual(self.recorded("src_alpha")["argv"][1], "do the thing")

    def test_dry_run_creates_nothing(self):
        self.assertEqual(self.fan_out("--dry-run"), 0)
        self.assertFalse(fan_out.worktree_path(self.repos[0], "t1").exists())
        self.assertEqual(list(self.record.iterdir()), [])

    def test_rerun_reuses_the_jobs_worktree(self):
        self.assertEqual(self.fan_out(), 0)
        self.assertEqual(self.fan_out(), 0)
        notes = json.loads((self.logs / "summary.json").read_text())[0]["notes"]
        self.assertTrue(any(n.startswith("reused") for n in notes), notes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
