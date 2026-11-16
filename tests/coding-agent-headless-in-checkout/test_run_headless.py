#!/usr/bin/env python3
"""Tests for run_headless.py: the pieces, then whole runs against a fake `claude`.

Run with `skills-dev test coding-agent-headless-in-checkout`. Needs `git` and `xargs` on PATH;
uses no network and no real Claude Code.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from typing import Callable
from unittest import mock

import run_headless

SCRIPTS = Path(run_headless.__file__).resolve().parent

FAKE_CLAUDE = textwrap.dedent(
    """\
    #!{python}
    # Records how it was called and its worktree's lock reason, null when unlocked,
    # then behaves as FAKE_CLAUDE_MODE says.
    import json, os, subprocess, sys
    cwd = os.getcwd()
    name = os.path.basename(os.path.dirname(cwd)) + "_" + os.path.basename(cwd)
    record = os.path.join(os.environ["FAKE_CLAUDE_RECORD"], name + ".json")
    def lock():
        gitdir = subprocess.run(["git", "rev-parse", "--absolute-git-dir"],
                                capture_output=True, text=True).stdout.strip()
        path = os.path.join(gitdir, "locked")
        return open(path).read().rstrip("\\n") if gitdir and os.path.isfile(path) else None
    def write(extra):
        with open(record, "w") as f:
            json.dump({{"argv": sys.argv[1:], "cwd": cwd, "locked": lock(), **extra}}, f)
    write({{}})
    mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
    if mode == "sweep":
        # A sweep run in the checkout while this session works, as another run's would.
        sweep = subprocess.run(["git-worktree-manager", "sweep"], cwd=os.environ["FAKE_CLAUDE_SWEEP_IN"],
                               capture_output=True, text=True)
        status = subprocess.run(["git-worktree-manager", "status", "--format", "json", cwd],
                                cwd=os.environ["FAKE_CLAUDE_SWEEP_IN"], capture_output=True, text=True)
        locks = [w.get("lock") for r in json.loads(status.stdout or "{{}}").get("repositories", [])
                 for w in r.get("worktrees", []) if os.path.realpath(w["path"]) == os.path.realpath(cwd)]
        write({{"sweep_exit": sweep.returncode, "left": os.path.isdir(cwd),
                "status_lock": locks[0] if locks else None}})
    if mode in ("unlock", "relock"):
        subprocess.run(["git", "worktree", "unlock", cwd], check=True)
    if mode == "relock":
        subprocess.run(["git", "worktree", "lock", "--reason", "someone else's", cwd], check=True)
    if mode == "move":
        os.rename(os.environ["FAKE_CLAUDE_MOVES"], os.environ["FAKE_CLAUDE_MOVES"] + ".gone")
    if mode == "limit":
        print(json.dumps({{"type": "result", "is_error": True, "result": "Claude usage limit reached"}}))
        sys.exit(1)
    if mode == "fail":
        print(json.dumps({{"type": "result", "is_error": True, "result": "tests failed"}}))
        sys.exit(1)
    print(json.dumps({{"type": "system", "subtype": "init", "session_id": "sess-1"}}), flush=True)
    if mode in ("commit", "commit-build"):
        import subprocess
        open("work.txt", "w").write("work\\n")
        subprocess.run(["git", "add", "work.txt"], check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
                        "commit", "-q", "-m", "work"], check=True)
    if mode in ("commit-build", "build"):
        os.makedirs("build")
        open(os.path.join("build", "out.o"), "w").write("output\\n")
    if mode == "dirty":
        open("scratch.txt", "w").write("left behind\\n")
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

# A stand-in for git-worktree-manager. It notes its working directory and
# arguments, one JSON line per call, then answers as the real program does: in
# JSON under `--format json`, else one line, with one more line on stderr. It
# exits with FAKE_MANAGER_EXIT_<command>, else FAKE_MANAGER_EXIT, else 0; an exit
# 3 from `finish` or `clean` carries reasons, `finish`'s the codes
# FAKE_MANAGER_FINISH_REASONS lists, `not-landed,uncommitted` by default, and an
# exit 1 errors. `finish` and `clean` note their target's lock reason, null when
# unlocked, in manager_locks.jsonl. `status` reports its target's lock, alive
# when FAKE_MANAGER_LOCK_ALIVE is `true`. A `sweep` renames the folder
# FAKE_MANAGER_SWEEP_MOVES names, when set. `disk` reports FAKE_MANAGER_FLOOR as
# the build floor, 70 by default, and `provision` reports its `direnv` step as
# FAKE_MANAGER_DIRENV, `done` by default.
FAKE_MANAGER = textwrap.dedent(
    """\
    #!{python}
    import json, os, subprocess, sys
    env, args = os.environ, sys.argv[1:]
    command, target = args[0], args[-1]
    with open(os.path.join(env["FAKE_CLAUDE_RECORD"], "manager.jsonl"), "a") as f:
        f.write(json.dumps([os.getcwd(), args]) + "\\n")
    def lock_reason():
        gitdir = subprocess.run(["git", "-C", target, "rev-parse", "--absolute-git-dir"],
                                capture_output=True, text=True).stdout.strip()
        lock = os.path.join(gitdir, "locked")
        return open(lock).read().rstrip("\\n") if gitdir and os.path.isfile(lock) else None
    if command in ("finish", "clean"):
        with open(os.path.join(env["FAKE_CLAUDE_RECORD"], "manager_locks.jsonl"), "a") as f:
            f.write(json.dumps([command, lock_reason()]) + "\\n")
    code = int(env.get("FAKE_MANAGER_EXIT_" + command, env.get("FAKE_MANAGER_EXIT", "0")))
    kept, failed = code == 3, code == 1
    details = {{"not-landed": "HEAD is not merged into refs/remotes/origin/main",
                "uncommitted": "1 uncommitted paths: u.txt", "locked": "locked: someone else's"}}
    finish_codes = env.get("FAKE_MANAGER_FINISH_REASONS", "not-landed,uncommitted").split(",")
    if command == "sweep" and env.get("FAKE_MANAGER_SWEEP_MOVES"):
        os.rename(env["FAKE_MANAGER_SWEEP_MOVES"], env["FAKE_MANAGER_SWEEP_MOVES"] + ".gone")
    replies = {{
        "status": {{"schema": 1, "command": "status", "dry_run": True, "repositories": [
            {{"worktrees": [{{"path": target, "lock": {{
                "reason": lock_reason(), "alive": env.get("FAKE_MANAGER_LOCK_ALIVE") == "true"}}}}]}}]}}
            if command == "status" else {{}},
        "disk": {{"schema": 1, "command": "disk", "disks": [],
                  "floors": {{"build_gb": float(env.get("FAKE_MANAGER_FLOOR", "70")),
                              "cleanup_only_gb": 35.0}}}},
        "provision": {{"schema": 1, "command": "provision", "worktree": target, "steps": [
            {{"step": "repo", "outcome": "done", "detail": "wrote REPO"}},
            {{"step": "direnv", "outcome": env.get("FAKE_MANAGER_DIRENV", "done"),
              "detail": "stub direnv step"}}]}},
        "clean": {{"schema": 1, "command": "clean", "dry_run": False, "worktree": target,
                   "outcome": "none" if kept else "done", "build_output": [],
                   "errors": [{{"path": target, "error": "stub deletion failed"}}] if failed else [],
                   "reasons": [{{"code": "locked", "detail": "it is locked: held by pid 1"}}] if kept else []}},
        "finish": {{"schema": 1, "command": "finish", "dry_run": False, "repositories": [
            {{"worktrees": [{{"path": target, "action": "keep" if kept else "remove",
                             **({{"error": "stub removal failed"}} if failed else {{}}), "reasons": [
                {{"code": c, "detail": details[c]}} for c in finish_codes] if kept else []}}]}}]}},
    }}
    if "--format" in args:
        print(json.dumps(replies[command]))
    else:
        print("stub " + command + " done")
    print("stub " + command + " said", file=sys.stderr)
    sys.exit(code)
    """
)
DISK_CALL = ["disk", "--format", "json"]
SWEEP_CALL = ["sweep"]
FAKE_DIRENV = '#!/bin/sh\necho "$*" >> "$FAKE_CLAUDE_RECORD/direnv.txt"\nshift 2\nexec "$@"\n'
MANAGER = "git-worktree-manager"
FLOOR_KEYS = ("WORKTREE_MANAGER_FLOOR_BUILD_GB", "WORKTREE_MANAGER_FLOOR_CLEANUP_ONLY_GB")


def git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def lock_of_worktree(path: Path) -> str | None:
    """The worktree's lock reason, as git keeps it in the worktree's own git folder; None
    when it is unlocked."""
    gitdir = subprocess.run(["git", "-C", str(path), "rev-parse", "--absolute-git-dir"],
                            capture_output=True, text=True, check=True).stdout.strip()
    lock = Path(gitdir) / "locked"
    return lock.read_text().rstrip("\n") if lock.is_file() else None


