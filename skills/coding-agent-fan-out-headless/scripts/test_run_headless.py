#!/usr/bin/env python3
"""Tests for run_headless.py: the pieces, then whole runs against a fake `claude`.

Run with `python3 -I test_run_headless.py`. Needs `git` and `xargs` on PATH;
uses no network and no real Claude Code.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import run_headless  # noqa: E402

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
    if mode == "fail":
        print(json.dumps({{"type": "result", "is_error": True, "result": "tests failed"}}))
        sys.exit(1)
    print(json.dumps({{"type": "system", "subtype": "init"}}), flush=True)
    if mode == "slow":
        import time
        print('{{"type":"assistant","message":{{"content":[{{"type":"tool_use","id":"toolu_1","name":"Bash","input":{{}}}}]}}}}', flush=True)
        time.sleep(1.5)
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
        self.assertEqual(run_headless.project_key(Path("/Users/me/git/github-config")),
                         "-Users-me-git-github-config")
        self.assertEqual(run_headless.project_key(Path("/a/Shane - Investing/x.y_z")),
                         "-a-Shane---Investing-x-y-z")

    def test_newest_session_picks_latest_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, checkout = Path(tmp), Path("/w/repo")
            folder = root / run_headless.project_key(checkout)
            folder.mkdir()
            self.assertIsNone(run_headless.newest_session(checkout, root))
            old, new = folder / "old.jsonl", folder / "new.jsonl"
            old.write_text("{}\n")
            new.write_text("{}\n")
            os.utime(old, (time.time() - 100, time.time() - 100))
            (folder / "memory").mkdir()
            self.assertEqual(run_headless.newest_session(checkout, root), new)

    def test_command_continues_in_checkout_and_resumes_by_path_in_worktree(self):
        resume = Path("/s/abc.jsonl")
        in_checkout = run_headless.claude_command("p", "n", where="checkout", resume=resume)
        self.assertIn("--continue", in_checkout)
        self.assertNotIn("--resume", in_checkout)
        in_worktree = run_headless.claude_command("p", "n", where="worktree", resume=resume)
        i = in_worktree.index("--resume")
        self.assertEqual(in_worktree[i + 1], str(resume))
        for cmd in (in_checkout, in_worktree):
            self.assertIn("--fork-session", cmd)
            self.assertEqual(cmd[:3], ["claude", "-p", "p"])
            self.assertEqual(cmd[cmd.index("--permission-prompts") + 1], "none")
        fresh = run_headless.claude_command("p", "n", where="worktree", resume=None,
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
        self.assertEqual(run_headless.parse_result(stream)["result"], "last")
        self.assertIsNone(run_headless.parse_result("nothing here"))

    def test_usage_limit_detection(self):
        self.assertTrue(run_headless.is_usage_limit("Claude usage limit reached; resets at 5pm"))
        self.assertTrue(run_headless.is_usage_limit("", "API Error: 429"))
        self.assertFalse(run_headless.is_usage_limit("tests failed", "exit 1"))


class Runs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name).resolve()
        self.alpha, self.beta = (make_repo(base / "src" / n) for n in ("alpha", "beta"))
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
        folder = self.projects / run_headless.project_key(self.alpha)
        folder.mkdir(parents=True)
        self.alpha_session = folder / "11111111.jsonl"
        self.alpha_session.write_text("{}\n")

    def tearDown(self):
        self.tmp.cleanup()

    def common(self) -> list[str]:
        return ["--prompt", "do the thing", "--job", "t1", "--progress-every", "0",
                "--projects-root", str(self.projects), "--log-dir", str(self.logs)]

    def run_one(self, checkout: Path, *extra: str, mode: str = "ok") -> tuple[int, str]:
        """main() in this process, for one checkout; returns its exit status and stdout."""
        env = {**self.env, "FAKE_CLAUDE_MODE": mode}
        old = {k: os.environ.get(k) for k in [*env, "ANTHROPIC_API_KEY"]}
        os.environ.update(env)
        os.environ.pop("ANTHROPIC_API_KEY", None)
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = run_headless.main([*self.common(), *extra, str(checkout)])
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.stderr = err.getvalue()
        return code, out.getvalue()

    def recorded(self, name: str) -> dict:
        return json.loads((self.record / f"{name}.json").read_text())

    def outcome(self, label: str) -> dict:
        return json.loads((self.logs / f"{label}.outcome.json").read_text())

    def test_worktree_run_resumes_the_checkouts_session_and_leaves_it_untouched(self):
        code, out = self.run_one(self.alpha)
        self.assertEqual(code, 0)
        argv = self.recorded("alpha.worktrees_fan-out-t1")["argv"]
        self.assertEqual(argv[argv.index("--resume") + 1], str(self.alpha_session))
        self.assertIn("--fork-session", argv)
        printed = json.loads(out)
        self.assertEqual(printed, self.outcome("alpha"))
        self.assertEqual(printed["status"], "ok")
        self.assertEqual(printed["resumed_from"], str(self.alpha_session))
        self.assertEqual(printed["session_id"], "sess-1")
        wt = run_headless.worktree_path(self.alpha, "t1")
        self.assertTrue((wt / "README.md").is_file())
        branch = subprocess.run(["git", "branch", "--show-current"], cwd=wt,
                                capture_output=True, text=True).stdout.strip()
        self.assertEqual(branch, "fan-out/t1")
        status = subprocess.run(["git", "status", "--porcelain"], cwd=self.alpha,
                                capture_output=True, text=True).stdout
        self.assertEqual(status, "", "the main checkout must stay clean")

    def test_checkout_without_a_session_starts_a_new_one(self):
        self.assertEqual(self.run_one(self.beta)[0], 0)
        self.assertNotIn("--resume", self.recorded("beta.worktrees_fan-out-t1")["argv"])
        self.assertIsNone(self.outcome("beta")["resumed_from"])

    def test_checkout_run_uses_continue_where_there_is_a_session(self):
        self.assertEqual(self.run_one(self.alpha, "--where", "checkout")[0], 0)
        alpha = self.recorded("src_alpha")
        self.assertEqual(Path(alpha["cwd"]).resolve(), self.alpha)
        self.assertIn("--continue", alpha["argv"])
        self.assertIn("--fork-session", alpha["argv"])
        self.assertEqual(self.run_one(self.beta, "--where", "checkout")[0], 0)
        self.assertEqual(self.recorded("src_beta")["argv"][:2], ["-p", "do the thing"])

    def test_new_session_ignores_earlier_ones(self):
        self.assertEqual(self.run_one(self.alpha, "--where", "checkout", "--session", "new")[0], 0)
        self.assertNotIn("--continue", self.recorded("src_alpha")["argv"])

    def test_exit_status_says_how_it_ended(self):
        self.assertEqual(self.run_one(self.alpha, "--where", "checkout", mode="fail")[0], 1)
        self.assertEqual(self.outcome("alpha")["status"], "failed")
        self.assertEqual(self.run_one(self.alpha, "--where", "checkout", mode="limit")[0], 255)
        self.assertEqual(self.outcome("alpha")["status"], "limit")

    def test_label_names_the_log_files(self):
        self.assertEqual(self.run_one(self.alpha, "--label", "alpha-main")[0], 0)
        self.assertTrue((self.logs / "alpha-main.stream.jsonl").is_file())
        self.assertEqual(self.outcome("alpha-main")["label"], "alpha-main")

    def make_alpha_dirty(self):
        (self.alpha / "README.md").write_text("edited, not committed\n")
        (self.alpha / "new.txt").write_text("untracked\n")

    def test_dirty_checkout_continues_with_a_note_naming_its_uncommitted_paths(self):
        self.make_alpha_dirty()
        self.assertEqual(self.run_one(self.alpha)[0], 0)
        argv = self.recorded("alpha.worktrees_fan-out-t1")["argv"]
        prompt = argv[1]
        self.assertTrue(prompt.startswith("Note from the headless runner"), prompt)
        self.assertIn("- README.md", prompt)
        self.assertIn("- new.txt", prompt)
        self.assertTrue(prompt.endswith("do the thing"))
        self.assertIn("--resume", argv)

    def test_dirty_new_starts_a_fresh_session(self):
        self.make_alpha_dirty()
        self.assertEqual(self.run_one(self.alpha, "--dirty", "new")[0], 0)
        argv = self.recorded("alpha.worktrees_fan-out-t1")["argv"]
        self.assertNotIn("--resume", argv)
        self.assertEqual(argv[1], "do the thing")

    def test_dirty_skip_does_not_run(self):
        self.make_alpha_dirty()
        self.assertEqual(self.run_one(self.alpha, "--dirty", "skip")[0], 3)
        self.assertEqual(self.outcome("alpha")["status"], "skipped")
        self.assertIn("uncommitted", self.outcome("alpha")["result"])
        self.assertFalse(run_headless.worktree_path(self.alpha, "t1").exists())

    def test_dirty_checkout_runs_in_place_untouched_by_the_note(self):
        self.make_alpha_dirty()
        self.assertEqual(self.run_one(self.alpha, "--where", "checkout")[0], 0)
        self.assertEqual(self.recorded("src_alpha")["argv"][1], "do the thing")

    def test_progress_lines_go_to_stderr(self):
        code, out = self.run_one(self.alpha, "--where", "checkout", "--progress-every", "0.5",
                                 mode="slow")
        self.assertEqual(code, 0)
        self.assertIn("start   alpha", self.stderr)
        self.assertRegex(self.stderr, r"\.\.\.     alpha \d+s, 1 tools, last Bash")
        self.assertRegex(self.stderr, r"ok      alpha \(3 turns\)")
        self.assertEqual(len(out.splitlines()), 1, "stdout holds only the outcome line")

    def test_dry_run_creates_nothing(self):
        self.assertEqual(self.run_one(self.alpha, "--dry-run")[0], 0)
        self.assertFalse(run_headless.worktree_path(self.alpha, "t1").exists())
        self.assertEqual(list(self.record.iterdir()), [])

    def test_rerun_reuses_the_jobs_worktree(self):
        self.assertEqual(self.run_one(self.alpha)[0], 0)
        self.assertEqual(self.run_one(self.alpha)[0], 0)
        notes = self.outcome("alpha")["notes"]
        self.assertTrue(any(n.startswith("reused") for n in notes), notes)

    def test_xargs_fan_out_stops_after_a_usage_limit(self):
        listing = f"{self.alpha}\n{self.beta}\n"
        cmd = ["xargs", "-P", "1", "-I{}", sys.executable, "-I", str(SCRIPTS / "run_headless.py"),
               *self.common(), "--where", "checkout", "{}"]
        env = {**os.environ, **self.env, "FAKE_CLAUDE_MODE": "limit"}
        env.pop("ANTHROPIC_API_KEY", None)
        proc = subprocess.run(cmd, input=listing, text=True, capture_output=True, env=env)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(self.outcome("alpha")["status"], "limit")
        self.assertFalse((self.record / "src_beta.json").exists(), "beta must not start")


if __name__ == "__main__":
    unittest.main(verbosity=2)
