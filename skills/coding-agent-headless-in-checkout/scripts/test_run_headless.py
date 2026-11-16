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
from unittest import mock

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
    print(json.dumps({{"type": "system", "subtype": "init", "session_id": "sess-1"}}), flush=True)
    if mode == "slow":
        import time
        print(json.dumps({{"type": "assistant", "message": {{"id": "m1", "content": [
            {{"type": "text", "text": "Plan.\\n⛳ skills/coding-agent-usage-line-report-eta: ETA 4m"}}]}}}}), flush=True)
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


ETA = "⛳ skills/coding-agent-usage-line-report-eta: ETA"


def assistant(text: str, **extra: object) -> dict:
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}, **extra}


class Status(unittest.TestCase):
    def test_last_eta_takes_the_last_line_and_its_timestamp(self):
        events = [assistant(f"{ETA} 10m", timestamp="2026-11-16T01:00:00Z"),
                  assistant("no figure here"),
                  assistant(f"done soon\n{ETA} 90s — tests", timestamp="2026-11-16T01:05:00Z")]
        self.assertEqual(run_headless.last_eta(events),
                         {"figure": "90s", "seconds": 90.0, "count": 2, "at": "2026-11-16T01:05:00Z"})
        self.assertEqual(run_headless.last_eta([assistant(f"{ETA} 2h")])["seconds"], 7200.0)

    def test_last_eta_ignores_placeholders_and_other_speakers(self):
        self.assertIsNone(run_headless.last_eta([assistant(f"{ETA} <n><s|m|h>")]))
        self.assertIsNone(run_headless.last_eta([{"type": "user", "message": {
            "content": [{"type": "text", "text": f"{ETA} 4m"}]}}]))
        self.assertIsNone(run_headless.last_eta([assistant(f"{ETA} 4min")]))

    def test_eta_without_a_timestamp_keeps_the_time_it_was_first_seen(self):
        eta = run_headless.last_eta([assistant(f"{ETA} 4m")])
        first = run_headless.eta_with_time(eta, None, 0)
        self.assertEqual(first["at"], "1970-01-01T00:00:00+00:00")
        self.assertEqual(run_headless.eta_with_time(eta, first, 600)["at"], first["at"])
        newer = run_headless.last_eta([assistant(f"{ETA} 4m"), assistant(f"{ETA} 4m")])
        self.assertEqual(run_headless.eta_with_time(newer, first, 600)["at"],
                         "1970-01-01T00:10:00+00:00")

    def test_stream_progress_counts_turns_and_tools(self):
        tool = lambda name: {"type": "tool_use", "id": "t", "name": name, "input": {}}  # noqa: E731
        events = [
            {"type": "system", "subtype": "init", "session_id": "s1"},
            {"type": "assistant", "message": {"id": "m1", "content": [tool("Read")]}},
            {"type": "assistant", "message": {"id": "m1", "content": [tool("Bash")]}},
            {"type": "assistant", "message": {"id": "m2", "content": [tool("Edit")]}},
            {"type": "user", "message": {"content": "x"}},
        ]
        self.assertEqual(run_headless.stream_progress(events),
                         {"session_id": "s1", "turns": 2, "tool_calls": 3, "last_tool": "Edit"})
        done = [*events, {"type": "result", "num_turns": 7, "session_id": "s1"}]
        self.assertEqual(run_headless.stream_progress(done)["turns"], 7)
        self.assertEqual(run_headless.stream_progress([])["session_id"], None)

    def test_parent_prefers_claude_codes_exports(self):
        self.assertEqual(
            run_headless.parent_of({"CLAUDE_CODE_SESSION_ID": "abc", "CLAUDE_PID": "42"}, 7, "/w"),
            {"session_id": "abc", "pid": 42, "cwd": "/w"})
        self.assertEqual(run_headless.parent_of({}, 7, "/w"),
                         {"session_id": None, "pid": 7, "cwd": "/w"})

    def test_status_record_lets_the_outcome_win_and_stamps_times(self):
        record = run_headless.status_record(
            {"job": "j", "label": "l"}, "ok",
            progress={"session_id": "s1", "turns": 2, "tool_calls": 3, "last_tool": "Bash"},
            eta=None, previous={}, started=0, now=60, ended=60,
            final={"turns": 5, "session_id": None})
        self.assertEqual((record["state"], record["turns"], record["session_id"]), ("ok", 5, "s1"))
        self.assertEqual((record["started"], record["updated"], record["ended"]),
                         ("1970-01-01T00:00:00+00:00", "1970-01-01T00:01:00+00:00",
                          "1970-01-01T00:01:00+00:00"))

    def test_write_status_replaces_the_file_whole(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.status.json"
            run_headless.write_status(path, {"state": "running"})
            run_headless.write_status(path, {"state": "ok"})
            self.assertEqual(json.loads(path.read_text()), {"state": "ok"})
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["x.status.json"])