def dead_pid() -> int:
    """The pid of a process that has ended."""
    proc = subprocess.Popen(["true"])
    proc.wait()
    return proc.pid


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

    def test_a_disk_shortfall_holds_the_run_like_memory_pressure(self):
        decide = run_headless.admission_decision
        short = ("60 GB free on /nix, below the 70 GB build floor",)
        self.assertEqual(decide(1, 0, None, short), "wait")
        self.assertEqual(decide(1, 10, 10, short), "give_up")
        self.assertEqual(decide(1, 10, 10, ()), "start")

    def test_waits_for_disk_space_then_starts(self):
        shortfalls, now = iter([("low on /nix",), ("low on /nix",), ()]), [0.0]
        def sleep(seconds):
            now[0] += seconds
        with contextlib.redirect_stderr(io.StringIO()) as err:
            result = run_headless.await_admission(
                "x", None, read=lambda: (1, None), disk=lambda: next(shortfalls),
                sleep=sleep, clock=lambda: now[0], poll=5)
        self.assertEqual((result.action, result.waited), ("start", 10.0))
        self.assertIn("waiting x 0s: low on /nix", err.getvalue())
        self.assertEqual(result.notes, ("waited 10s for disk space before starting",))


class Disk(unittest.TestCase):
    DISK = json.dumps({"schema": 1, "command": "disk",
                       "floors": {"build_gb": 50.0, "cleanup_only_gb": 20.0},
                       "disks": [{"path": "/nix", "free_gb": 254.5, "state": "ok"}]})

    def test_the_floor_is_the_one_disk_reports(self):
        reply = (0, self.DISK)
        self.assertEqual(run_headless.build_floor(reply, {}), (50.0, None))
        self.assertEqual(run_headless.build_floor(reply, {"WORKTREE_MANAGER_FLOOR_BUILD_GB": "90"}),
                         (50.0, None), "the program reads the variable itself")

    def test_without_the_program_the_floor_is_the_variable_else_70(self):
        self.assertEqual(run_headless.build_floor(None, {}), (70.0, None))
        self.assertEqual(run_headless.build_floor(None, {"WORKTREE_MANAGER_FLOOR_BUILD_GB": "90"}),
                         (90.0, None))

    def test_a_floor_that_is_not_a_number_falls_back_to_70_with_a_note(self):
        gb, note = run_headless.build_floor(None, {"WORKTREE_MANAGER_FLOOR_BUILD_GB": "lots"})
        self.assertEqual(gb, 70.0)
        self.assertIn("'lots'", note)

    def test_a_floor_that_is_infinite_nan_zero_or_negative_falls_back_to_70_with_a_note(self):
        for value in ("inf", "-inf", "nan", "0", "-5"):
            with self.subTest(value=value):
                gb, note = run_headless.build_floor(None, {"WORKTREE_MANAGER_FLOOR_BUILD_GB": value})
                self.assertEqual(gb, 70.0)
                self.assertIn(f"{value!r} from WORKTREE_MANAGER_FLOOR_BUILD_GB is not a finite number "
                              "of GB above 0", note)

    def test_a_reported_floor_that_is_infinite_or_nan_is_no_floor(self):
        for value in ("Infinity", "NaN", "-1"):
            with self.subTest(value=value):
                reply = (0, f'{{"schema": 1, "command": "disk", "floors": {{"build_gb": {value}}}}}')
                self.assertEqual(run_headless.build_floor(reply, {})[0], 70.0)

    def test_a_reply_without_floors_falls_back_with_a_note_naming_the_call(self):
        error = json.dumps({"schema": 1, "command": "disk",
                            "error": {"code": "unreadable", "detail": "the build floor is below"}})
        for reply in ((0, '{"schema": 1, "command": "disk", "disks": []}'), (0, error),
                      (0, '{"schema": 1, "floors": {"build_gb": "lots"}}'),
                      (0, self.DISK.replace('"schema": 1', '"schema": 2')),
                      (0, "not json"), (0, "[]")):
            with self.subTest(reply=reply):
                gb, note = run_headless.build_floor(reply, {"WORKTREE_MANAGER_FLOOR_BUILD_GB": "90"})
                self.assertEqual(gb, 90.0)
                self.assertIn("git-worktree-manager disk --format json: exit 0, with no build floor", note)

    def test_a_disk_that_exits_non_zero_falls_back_with_a_note(self):
        for code in (1, 2, 127):
            with self.subTest(code=code):
                gb, note = run_headless.build_floor((code, self.DISK), {})
                self.assertEqual(gb, 70.0, "a failed call's output isn't read")
                self.assertEqual(note, f"git-worktree-manager disk --format json: exit {code}, "
                                       "with no build floor in its output; used 70 GB")

    def test_shortfalls_name_each_volume_under_the_floor(self):
        free = (("/w", 80 * 10**9), ("/nix", 60 * 10**9), ("/gone", None))
        self.assertEqual(run_headless.disk_shortfalls(free, 70),
                         ("60 GB free on /nix, below the 70 GB build floor",))

    def test_free_bytes_of_a_missing_path_is_none(self):
        self.assertIsNone(run_headless.free_bytes(Path("/no/such/volume/here")))


class Finishing(unittest.TestCase):
    FINISH_KEPT = json.dumps({"schema": 1, "command": "finish", "repositories": [{"worktrees": [{
        "path": "/wt", "action": "keep", "reasons": [
            {"code": "not-landed", "detail": "HEAD is not merged into refs/remotes/origin/main"},
            {"code": "uncommitted", "detail": "1 uncommitted paths: u.txt"}]}]}]})
    CLEAN_KEPT = json.dumps({"schema": 1, "command": "clean", "worktree": "/wt", "outcome": "none",
                             "reasons": [{"code": "locked", "detail": "it is locked: held by pid 1"}],
                             "build_output": [], "errors": []})

    def test_commits_decide_the_call_whatever_the_status(self):
        args = run_headless.finish_args
        self.assertEqual(args(0, "/wt"), ("finish", "--format", "json", "/wt"))
        self.assertEqual(args(2, "/wt"), ("clean", "--format", "json", "/wt"))

    def test_program_note_keeps_the_last_line(self):
        self.assertEqual(run_headless.program_note(("sweep",), 0, "a\ntotals: repositories 1\n"),
                         "git-worktree-manager sweep: exit 0: totals: repositories 1")
        self.assertEqual(run_headless.program_note(("sweep",), 1, ""), "git-worktree-manager sweep: exit 1")

    def test_exit_3_from_finish_keeps_the_worktree_with_every_reason(self):
        call = ("finish", "--format", "json", "/wt")
        self.assertEqual(run_headless.cleanup_note(call, 3, self.FINISH_KEPT, "/wt stays: …\n"),
                         "git-worktree-manager finish --format json /wt: kept the worktree: "
                         "not-landed: HEAD is not merged into refs/remotes/origin/main; "
                         "uncommitted: 1 uncommitted paths: u.txt")

    def test_exit_3_from_clean_keeps_the_worktree_with_its_reason(self):
        call = ("clean", "--format", "json", "/wt")
        self.assertEqual(run_headless.cleanup_note(call, 3, self.CLEAN_KEPT, ""),
                         "git-worktree-manager clean --format json /wt: kept the worktree: "
                         "locked: it is locked: held by pid 1")

    def test_exit_3_without_a_readable_reply_keeps_the_last_line_of_stderr(self):
        call = ("finish", "--format", "json", "/wt")
        self.assertEqual(run_headless.cleanup_note(call, 3, "not json", "a\n/wt stays: locked\n"),
                         "git-worktree-manager finish --format json /wt: kept the worktree: /wt stays: locked")

    def test_exit_1_from_finish_carries_the_errors_in_its_reply(self):
        call = ("finish", "--format", "json", "/wt")
        reply = json.dumps({"schema": 1, "command": "finish", "repositories": [{
            "problem": None,
            "worktrees": [{"path": "/wt", "outcome": "failed",
                           "error": "git worktree remove failed:\nfatal: '/wt' is locked"}],
            "branches": [{"name": "headless/t1", "outcome": "failed", "error": "ref moved"},
                         {"name": "other", "outcome": "done"}],
            "backup": {"compares": [{"ref": "refs/archive/a/1", "ok": False, "detail": "fsck failed"},
                                    {"ref": "refs/archive/b/1", "ok": True, "detail": None}]}}]})
        self.assertEqual(run_headless.cleanup_note(call, 1, reply, ""),
                         "git-worktree-manager finish --format json /wt: exit 1: "
                         "/wt: git worktree remove failed: fatal: '/wt' is locked; "
                         "branch headless/t1: ref moved; archive refs/archive/a/1: fsck failed")

    def test_exit_1_before_a_report_carries_its_error(self):
        call = ("finish", "--format", "json", "/wt")
        reply = json.dumps({"schema": 1, "command": "finish",
                            "error": {"code": "unreadable", "detail": "the repository can't be read"}})
        self.assertEqual(run_headless.cleanup_note(call, 1, reply, "the repository can't be read\n"),
                         "git-worktree-manager finish --format json /wt: exit 1: "
                         "unreadable: the repository can't be read")

    def test_exit_1_from_clean_carries_its_errors(self):
        call = ("clean", "--format", "json", "/wt")
        reply = json.dumps({"schema": 1, "command": "clean", "worktree": "/wt", "outcome": "failed",
                            "reasons": [], "build_output": ["/wt/build"],
                            "errors": [{"path": "/wt/build", "error": "Permission denied"}]})
        self.assertEqual(run_headless.cleanup_note(call, 1, reply, ""),
                         "git-worktree-manager clean --format json /wt: exit 1: /wt/build: Permission denied")

    def test_a_reply_that_is_not_schema_1_json_falls_back_to_stderr_then_the_code(self):
        call = ("finish", "--format", "json", "/wt")
        failed = {"command": "finish", "repositories": [{"worktrees": [{"path": "/wt", "error": "x"}]}]}
        for reply in ("not json", "[]", json.dumps(failed), json.dumps({**failed, "schema": 2})):
            with self.subTest(reply=reply):
                self.assertEqual(run_headless.cleanup_note(call, 1, reply, "a\nstep failed\n"),
                                 "git-worktree-manager finish --format json /wt: exit 1: step failed")
                self.assertEqual(run_headless.cleanup_note(call, 1, reply, ""),
                                 "git-worktree-manager finish --format json /wt: exit 1")

    def test_exit_0_is_the_bare_status(self):
        call = ("finish", "--format", "json", "/wt")
        self.assertEqual(run_headless.cleanup_note(call, 0, self.FINISH_KEPT, ""),
                         "git-worktree-manager finish --format json /wt: exit 0")

    def finish_reply(self, *codes: str) -> str:
        return json.dumps({"schema": 1, "command": "finish", "repositories": [{"worktrees": [{
            "path": "/wt", "action": "keep", "reasons": [{"code": c, "detail": "x"} for c in codes]}]}]})

    def test_clean_follows_a_finish_kept_as_not_landed_alone(self):
        finish = ("finish", "--format", "json", "/wt")
        follows = run_headless.follows_with_clean
        self.assertTrue(follows(finish, 3, self.finish_reply("not-landed")))
        self.assertTrue(follows(finish, 3, self.finish_reply("not-landed", "keep-pattern-files")))

    def test_no_clean_follows_uncommitted_changes_another_status_or_a_clean(self):
        finish, clean = ("finish", "--format", "json", "/wt"), ("clean", "--format", "json", "/wt")
        follows = run_headless.follows_with_clean
        self.assertFalse(follows(finish, 3, self.FINISH_KEPT), "not-landed with uncommitted")
        self.assertFalse(follows(finish, 3, self.finish_reply("uncommitted")))
        self.assertFalse(follows(finish, 3, self.finish_reply("locked")))
        self.assertFalse(follows(finish, 3, self.finish_reply("locked", "not-landed")),
                         "clean keeps a locked worktree")
        self.assertFalse(follows(finish, 3, "not json"))
        self.assertFalse(follows(finish, 0, self.finish_reply("not-landed")))
        self.assertFalse(follows(finish, 1, self.finish_reply("not-landed")))
        self.assertFalse(follows(clean, 3, self.finish_reply("not-landed")))

    def test_the_direnv_step_of_provision(self):
        reply = json.dumps({"schema": 1, "command": "provision", "worktree": "/wt", "steps": [
            {"step": "settings", "outcome": "failed", "detail": "x"},
            {"step": "direnv", "outcome": "skipped", "detail": "the worktree's .envrc differs"}]})
        self.assertEqual(run_headless.direnv_step(reply), ("skipped", "the worktree's .envrc differs"))
        self.assertEqual(run_headless.direnv_step("not json"), ("missing", "no direnv step in its output"))