class FakeLibc:
    """Stands in for libc: sysctlbyname writes `value` through the pointer, returns `status`."""

    def __init__(self, value: int, status: int = 0):
        self.value, self.status, self.asked = value, status, None

    def sysctlbyname(self, name, oldp, oldlenp, newp, newlen):
        import ctypes
        self.asked = name
        ctypes.cast(oldp, ctypes.POINTER(ctypes.c_int))[0] = self.value
        return self.status


class Admission(unittest.TestCase):
    def test_decision_is_a_function_of_level_and_time_waited(self):
        decide = run_headless.admission_decision
        self.assertEqual(decide(1, 0, None), "start")
        self.assertEqual(decide(1, 999, 10), "start")
        for level in (2, 4):
            self.assertEqual(decide(level, 0, None), "wait")
            self.assertEqual(decide(level, 9999, None), "wait")
            self.assertEqual(decide(level, 9, 10), "wait")
            self.assertEqual(decide(level, 10, 10), "give_up")

    def test_taskpolicy_prefix_is_macos_only(self):
        self.assertEqual(run_headless.taskpolicy_prefix("darwin"), ["taskpolicy", "-c", "utility"])
        self.assertEqual(run_headless.taskpolicy_prefix("linux"), [])

    def test_reading_the_level_through_sysctlbyname(self):
        libc = FakeLibc(4)
        self.assertEqual(run_headless.read_pressure_level("darwin", lambda: libc), (4, None))
        self.assertEqual(libc.asked, b"kern.memorystatus_vm_pressure_level")
        self.assertEqual(run_headless.read_pressure_level("linux", lambda: libc), (1, None))

    def test_any_failure_to_read_counts_as_level_one_with_a_note(self):
        def broken():
            raise OSError("no libc")
        for load in (broken, lambda: FakeLibc(2, status=-1), lambda: FakeLibc(3), lambda: object()):
            level, note = run_headless.read_pressure_level("darwin", load)
            self.assertEqual(level, 1)
            self.assertIn("counted as 1", note)

    def test_waits_until_the_level_drops_then_starts(self):
        levels, now, slept = iter([2, 4, 2, 1]), [0.0], []
        def sleep(seconds):
            slept.append(seconds)
            now[0] += seconds
        with contextlib.redirect_stderr(io.StringIO()) as err:
            result = run_headless.await_admission(
                "x", None, read=lambda: (next(levels), None), sleep=sleep,
                clock=lambda: now[0], poll=5)
        self.assertEqual((result.action, result.waited, slept), ("start", 15.0, [5, 5, 5]))
        self.assertEqual(err.getvalue().count("waiting x"), 3)
        self.assertIn("memory pressure level 4", err.getvalue())
        self.assertTrue(result.notes)

    def test_gives_up_after_the_timeout(self):
        now = [0.0]
        def sleep(seconds):
            now[0] += seconds
        with contextlib.redirect_stderr(io.StringIO()):
            result = run_headless.await_admission(
                "x", 12, read=lambda: (2, None), sleep=sleep, clock=lambda: now[0], poll=5)
        self.assertEqual((result.action, result.waited), ("give_up", 15.0))

    def test_normal_pressure_starts_without_a_note(self):
        result = run_headless.await_admission("x", None, read=lambda: (1, None), sleep=None)
        self.assertEqual((result.action, result.notes), ("start", ()))