class Locking(unittest.TestCase):
    def test_the_reason_reads_as_who_since_when(self):
        self.assertEqual(run_headless.lock_reason("t1", 42, 0),
                         "headless t1 pid 42 since 1970-01-01T00:00:00+00:00")

    def test_the_lock_in_a_worktrees_locked_file(self):
        lock_in = run_headless.lock_in
        self.assertEqual(lock_in("headless t1 pid 7 since 2026-11-19T07:00:00+00:00\n"),
                         "headless t1 pid 7 since 2026-11-19T07:00:00+00:00")
        self.assertEqual(lock_in(""), "", "a lock with no reason")
        self.assertEqual(lock_in("two\nlines\n"), "two\nlines")
        self.assertIsNone(lock_in(None), "no file, no lock")

    def test_the_pid_of_a_lock_a_run_of_the_job_took(self):
        lock_pid = run_headless.lock_pid
        self.assertEqual(lock_pid("headless t1 pid 7 since 2026-11-19T07:00:00+00:00", "t1"), 7)
        self.assertEqual(lock_pid("headless t1 pid 7", "t1"), 7)
        for other in ("headless t10 pid 7 since 2026-11-19T07:00:00+00:00", "someone else's", "",
                      "headless t1 since 2026-11-19T07:00:00+00:00", "headless t1 pid 0 since x",
                      "headless t1 pid x7 since x", "my headless t1 pid 7 since x",
                      "headless t1 pid ² since x", "headless t1 pid 1² since x", "headless t1 pid ٣ since x"):
            with self.subTest(other=other):
                self.assertIsNone(lock_pid(other, "t1"))

    def test_an_earlier_run_whose_process_is_gone_is_taken_over_and_any_other_left(self):
        action, ours = run_headless.lock_action, "headless t1 pid 7 since 2026-11-19T07:00:00+00:00"
        for alive in (True, False, None):
            self.assertEqual(action(None, "t1", alive), "lock")
        self.assertEqual(action(ours, "t1", False), "take")
        self.assertEqual(action(ours, "t1", True), "leave", "a live run of the job keeps its lock")
        self.assertEqual(action(ours, "t1", None), "leave", "a lock whose process is unknown is kept")
        for other in ("headless t10 pid 7 since 2026-11-19T07:00:00+00:00", "someone else's", "",
                      "headless t1 since 2026-11-19T07:00:00+00:00"):
            with self.subTest(other=other):
                self.assertEqual(action(other, "t1", False), "leave")

    def test_whether_the_lock_is_alive_by_status(self):
        def reply(lock: object, path: str = "/wt") -> str:
            return json.dumps({"schema": 1, "command": "status", "repositories": [
                {"worktrees": [{"path": "/w/app", "lock": None}, {"path": path, "lock": lock}]}]})
        alive = run_headless.status_lock_alive
        self.assertTrue(alive(reply({"reason": "r", "alive": True}), "/wt"))
        self.assertFalse(alive(reply({"reason": "r", "alive": False}), "/wt"))
        for stdout in (reply({"reason": "r", "alive": None}), reply({"reason": "r"}), reply(None),
                       reply({"alive": True}, "/other"), "not json", json.dumps({"schema": 2})):
            with self.subTest(stdout=stdout):
                self.assertIsNone(alive(stdout, "/wt"))

    def test_why_the_lock_was_left_at_the_end(self):
        note = run_headless.unreleased_note
        self.assertEqual(note(Path("/wt"), None), "the run's lock on /wt was gone when the session ended")
        self.assertEqual(note(Path("/wt"), "theirs"),
                         "left the lock on /wt as it is, since it is no longer this run's: theirs")


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
        # A fake `taskpolicy`, since a sandbox may refuse the real one: it notes
        # its arguments, then runs the command that follows `-c utility`.
        policy = bin_dir / "taskpolicy"
        policy.write_text('#!/bin/sh\necho "$1 $2" >> "$FAKE_CLAUDE_RECORD/taskpolicy.txt"\nshift 2\nexec "$@"\n')
        policy.chmod(0o755)
        # The stub git-worktree-manager sits in a folder of its own, off the PATH, so
        # a run finds it only through run_one's `program=True`, never a real one on
        # this machine.
        self.manager = base / "tools" / MANAGER
        self.manager.parent.mkdir()
        self.manager.write_text(FAKE_MANAGER.format(python=sys.executable))
        self.manager.chmod(0o755)
        direnv = bin_dir / "direnv"
        direnv.write_text(FAKE_DIRENV)
        direnv.chmod(0o755)
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

    def run_one(self, checkout: Path, *extra: str, mode: str = "ok",
                levels: tuple[int, ...] = (1,), platform: str = "linux",
                free_gb: float = 500, program: bool = False) -> tuple[int, str]:
        """main() in this process, for one checkout; returns its exit status and stdout.

        The memory pressure reader gives `levels` in turn, then repeats the last; `self.reads`
        counts its calls. `platform` stands in for sys.platform, `free_gb` for the free space
        on every volume, and `program` puts the stub git-worktree-manager in reach.
        """
        self.reads = 0

        def read() -> tuple[int, None]:
            self.reads += 1
            return levels[min(self.reads, len(levels)) - 1], None

        def find(name: str) -> str | None:
            return str(self.manager) if program and name == MANAGER else None

        env = {**self.env, "FAKE_CLAUDE_MODE": mode}
        old = {k: os.environ.get(k) for k in [*env, "ANTHROPIC_API_KEY", *FLOOR_KEYS]}
        os.environ.update(env)
        os.environ.pop("ANTHROPIC_API_KEY", None)
        for key in FLOOR_KEYS:
            if key not in env:
                os.environ.pop(key, None)
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = run_headless.main([*self.common(), *extra, str(checkout)],
                                         read=read, platform=platform,
                                         free=lambda _: int(free_gb * 10**9), find_program=find)
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

    def test_new_session_is_the_default_and_ignores_earlier_ones(self):
        for chosen in ([], ["--session", "new"]):
            with self.subTest(session=chosen or "default"):
                self.assertEqual(self.run_one(self.alpha, "--where", "checkout", *chosen)[0], 0)
                argv = self.recorded("src_alpha")["argv"]
                self.assertNotIn("--continue", argv)
                self.assertNotIn("--resume", argv)
                self.assertIsNone(self.outcome("alpha")["resumed_from"])

    def test_pressure_holds_a_run_until_it_eases(self):
        code, out = self.run_one(self.beta, "--admission-poll", "0", levels=(2, 2, 1))
        self.assertEqual(code, 0)
        self.assertEqual(self.stderr.count("waiting beta"), 2)
        self.assertIn("waited", " ".join(json.loads(out)["notes"]))

    def test_admission_timeout_skips_the_run(self):
        code, out = self.run_one(self.beta, "--admission-timeout", "0", "--admission-poll", "0",
                                 levels=(4,))
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(out)["status"], "skipped")
        self.assertIn("level 4", json.loads(out)["result"])
        self.assertFalse(any(self.record.iterdir()), "claude must not have started")
        self.assertFalse(run_headless.worktree_path(self.beta, "t1").exists())

    def test_no_admission_starts_under_pressure_that_would_skip_the_run(self):
        code, out = self.run_one(self.beta, "--no-admission", "--admission-timeout", "0",
                                 levels=(4,))
        self.assertEqual((code, json.loads(out)["status"]), (0, "ok"))
        self.assertTrue((self.record / "beta.worktrees_headless-t1.json").is_file(),
                        "claude must have started")
        self.assertNotIn("waiting", self.stderr)
        self.assertNotIn("pressure", " ".join(json.loads(out)["notes"]))
        self.assertEqual(self.reads, 0)

    def test_run_carries_the_priority_prefix_ahead_of_claude(self):
        code, _ = self.run_one(self.beta, platform="darwin")
        self.assertEqual(code, 0)
        self.assertEqual((self.record / "taskpolicy.txt").read_text(), "-c utility\n")
        self.assertEqual(self.recorded("beta.worktrees_headless-t1")["argv"][:2], ["-p", "do the thing"])

    def test_dry_run_shows_the_prefix_and_the_level_it_read(self):
        code, out = self.run_one(self.beta, "--dry-run", levels=(2,), platform="darwin")
        plan = json.loads(out)
        self.assertEqual((code, plan["prefix"], plan["pressure_level"]),
                         (0, ["taskpolicy", "-c", "utility"], 2))
        code, out = self.run_one(self.beta, "--dry-run", "--no-admission")
        self.assertIsNone(json.loads(out)["pressure_level"])

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

    def test_dirty_new_and_skip_warn_of_no_fork(self):
        for dirty in ("new", "skip"):
            with self.subTest(dirty=dirty):
                self.make_alpha_dirty()
                self.run_one(self.alpha, "--session", "continue", "--dirty", dirty)
                self.assertNotIn("may still be running", self.stderr)
                self.assertFalse(any("may still be running" in n for n in self.outcome("alpha")["notes"]))

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
        # Floors of 1 MB, the least above 0, so this machine's own free space never holds
        # the run, whether the floor comes from the variable or from a git-worktree-manager
        # on the PATH.
        env = {**os.environ, **self.env, "FAKE_CLAUDE_MODE": "limit", **dict.fromkeys(FLOOR_KEYS, "0.001")}
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
        self.run_one(self.beta, "--admission-timeout", "0", "--admission-poll", "0", levels=(4,))
        status = self.status("beta")
        self.assertEqual((status["state"], status["session_id"], status["tool_calls"]),
                         ("skipped", None, 0))

    # Disk admission.

    def test_below_the_default_floor_the_run_is_skipped_with_status_3(self):
        code, out = self.run_one(self.beta, "--admission-timeout", "0", "--admission-poll", "0",
                                 free_gb=60, program=True)
        self.assertEqual(code, 3)
        outcome = json.loads(out)
        self.assertEqual(outcome["status"], "skipped")
        self.assertIn("60 GB free", outcome["result"])
        self.assertIn("below the 70 GB build floor", outcome["result"])
        self.assertIsNone(outcome["cleanup"])
        self.assertEqual([p.name for p in self.record.iterdir()], ["manager.jsonl"], "claude must not have run")
        self.assertEqual(self.manager_calls(), [(str(self.beta), DISK_CALL)],
                         "git-worktree-manager only reported the floor")
        self.assertFalse(run_headless.worktree_path(self.beta, "t1").exists())

    def test_the_floor_comes_from_disk(self):
        held = ("--admission-timeout", "0", "--admission-poll", "0")
        self.env["FAKE_MANAGER_FLOOR"] = "50"
        self.assertEqual(self.run_one(self.beta, *held, free_gb=60, program=True)[0], 0)
        self.env["FAKE_MANAGER_FLOOR"] = "100"
        code, out = self.run_one(self.beta, *held, free_gb=60, program=True)
        self.assertEqual(code, 3)
        self.assertIn("below the 100 GB build floor", json.loads(out)["result"])

    def test_a_disk_that_exits_non_zero_falls_back_to_the_variable_with_a_warning(self):
        held = ("--admission-timeout", "0", "--admission-poll", "0")
        self.env.update(FAKE_MANAGER_EXIT_disk="1", FAKE_MANAGER_FLOOR="10",
                        WORKTREE_MANAGER_FLOOR_BUILD_GB="100")
        code, out = self.run_one(self.beta, *held, free_gb=60, program=True)
        self.assertEqual(code, 3)
        self.assertIn("below the 100 GB build floor", json.loads(out)["result"])
        self.assertIn("warning beta: git-worktree-manager disk --format json: exit 1, with no build floor",
                      self.stderr)

    def test_without_the_program_the_floor_is_the_variable(self):
        held = ("--admission-timeout", "0", "--admission-poll", "0")
        self.env["WORKTREE_MANAGER_FLOOR_BUILD_GB"] = "10"
        self.assertEqual(self.run_one(self.beta, *held, free_gb=60)[0], 0)
        self.env["WORKTREE_MANAGER_FLOOR_BUILD_GB"] = "100"
        code, out = self.run_one(self.beta, *held, free_gb=60)
        self.assertEqual(code, 3)
        self.assertIn("below the 100 GB build floor", json.loads(out)["result"])

    def test_dry_run_shows_the_floor_and_the_shortfall(self):
        plan = json.loads(self.run_one(self.beta, "--dry-run", free_gb=60, program=True)[1])
        self.assertEqual(plan["build_floor_gb"], 70.0)
        self.assertEqual(len(plan["disk_short"]), 2, "the checkout's volume and /nix")
        self.assertEqual(plan["worktree_manager"], str(self.manager))
        self.assertEqual(self.manager_calls(), [(str(self.beta), DISK_CALL)])

    def test_no_admission_starts_below_the_floor(self):
        self.assertEqual(self.run_one(self.beta, "--no-admission", "--admission-timeout", "0",
                                      free_gb=1)[0], 0)

    # Finishing the worktree.

    def manager_calls(self) -> list[tuple[str, list[str]]]:
        """The stub git-worktree-manager's calls, each as (working directory, arguments)."""
        path = self.record / "manager.jsonl"
        lines = path.read_text().splitlines() if path.exists() else []
        return [tuple(json.loads(line)) for line in lines]

    def test_a_run_that_changed_nothing_is_finished(self):
        self.assertEqual(self.run_one(self.alpha, program=True)[0], 0)
        wt = str(run_headless.worktree_path(self.alpha, "t1"))
        self.assertEqual(self.manager_calls(),
                         [(str(self.alpha), DISK_CALL), (str(self.alpha), SWEEP_CALL),
                          (str(self.alpha), ["finish", "--format", "json", wt])])
        self.assertEqual(self.outcome("alpha")["cleanup"],
                         f"git-worktree-manager finish --format json {wt}: exit 0: stub finish said")
        self.assertIn("[git-worktree-manager finish", self.stderr)

    def test_a_failed_run_without_commits_is_finished_the_same_way(self):
        self.assertEqual(self.run_one(self.alpha, mode="fail", program=True)[0], 1)
        wt = str(run_headless.worktree_path(self.alpha, "t1"))
        self.assertEqual(self.manager_calls()[-1], (str(self.alpha), ["finish", "--format", "json", wt]))

    def test_a_run_that_committed_is_cleaned_and_kept(self):
        self.assertEqual(self.run_one(self.alpha, mode="commit", program=True)[0], 0)
        wt = run_headless.worktree_path(self.alpha, "t1")
        self.assertEqual(self.manager_calls()[-1], (str(self.alpha), ["clean", "--format", "json", str(wt)]))
        self.assertTrue((wt / "work.txt").is_file())

    def test_exit_3_from_finish_is_kept_with_its_reasons_not_a_failure(self):
        self.env["FAKE_MANAGER_EXIT_finish"] = "3"
        self.assertEqual(self.run_one(self.alpha, program=True)[0], 0)
        wt = run_headless.worktree_path(self.alpha, "t1")
        self.assertEqual(self.outcome("alpha")["cleanup"],
                         f"git-worktree-manager finish --format json {wt}: kept the worktree: "
                         "not-landed: HEAD is not merged into refs/remotes/origin/main; "
                         "uncommitted: 1 uncommitted paths: u.txt")
        self.assertEqual(self.outcome("alpha")["status"], "ok")

    def test_exit_3_from_clean_is_kept_with_its_reason_not_a_failure(self):
        self.env["FAKE_MANAGER_EXIT_clean"] = "3"
        self.assertEqual(self.run_one(self.alpha, mode="commit", program=True)[0], 0)
        wt = run_headless.worktree_path(self.alpha, "t1")
        self.assertEqual(self.outcome("alpha")["cleanup"],
                         f"git-worktree-manager clean --format json {wt}: kept the worktree: "
                         "locked: it is locked: held by pid 1")

    def test_the_programs_failure_is_reported_not_fatal(self):
        self.env["FAKE_MANAGER_EXIT"] = "1"
        self.assertEqual(self.run_one(self.alpha, program=True)[0], 0)
        wt = run_headless.worktree_path(self.alpha, "t1")
        self.assertEqual(self.outcome("alpha")["cleanup"],
                         f"git-worktree-manager finish --format json {wt}: exit 1: {wt}: stub removal failed",
                         "the error in the JSON reply, not stderr")
        self.assertIn("git-worktree-manager sweep: exit 1: stub sweep said",
                      " ".join(self.outcome("alpha")["notes"]))

    def test_exit_1_from_clean_carries_the_error_in_its_reply(self):
        self.env["FAKE_MANAGER_EXIT_clean"] = "1"
        self.assertEqual(self.run_one(self.alpha, mode="commit", program=True)[0], 0)
        wt = run_headless.worktree_path(self.alpha, "t1")
        self.assertEqual(self.outcome("alpha")["cleanup"],
                         f"git-worktree-manager clean --format json {wt}: exit 1: {wt}: stub deletion failed")

    def kept_not_landed(self, wt: Path) -> str:
        return (f"git-worktree-manager finish --format json {wt}: kept the worktree: "
                "not-landed: HEAD is not merged into refs/remotes/origin/main; then ")

    def test_a_finish_kept_as_not_landed_alone_is_followed_by_clean(self):
        self.env.update(FAKE_MANAGER_EXIT_finish="3", FAKE_MANAGER_FINISH_REASONS="not-landed")
        self.assertEqual(self.run_one(self.alpha, program=True)[0], 0)
        wt = run_headless.worktree_path(self.alpha, "t1")
        self.assertEqual(self.manager_calls()[-2:],
                         [(str(self.alpha), ["finish", "--format", "json", str(wt)]),
                          (str(self.alpha), ["clean", "--format", "json", str(wt)])])
        self.assertEqual(self.outcome("alpha")["cleanup"], self.kept_not_landed(wt) +
                         f"git-worktree-manager clean --format json {wt}: exit 0: stub clean said")
        self.assertEqual(self.outcome("alpha")["status"], "ok")

    def test_no_clean_follows_a_finish_kept_for_uncommitted_changes(self):
        self.env["FAKE_MANAGER_EXIT_finish"] = "3"
        wt = run_headless.worktree_path(self.alpha, "t1")
        for reasons in ("uncommitted", "not-landed,uncommitted"):
            with self.subTest(reasons=reasons):
                self.env["FAKE_MANAGER_FINISH_REASONS"] = reasons
                self.assertEqual(self.run_one(self.alpha, program=True)[0], 0)
                self.assertEqual(self.manager_calls()[-1],
                                 (str(self.alpha), ["finish", "--format", "json", str(wt)]))
                self.assertNotIn("then", self.outcome("alpha")["cleanup"])

    def test_the_clean_after_a_finish_reports_its_own_failure_or_exit_3(self):
        self.env.update(FAKE_MANAGER_EXIT_finish="3", FAKE_MANAGER_FINISH_REASONS="not-landed")
        wt = run_headless.worktree_path(self.alpha, "t1")
        for code, said in (("1", f"exit 1: {wt}: stub deletion failed"),
                           ("3", "kept the worktree: locked: it is locked: held by pid 1")):
            with self.subTest(code=code):
                self.env["FAKE_MANAGER_EXIT_clean"] = code
                self.assertEqual(self.run_one(self.alpha, program=True)[0], 0)
                self.assertEqual(self.outcome("alpha")["cleanup"], self.kept_not_landed(wt) +
                                 f"git-worktree-manager clean --format json {wt}: {said}")
                self.assertEqual(self.outcome("alpha")["status"], "ok")

    # Locking the worktree while its session runs.

    def manager_locks(self) -> list[list[str | None]]:
        """Each `finish` and `clean` call of the stub with its target's lock reason then."""
        path = self.record / "manager_locks.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def session_lock(self) -> str | None:
        return self.recorded("alpha.worktrees_headless-t1")["locked"]

    def test_the_worktree_is_locked_while_the_session_runs(self):
        self.assertEqual(self.run_one(self.alpha)[0], 0)
        self.assertRegex(self.session_lock(),
                         rf"^headless t1 pid {os.getpid()} since \d{{4}}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00$")

    def test_the_lock_is_released_however_the_run_ends(self):
        wt = run_headless.worktree_path(self.alpha, "t1")
        endings = {"finished": ((), "ok", True), "failed": ((), "fail", True),
                   "cleaned": ((), "commit", True), "--keep-worktree": (("--keep-worktree",), "ok", True),
                   "no program": ((), "ok", False)}
        for ending, (extra, mode, program) in endings.items():
            with self.subTest(ending=ending):
                self.run_one(self.alpha, *extra, mode=mode, program=program)
                self.assertTrue(self.session_lock().startswith(f"headless t1 pid {os.getpid()} since "))
                self.assertIsNone(lock_of_worktree(wt))
                self.assertFalse(any("unlock" in note for note in self.outcome("alpha")["notes"]))
        self.assertEqual(self.manager_locks(), [["finish", None], ["finish", None], ["clean", None]],
                         "unlocked before the finish or clean call")

    def test_a_lock_gone_by_the_end_is_a_note(self):
        self.assertEqual(self.run_one(self.alpha, mode="unlock")[0], 0)
        wt = run_headless.worktree_path(self.alpha, "t1")
        self.assertIn(f"the run's lock on {wt} was gone when the session ended", self.outcome("alpha")["notes"])

    def test_a_lock_no_longer_the_runs_by_the_end_is_left(self):
        self.assertEqual(self.run_one(self.alpha, mode="relock", program=True)[0], 0)
        wt = run_headless.worktree_path(self.alpha, "t1")
        self.assertIn(f"left the lock on {wt} as it is, since it is no longer this run's: someone else's",
                      self.outcome("alpha")["notes"])
        self.assertEqual(lock_of_worktree(wt), "someone else's")
        self.assertEqual(self.manager_locks(), [["finish", "someone else's"]])

    def test_a_checkout_gone_during_the_session_still_ends_with_an_outcome(self):
        for checkout, extra, program in ((self.alpha, ("--keep-worktree",), True), (self.beta, (), False)):
            with self.subTest(checkout=checkout.name):
                self.env["FAKE_CLAUDE_MOVES"] = str(checkout)
                code, out = self.run_one(checkout, *extra, mode="move", program=program)
                self.assertEqual(code, 0)
                outcome = json.loads(out)
                self.assertEqual(outcome, self.outcome(checkout.name))
                wt = run_headless.worktree_path(checkout, "t1")
                self.assertTrue(any(note.startswith(f"left the lock on {wt}, which could not be read: ")
                                    for note in outcome["notes"]), outcome["notes"])
                self.assertTrue(outcome["cleanup"].startswith("kept the worktree"))

    def git_failing(self, failing: Callable[[tuple[str, ...]], bool], stderr: str):
        """`run_headless.git` patched to fail every call `failing` picks, with `stderr`."""
        real = run_headless.git

        def fake(*args: str, cwd: Path) -> subprocess.CompletedProcess:
            if failing(args):
                return subprocess.CompletedProcess(["git", *args], 129, "", stderr)
            return real(*args, cwd=cwd)

        return mock.patch.object(run_headless, "git", side_effect=fake)

    @staticmethod
    def reads_a_lock(args: tuple[str, ...]) -> bool:
        """The calls that read a worktree's lock, by `git worktree list` or by its git directory."""
        return args[:2] in (("worktree", "list"), ("rev-parse", "--absolute-git-dir"))

    def test_a_git_without_worktree_list_z_still_reads_and_releases_the_lock(self):
        with self.git_failing(lambda args: "-z" in args, "error: unknown switch `z'\n"):
            self.assertEqual(self.run_one(self.alpha)[0], 0)
            self.assertEqual(self.run_one(self.alpha)[0], 0)
        self.assertTrue(self.session_lock().startswith(f"headless t1 pid {os.getpid()} since "))
        self.assertIsNone(lock_of_worktree(run_headless.worktree_path(self.alpha, "t1")))
        self.assertFalse(any("lock" in note for note in self.outcome("alpha")["notes"]),
                         self.outcome("alpha")["notes"])

    def test_a_lock_that_cannot_be_read_at_the_end_is_left_with_gits_error(self):
        with self.git_failing(self.reads_a_lock, "fatal: cannot read it\n"):
            self.assertEqual(self.run_one(self.alpha)[0], 0)
        wt = run_headless.worktree_path(self.alpha, "t1")
        self.assertIn(f"left the lock on {wt}, which could not be read: "
                      "git rev-parse --absolute-git-dir: exit 129: fatal: cannot read it",
                      self.outcome("alpha")["notes"])
        self.assertEqual(lock_of_worktree(wt), self.session_lock(), "never taken for gone and unlocked")

    def test_a_lock_that_cannot_be_read_on_reuse_is_a_note_and_the_run_goes_on_without_one(self):
        self.assertEqual(self.run_one(self.alpha)[0], 0)
        wt = run_headless.worktree_path(self.alpha, "t1")
        left = f"headless t1 pid {dead_pid()} since 2026-11-19T07:00:00+00:00"
        git("worktree", "lock", "--reason", left, str(wt), cwd=self.alpha)
        with self.git_failing(self.reads_a_lock, "fatal: cannot read it\n"):
            self.assertEqual(self.run_one(self.alpha)[0], 0)
        self.assertIn(f"could not read the lock on {wt}, so the run goes on without one: "
                      "git rev-parse --absolute-git-dir: exit 129: fatal: cannot read it",
                      self.outcome("alpha")["notes"])
        self.assertEqual(self.session_lock(), left, "not taken over")
        self.assertEqual(lock_of_worktree(wt), left, "not unlocked at the end")

    def test_a_crafted_pid_in_a_reused_lock_is_someone_elses(self):
        self.assertEqual(self.run_one(self.alpha)[0], 0)
        wt = run_headless.worktree_path(self.alpha, "t1")
        crafted = "headless t1 pid ² since 2026-11-19T07:00:00+00:00"
        git("worktree", "lock", "--reason", crafted, str(wt), cwd=self.alpha)
        self.assertEqual(self.run_one(self.alpha)[0], 0)
        self.assertIn(f"left the lock someone else holds on {wt}: {crafted}", self.outcome("alpha")["notes"])
        self.assertEqual(lock_of_worktree(wt), crafted)

    def test_a_worktree_on_a_path_with_a_space_is_locked_and_released(self):
        spaced = make_repo(Path(self.tmp.name).resolve() / "My Projects" / "gamma")
        self.assertEqual(self.run_one(spaced)[0], 0)
        self.assertTrue(self.recorded("gamma.worktrees_headless-t1")["locked"].startswith("headless t1 pid "))
        self.assertIsNone(lock_of_worktree(run_headless.worktree_path(spaced, "t1")))
        self.assertFalse(any("lock" in note for note in self.outcome("gamma")["notes"]))

    def test_a_log_that_cannot_be_opened_is_could_not_start_and_its_lock_released(self):
        (self.logs / "alpha.stream.jsonl").mkdir(parents=True)
        code, out = self.run_one(self.alpha)
        outcome = json.loads(out)
        self.assertEqual((code, outcome["status"]), (1, "failed"))
        self.assertTrue(outcome["result"].startswith("could not start: "), outcome["result"])
        self.assertIn("alpha.stream.jsonl", outcome["result"])
        self.assertIsNone(lock_of_worktree(run_headless.worktree_path(self.alpha, "t1")))

    def test_a_checkout_gone_during_the_session_ends_with_could_not_finish(self):
        self.env["FAKE_CLAUDE_MOVES"] = str(self.alpha)
        code, out = self.run_one(self.alpha, mode="move", program=True)
        outcome = json.loads(out)
        self.assertEqual((code, outcome["status"]), (0, "ok"), "the session's own status")
        self.assertEqual(outcome, self.outcome("alpha"))
        wt = run_headless.worktree_path(self.alpha, "t1")
        self.assertTrue(outcome["cleanup"].startswith(f"could not finish {wt}: "), outcome["cleanup"])
        self.assertIn(str(self.alpha), outcome["cleanup"])

    def test_the_lock_is_released_when_the_session_times_out(self):
        code, out = self.run_one(self.alpha, "--timeout", "0.01", mode="slow")
        self.assertEqual((code, json.loads(out)["result"]), (1, "timed out after 0.01 min"))
        self.assertTrue(self.session_lock().startswith("headless t1 pid "))
        self.assertIsNone(lock_of_worktree(run_headless.worktree_path(self.alpha, "t1")))

    def test_a_session_that_cannot_start_is_failed_and_its_lock_released(self):
        # An argument past every system's limit, so no `claude` on the PATH can start.
        code, out = self.run_one(self.alpha, "--claude-arg", "x" * (8 * 2**20))
        outcome = json.loads(out)
        self.assertEqual((code, outcome["status"]), (1, "failed"))
        self.assertTrue(outcome["result"].startswith("could not start: "), outcome["result"])
        self.assertIsNone(lock_of_worktree(run_headless.worktree_path(self.alpha, "t1")))

    def test_ctrl_c_during_the_session_releases_the_lock_and_goes_on_up(self):
        real = subprocess.run

        def interrupted(cmd, *args, **kwargs):
            if cmd[0] == "claude":
                raise KeyboardInterrupt
            return real(cmd, *args, **kwargs)

        with mock.patch.object(run_headless.subprocess, "run", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.run_one(self.alpha)
        wt = run_headless.worktree_path(self.alpha, "t1")
        self.assertTrue(wt.is_dir())
        self.assertIsNone(lock_of_worktree(wt))

    def test_a_reused_worktree_is_locked_again(self):
        self.assertEqual(self.run_one(self.alpha)[0], 0)
        self.assertEqual(self.run_one(self.alpha)[0], 0)
        self.assertTrue(self.session_lock().startswith(f"headless t1 pid {os.getpid()} since "))
        self.assertIsNone(lock_of_worktree(run_headless.worktree_path(self.alpha, "t1")))
        self.assertFalse(any("lock" in note for note in self.outcome("alpha")["notes"]))

    def test_a_rerun_takes_over_the_lock_an_earlier_run_of_its_job_left(self):
        self.assertEqual(self.run_one(self.alpha)[0], 0)
        wt = run_headless.worktree_path(self.alpha, "t1")
        status_call = (str(self.alpha), ["status", "--format", "json", str(wt)])
        # Gone by the program's `status`, even with a pid that runs, as when a later process
        # reused it; and, without the program, by its pid alone.
        for pid, program in ((os.getpid(), True), (dead_pid(), False)):
            with self.subTest(program=program):
                self.env["FAKE_MANAGER_LOCK_ALIVE"] = "false"
                left = f"headless t1 pid {pid} since 2026-11-19T07:00:00+00:00"
                git("worktree", "lock", "--reason", left, str(wt), cwd=self.alpha)
                calls = len(self.manager_calls())
                self.assertEqual(self.run_one(self.alpha, program=program)[0], 0)
                self.assertTrue(self.session_lock().startswith(f"headless t1 pid {os.getpid()} since "))
                self.assertNotEqual(self.session_lock(), left)
                self.assertIn(f"took over the lock an earlier run of this job left: {left}",
                              self.outcome("alpha")["notes"])
                self.assertIsNone(lock_of_worktree(wt))
                self.assertEqual(status_call in self.manager_calls()[calls:], program)
        self.assertEqual(self.manager_locks(), [["finish", None]])

    def test_a_live_run_of_the_job_keeps_its_lock(self):
        self.assertEqual(self.run_one(self.alpha)[0], 0)
        wt = run_headless.worktree_path(self.alpha, "t1")
        # Alive by the program's `status`, whatever the pid; and, without it, by its pid.
        for pid, program in ((dead_pid(), True), (os.getpid(), False)):
            with self.subTest(program=program):
                self.env["FAKE_MANAGER_LOCK_ALIVE"] = "true"
                live = f"headless t1 pid {pid} since 2026-11-19T07:00:00+00:00"
                git("worktree", "lock", "--reason", live, str(wt), cwd=self.alpha)
                self.assertEqual(self.run_one(self.alpha, program=program)[0], 0)
                self.assertEqual(self.session_lock(), live)
                self.assertIn(f"left the lock a run of this job still holds on {wt}: {live}",
                              self.outcome("alpha")["notes"])
                self.assertEqual(lock_of_worktree(wt), live, "not unlocked at the end")
                git("worktree", "unlock", str(wt), cwd=self.alpha)

    def test_a_takeover_whose_new_lock_fails_says_the_old_one_was_released(self):
        self.assertEqual(self.run_one(self.alpha)[0], 0)
        wt = run_headless.worktree_path(self.alpha, "t1")
        left = f"headless t1 pid {dead_pid()} since 2026-11-19T07:00:00+00:00"
        git("worktree", "lock", "--reason", left, str(wt), cwd=self.alpha)
        real = run_headless.git

        def no_lock(*args: str, cwd: Path) -> subprocess.CompletedProcess:
            if args[:2] == ("worktree", "lock"):
                return subprocess.CompletedProcess(["git", *args], 128, "", "fatal: no lock for you\n")
            return real(*args, cwd=cwd)

        with mock.patch.object(run_headless, "git", side_effect=no_lock):
            self.assertEqual(self.run_one(self.alpha)[0], 0)
        self.assertIn(f"released the lock an earlier run of this job left, {left}, but "
                      f"git worktree lock {wt}: exit 128: fatal: no lock for you", self.outcome("alpha")["notes"])
        self.assertIsNone(self.session_lock())
        self.assertIsNone(lock_of_worktree(wt))

    def test_someone_elses_lock_on_a_reused_worktree_is_left_as_it_is(self):
        self.assertEqual(self.run_one(self.alpha)[0], 0)
        wt = run_headless.worktree_path(self.alpha, "t1")
        for theirs in ("someone else's", "headless t10 pid 1 since 2026-11-19T07:00:00+00:00"):
            with self.subTest(theirs=theirs):
                git("worktree", "lock", "--reason", theirs, str(wt), cwd=self.alpha)
                self.assertEqual(self.run_one(self.alpha, program=True)[0], 0)
                self.assertEqual(self.session_lock(), theirs)
                self.assertIn(f"left the lock someone else holds on {wt}: {theirs}", self.outcome("alpha")["notes"])
                self.assertEqual(lock_of_worktree(wt), theirs, "not unlocked at the end")
                self.assertEqual(self.manager_locks()[-1], ["finish", theirs])
                git("worktree", "unlock", str(wt), cwd=self.alpha)

    def test_no_clean_follows_a_finish_kept_as_locked(self):
        self.env.update(FAKE_MANAGER_EXIT_finish="3", FAKE_MANAGER_FINISH_REASONS="locked,not-landed")
        self.assertEqual(self.run_one(self.alpha, program=True)[0], 0)
        wt = run_headless.worktree_path(self.alpha, "t1")
        self.assertEqual(self.manager_calls()[-1], (str(self.alpha), ["finish", "--format", "json", str(wt)]))
        self.assertEqual(self.outcome("alpha")["cleanup"],
                         f"git-worktree-manager finish --format json {wt}: kept the worktree: "
                         "locked: locked: someone else's; not-landed: HEAD is not merged into refs/remotes/origin/main")

    def test_a_checkout_that_goes_during_the_sweep_ends_the_run_with_its_outcome(self):
        self.env["FAKE_MANAGER_SWEEP_MOVES"] = str(self.alpha)
        code, out = self.run_one(self.alpha, program=True)
        self.assertEqual(code, 1)
        outcome = self.outcome("alpha")
        self.assertEqual(json.loads(out), outcome)
        self.assertEqual(outcome["status"], "failed")
        self.assertTrue(outcome["result"].startswith("could not make the worktree: "), outcome["result"])
        self.assertIn(str(self.alpha), outcome["result"])
        self.assertIsNone(outcome["cleanup"])

    def test_no_call_passes_an_option_the_program_does_not_have(self):
        self.commit_envrc()
        for mode in ("ok", "fail", "commit"):
            with self.subTest(mode=mode):
                self.run_one(self.alpha, mode=mode, program=True)
        self.run_one(self.alpha, "--dry-run", program=True)
        args = [arg for _, call in self.manager_calls() for arg in call]
        self.assertIn("finish", args)
        self.assertIn("clean", args)
        self.assertIn("provision", args)
        self.assertEqual({"--apply", "--log", "--no-size", "--json"} & set(args), set())

    def test_keep_worktree_turns_off_the_sweep_and_the_finish(self):
        self.assertEqual(self.run_one(self.alpha, "--keep-worktree", program=True)[0], 0)
        self.assertEqual(self.manager_calls(), [(str(self.alpha), DISK_CALL)])
        self.assertEqual(self.outcome("alpha")["cleanup"], "kept the worktree: --keep-worktree")

    def test_without_the_program_the_worktree_stays_and_the_outcome_says_so(self):
        self.assertEqual(self.run_one(self.alpha)[0], 0)
        self.assertTrue(run_headless.worktree_path(self.alpha, "t1").is_dir())
        self.assertEqual(self.outcome("alpha")["cleanup"],
                         "kept the worktree, nothing cleaned: git-worktree-manager is not on the PATH")
        self.assertIn("nothing cleaned", self.stderr)

    def test_a_run_in_the_checkout_finishes_nothing(self):
        self.assertEqual(self.run_one(self.alpha, "--where", "checkout", program=True)[0], 0)
        self.assertEqual(self.manager_calls(), [(str(self.alpha), DISK_CALL)])
        self.assertIsNone(self.outcome("alpha")["cleanup"])

    # Provisioning a worktree's .envrc for direnv exec.

    def commit_envrc(self) -> None:
        (self.alpha / ".envrc").write_text("export X=1\n")
        git("add", ".envrc", cwd=self.alpha)
        git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "envrc",
            cwd=self.alpha)

    def test_a_worktree_with_an_envrc_is_provisioned_before_direnv_exec(self):
        self.commit_envrc()
        self.assertEqual(self.run_one(self.alpha, program=True)[0], 0)
        wt = run_headless.worktree_path(self.alpha, "t1")
        self.assertIn((str(self.alpha), ["provision", "--format", "json", str(wt)]), self.manager_calls())
        self.assertEqual((self.record / "direnv.txt").read_text().split()[:2], ["exec", str(wt)])
        self.assertIn(f"git-worktree-manager provision --format json {wt}: exit 0: direnv done: stub direnv step",
                      self.outcome("alpha")["notes"])

    def test_without_the_program_a_worktree_runs_without_direnv_exec(self):
        self.commit_envrc()
        self.assertEqual(self.run_one(self.alpha)[0], 0)
        self.assertFalse((self.record / "direnv.txt").exists())
        self.assertIn("started without direnv exec", " ".join(self.outcome("alpha")["notes"]))

    def test_a_provision_whose_direnv_step_is_not_done_runs_without_direnv_exec(self):
        self.commit_envrc()
        for step, code in (("skipped", "0"), ("failed", "1")):
            with self.subTest(step=step):
                self.env.update(FAKE_MANAGER_DIRENV=step, FAKE_MANAGER_EXIT_provision=code)
                self.assertEqual(self.run_one(self.alpha, program=True)[0], 0)
                self.assertFalse((self.record / "direnv.txt").exists())
                self.assertIn(f"exit {code}: direnv {step}: stub direnv step; started without direnv exec",
                              " ".join(self.outcome("alpha")["notes"]))

    def test_a_failed_step_besides_direnv_still_runs_under_direnv_exec(self):
        self.commit_envrc()
        self.env["FAKE_MANAGER_EXIT_provision"] = "1"
        self.assertEqual(self.run_one(self.alpha, program=True)[0], 0)
        self.assertTrue((self.record / "direnv.txt").exists())