class Runs(unittest.TestCase):
    def setUp(self):
        self.level = mock.patch.object(run_headless, "read_pressure_level", return_value=(1, None))
        self.level.start()
        self.addCleanup(self.level.stop)
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
        # A fake `taskpolicy`, since a sandbox may refuse the real one: it notes
        # its arguments, then runs the command that follows `-c utility`.
        policy = bin_dir / "taskpolicy"
        policy.write_text('#!/bin/sh\necho "$1 $2" >> "$FAKE_CLAUDE_RECORD/taskpolicy.txt"\nshift 2\nexec "$@"\n')
        policy.chmod(0o755)
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
        code, out = self.run_one(self.alpha, "--session", "continue")
        self.assertEqual(code, 0)
        argv = self.recorded("alpha.worktrees_headless-t1")["argv"]
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
        self.assertEqual(branch, "headless/t1")
        status = subprocess.run(["git", "status", "--porcelain"], cwd=self.alpha,
                                capture_output=True, text=True).stdout
        self.assertEqual(status, "", "the main checkout must stay clean")

    def test_checkout_without_a_session_starts_a_new_one(self):
        self.assertEqual(self.run_one(self.beta)[0], 0)
        self.assertNotIn("--resume", self.recorded("beta.worktrees_headless-t1")["argv"])
        self.assertIsNone(self.outcome("beta")["resumed_from"])

    def test_checkout_run_uses_continue_where_there_is_a_session(self):
        self.assertEqual(self.run_one(self.alpha, "--where", "checkout", "--session", "continue")[0], 0)
        alpha = self.recorded("src_alpha")
        self.assertEqual(Path(alpha["cwd"]).resolve(), self.alpha)
        self.assertIn("--continue", alpha["argv"])
        self.assertIn("--fork-session", alpha["argv"])
        self.assertEqual(self.run_one(self.beta, "--where", "checkout", "--session", "continue")[0], 0)
        self.assertEqual(self.recorded("src_beta")["argv"][:2], ["-p", "do the thing"])

    def test_new_session_ignores_earlier_ones(self):
        self.assertEqual(self.run_one(self.alpha, "--where", "checkout", "--session", "new")[0], 0)
        self.assertNotIn("--continue", self.recorded("src_alpha")["argv"])

    def test_pressure_holds_a_run_until_it_eases(self):
        with mock.patch.object(run_headless, "read_pressure_level",
                               side_effect=[(2, None), (2, None), (1, None)]):
            code, out = self.run_one(self.beta, "--admission-poll", "0")
        self.assertEqual(code, 0)
        self.assertEqual(self.stderr.count("waiting beta"), 2)
        self.assertIn("waited", " ".join(json.loads(out)["notes"]))

    def test_admission_timeout_skips_the_run(self):
        with mock.patch.object(run_headless, "read_pressure_level", return_value=(4, None)):
            code, out = self.run_one(self.beta, "--admission-timeout", "0", "--admission-poll", "0")
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(out)["status"], "skipped")
        self.assertIn("level 4", json.loads(out)["result"])
        self.assertFalse(any(self.record.iterdir()), "claude must not have started")
        self.assertFalse(run_headless.worktree_path(self.beta, "t1").exists())

    def test_no_admission_starts_at_once_and_never_reads_the_level(self):
        with mock.patch.object(run_headless, "read_pressure_level", return_value=(4, None)) as read:
            code, _ = self.run_one(self.beta, "--no-admission")
        self.assertEqual(code, 0)
        read.assert_not_called()

    def test_run_carries_the_priority_prefix_ahead_of_claude(self):
        with mock.patch.object(run_headless.sys, "platform", "darwin"):
            code, _ = self.run_one(self.beta)
        self.assertEqual(code, 0)
        self.assertEqual((self.record / "taskpolicy.txt").read_text(), "-c utility\n")
        self.assertEqual(self.recorded("beta.worktrees_headless-t1")["argv"][:2], ["-p", "do the thing"])

    def test_dry_run_shows_the_prefix_and_the_level_it_read(self):
        with mock.patch.object(run_headless.sys, "platform", "darwin"), \
                mock.patch.object(run_headless, "read_pressure_level", return_value=(2, None)):
            code, out = self.run_one(self.beta, "--dry-run")
        plan = json.loads(out)
        self.assertEqual((code, plan["prefix"], plan["pressure_level"]),
                         (0, ["taskpolicy", "-c", "utility"], 2))
        code, out = self.run_one(self.beta, "--dry-run", "--no-admission")
        self.assertIsNone(json.loads(out)["pressure_level"])

    def test_new_session_is_the_default(self):
        self.assertEqual(self.run_one(self.alpha, "--where", "checkout")[0], 0)
        self.assertNotIn("--continue", self.recorded("src_alpha")["argv"])
        self.assertIsNone(self.outcome("alpha")["resumed_from"])

    def test_continuing_a_recent_session_warns_that_it_may_be_live(self):
        self.assertEqual(self.run_one(self.alpha, "--where", "checkout", "--session", "continue")[0], 0)
        self.assertIn("warning alpha: session 11111111 was written", self.stderr)
        self.assertTrue(any("may still be running" in n for n in self.outcome("alpha")["notes"]))

    def test_continuing_an_old_session_does_not_warn(self):
        old = time.time() - 3600
        os.utime(self.alpha_session, (old, old))
        self.assertEqual(self.run_one(self.alpha, "--where", "checkout", "--session", "continue")[0], 0)
        self.assertNotIn("may still be running", self.stderr)
        os.utime(self.alpha_session)
        self.assertEqual(self.run_one(self.alpha, "--where", "checkout", "--session", "continue",
                                      "--live-within", "0")[0], 0)
        self.assertNotIn("may still be running", self.stderr)

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
        self.assertEqual(self.run_one(self.alpha, "--session", "continue")[0], 0)
        argv = self.recorded("alpha.worktrees_headless-t1")["argv"]
        prompt = argv[1]
        self.assertTrue(prompt.startswith("Note from the headless runner"), prompt)
        self.assertIn("- README.md", prompt)
        self.assertIn("- new.txt", prompt)
        self.assertTrue(prompt.endswith("do the thing"))
        self.assertIn("--resume", argv)

    def test_dirty_new_starts_a_fresh_session(self):
        self.make_alpha_dirty()
        self.assertEqual(self.run_one(self.alpha, "--session", "continue", "--dirty", "new")[0], 0)
        argv = self.recorded("alpha.worktrees_headless-t1")["argv"]
        self.assertNotIn("--resume", argv)
        self.assertEqual(argv[1], "do the thing")

    def test_dirty_skip_does_not_run(self):
        self.make_alpha_dirty()
        self.assertEqual(self.run_one(self.alpha, "--session", "continue", "--dirty", "skip")[0], 3)
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

    def status(self, label: str) -> dict:
        return json.loads((self.logs / f"{label}.status.json").read_text())

    def test_status_file_says_how_the_run_ended_and_who_started_it(self):
        self.env["CLAUDE_CODE_SESSION_ID"] = "parent-sess"
        self.assertEqual(self.run_one(self.alpha)[0], 0)
        status = self.status("alpha")
        self.assertEqual((status["state"], status["job"], status["label"], status["branch"]),
                         ("ok", "t1", "alpha", "headless/t1"))
        self.assertEqual((status["session_id"], status["turns"]), ("sess-1", 3))
        self.assertEqual(status["parent"]["session_id"], "parent-sess")
        self.assertEqual(status["pid"], os.getpid())
        wt = run_headless.worktree_path(self.alpha, "t1")
        self.assertEqual(status["transcript"],
                         str(self.projects / run_headless.project_key(wt) / "sess-1.jsonl"))
        self.assertIsNotNone(status["ended"])
        self.assertEqual(status["log"], str(self.logs / "alpha.stream.jsonl"))

    def test_status_file_is_rewritten_while_the_session_runs(self):
        seen: list[dict] = []
        write = run_headless.write_status

        def spy(path: Path, record: dict) -> None:
            seen.append(record)
            write(path, record)

        with mock.patch.object(run_headless, "write_status", side_effect=spy):
            code, _ = self.run_one(self.alpha, "--where", "checkout", "--status-every", "0.3",
                                   mode="slow")
        self.assertEqual(code, 0)
        running = [r for r in seen if r["state"] == "running"]
        self.assertGreaterEqual(len(running), 2)
        late = running[-1]
        self.assertEqual((late["tool_calls"], late["last_tool"], late["eta"]["figure"]),
                         (1, "Bash", "4m"))
        self.assertIsNone(late["ended"])
        self.assertEqual(seen[-1]["state"], "ok")
        self.assertEqual(seen[-1]["eta"]["at"], late["eta"]["at"])
        self.assertEqual(seen[-1]["branch"], "main")

    def test_status_file_shows_waiting_then_skipped(self):
        with mock.patch.object(run_headless, "read_pressure_level", return_value=(4, None)):
            self.run_one(self.beta, "--admission-timeout", "0", "--admission-poll", "0")
        status = self.status("beta")
        self.assertEqual((status["state"], status["session_id"], status["tool_calls"]),
                         ("skipped", None, 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