@unittest.skipUnless(shutil.which(MANAGER), f"{MANAGER} is not on the PATH")
class AgainstTheBinary(unittest.TestCase):
    """Whole runs against the real git-worktree-manager on the PATH, with the fake `claude`.

    Each works in a temporary repository whose `origin` names its default branch, with a
    HOME and XDG folders of its own, so the program's backup, state and build root are
    inside the test's folder and never the real ~/backups, ~/.local/state or ~/.cache.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name).resolve()
        self.home = base / "home"
        self.home.mkdir()
        self.app = make_repo(base / "app")
        (self.app / ".gitignore").write_text("build/\n")
        git("add", ".gitignore", cwd=self.app)
        git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "ignore",
            cwd=self.app)
        git("init", "-q", "--bare", "-b", "main", str(base / "origin.git"), cwd=base)
        git("remote", "add", "origin", str(base / "origin.git"), cwd=self.app)
        git("push", "-q", "origin", "main", cwd=self.app)
        git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main", cwd=self.app)
        self.record, self.logs, bin_dir = base / "record", base / "logs", base / "bin"
        self.record.mkdir()
        bin_dir.mkdir()
        fake = bin_dir / "claude"
        fake.write_text(FAKE_CLAUDE.format(python=sys.executable))
        fake.chmod(0o755)
        self.projects = base / "projects"
        self.env = {
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "FAKE_CLAUDE_RECORD": str(self.record),
            "HOME": str(self.home),
            **{f"XDG_{kind}_HOME": str(self.home / kind.lower()) for kind in ("STATE", "CACHE", "CONFIG")},
        }
        self.wt = run_headless.worktree_path(self.app, "t1")

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, *extra: str, mode: str = "ok", env: dict[str, str] | None = None) -> tuple[int, dict]:
        """main() on the temporary repository, with the real program found on the PATH;
        returns its exit status and the JSON line it printed."""
        env = {**self.env, **(env or {}), "FAKE_CLAUDE_MODE": mode}
        out = io.StringIO()
        with mock.patch.dict(os.environ, env):
            for key in [k for k in os.environ if k.startswith(("GIT_", "WORKTREE_MANAGER_")) and k not in env]:
                del os.environ[key]
            os.environ.pop("ANTHROPIC_API_KEY", None)
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                code = run_headless.main(
                    ["--prompt", "do the thing", "--job", "t1", "--progress-every", "0",
                     "--projects-root", str(self.projects), "--log-dir", str(self.logs),
                     *extra, str(self.app)],
                    read=lambda: (1, None), platform="linux", free=lambda _: 500 * 10**9)
        return code, json.loads(out.getvalue())

    def has_branch(self) -> bool:
        return subprocess.run(["git", "rev-parse", "--verify", "--quiet", "refs/heads/headless/t1"],
                              cwd=self.app, capture_output=True).returncode == 0

    def test_a_run_that_changed_nothing_has_its_worktree_finished(self):
        code, outcome = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(outcome["cleanup"], f"git-worktree-manager finish --format json {self.wt}: exit 0")
        self.assertIn("git-worktree-manager sweep: exit 0", " ".join(outcome["notes"]))
        self.assertFalse(self.wt.exists())
        self.assertFalse(self.has_branch())
        self.assertTrue((self.home / "state" / "git-worktree-manager").is_dir(),
                        "the program's state is under the test's own XDG_STATE_HOME")

    def test_a_run_that_committed_has_its_worktree_kept_and_cleaned(self):
        code, outcome = self.run_main(mode="commit-build")
        self.assertEqual(code, 0)
        self.assertEqual(outcome["cleanup"], f"git-worktree-manager clean --format json {self.wt}: exit 0")
        self.assertTrue((self.wt / "work.txt").is_file())
        self.assertFalse((self.wt / "build" / "out.o").exists(), "its build output is deleted")
        self.assertTrue(self.has_branch())

    def test_a_run_that_left_changes_is_kept_with_the_programs_reasons(self):
        code, outcome = self.run_main(mode="dirty")
        self.assertEqual(code, 0)
        self.assertEqual(outcome["cleanup"],
                         f"git-worktree-manager finish --format json {self.wt}: kept the worktree: "
                         "uncommitted: 1 uncommitted paths: scratch.txt")
        self.assertTrue((self.wt / "scratch.txt").is_file())

    def test_a_run_that_changed_nothing_ahead_of_origin_is_kept_as_not_landed_and_cleaned(self):
        (self.app / "local.txt").write_text("not pushed\n")
        git("add", "local.txt", cwd=self.app)
        git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "local",
            cwd=self.app)
        code, outcome = self.run_main(mode="build")
        self.assertEqual(code, 0)
        self.assertEqual(outcome["cleanup"],
                         f"git-worktree-manager finish --format json {self.wt}: kept the worktree: "
                         "not-landed: HEAD is not merged into refs/remotes/origin/main (local-only); "
                         f"then git-worktree-manager clean --format json {self.wt}: exit 0")
        self.assertTrue((self.wt / "local.txt").is_file(), "the worktree stays")
        self.assertFalse((self.wt / "build" / "out.o").exists(), "its build output is deleted")
        self.assertTrue(self.has_branch())

    def test_a_sweep_while_the_session_runs_leaves_its_locked_worktree(self):
        git("config", "worktreeManager.idle", "0s", cwd=self.app)
        code, outcome = self.run_main(mode="sweep", env={"FAKE_CLAUDE_SWEEP_IN": str(self.app)})
        self.assertEqual(code, 0)
        session = json.loads((self.record / "app.worktrees_headless-t1.json").read_text())
        self.assertEqual((session["sweep_exit"], session["left"]), (0, True))
        lock = session["status_lock"]
        self.assertEqual((lock["who"], lock["pid"], lock["alive"]),
                         (f"headless t1 pid {os.getpid()}", os.getpid(), True))
        self.assertEqual(lock["reason"], f"{lock['who']} since {lock['since'].replace('Z', '+00:00')}")
        self.assertEqual(outcome["cleanup"], f"git-worktree-manager finish --format json {self.wt}: exit 0",
                         "once unlocked, nothing else kept it")
        self.assertFalse(self.wt.exists())

    def test_a_rerun_takes_over_a_lock_whose_runner_is_gone_by_status(self):
        self.assertEqual(self.run_main("--keep-worktree")[0], 0)
        left = f"headless t1 pid {dead_pid()} since 2026-11-19T07:00:00+00:00"
        git("worktree", "lock", "--reason", left, str(self.wt), cwd=self.app)
        code, outcome = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn(f"took over the lock an earlier run of this job left: {left}", outcome["notes"])
        self.assertEqual(outcome["cleanup"], f"git-worktree-manager finish --format json {self.wt}: exit 0")
        self.assertFalse(self.wt.exists())

    def test_a_rerun_takes_over_a_lock_whose_pid_a_later_process_has_by_status(self):
        # A live pid, this process's, in a lock taken long before it started: the program's
        # `status` says the lock's process is gone, though the pid alone would say it runs.
        self.assertEqual(self.run_main("--keep-worktree")[0], 0)
        reused = f"headless t1 pid {os.getpid()} since 2000-01-01T00:00:00+00:00"
        git("worktree", "lock", "--reason", reused, str(self.wt), cwd=self.app)
        self.assertTrue(run_headless.pid_alive(os.getpid()))
        with mock.patch.dict(os.environ, self.env):
            status = subprocess.run([MANAGER, "status", "--format", "json", str(self.wt)], cwd=self.app,
                                    capture_output=True, text=True)
        self.assertIs(run_headless.status_lock_alive(status.stdout, str(self.wt)), False)
        code, outcome = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn(f"took over the lock an earlier run of this job left: {reused}", outcome["notes"])
        self.assertEqual(outcome["cleanup"], f"git-worktree-manager finish --format json {self.wt}: exit 0")
        self.assertFalse(self.wt.exists())

    def test_disk_gives_the_floor_the_runner_reads(self):
        code, plan = self.run_main("--dry-run", env={"WORKTREE_MANAGER_FLOOR_BUILD_GB": "123"})
        self.assertEqual((code, plan["build_floor_gb"]), (0, 123.0))
        self.assertEqual(Path(plan["worktree_manager"]).name, MANAGER)
        self.assertNotIn("no build floor", " ".join(plan.get("notes") or []))
        self.assertEqual(self.run_main("--dry-run")[1]["build_floor_gb"], 70.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
