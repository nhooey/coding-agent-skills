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
    if mode == "commit":
        import subprocess
        open("work.txt", "w").write("work\\n")
        subprocess.run(["git", "add", "work.txt"], check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
                        "commit", "-q", "-m", "work"], check=True)
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

# Stand-ins for the `worktrees` program and direnv: each notes its working
# directory and arguments, one call per line. The stub `worktrees` exits with
# FAKE_WORKTREES_EXIT; the stub direnv runs the command after `exec <dir>`.
FAKE_WORKTREES = '#!/bin/sh\necho "$PWD|$*" >> "$FAKE_CLAUDE_RECORD/worktrees.txt"\necho "stub $1 done"\nexit "${FAKE_WORKTREES_EXIT:-0}"\n'
FAKE_DIRENV = '#!/bin/sh\necho "$*" >> "$FAKE_CLAUDE_RECORD/direnv.txt"\nshift 2\nexec "$@"\n'


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
    def test_the_floor_is_70_gb_without_a_file_or_a_variable(self):
        self.assertEqual(run_headless.build_floor("", {}), (70.0, None))

    def test_the_floor_comes_from_the_files_key_value_lines(self):
        text = "# written by Home Manager\nWORKTREES_FLOOR_BUILD_GB=50\nWORKTREES_FLOOR_CLEANUP_ONLY_GB=20\n"
        self.assertEqual(run_headless.build_floor(text, {}), (50.0, None))

    def test_the_variable_overrides_the_file(self):
        floor = run_headless.build_floor("WORKTREES_FLOOR_BUILD_GB=50\n", {"WORKTREES_FLOOR_BUILD_GB": "90"})
        self.assertEqual(floor, (90.0, None))

    def test_a_floor_that_is_not_a_number_falls_back_to_70_with_a_note(self):
        gb, note = run_headless.build_floor("WORKTREES_FLOOR_BUILD_GB=lots\n", {})
        self.assertEqual(gb, 70.0)
        self.assertIn("'lots'", note)

    def test_shortfalls_name_each_volume_under_the_floor(self):
        free = (("/w", 80 * 10**9), ("/nix", 60 * 10**9), ("/gone", None))
        self.assertEqual(run_headless.disk_shortfalls(free, 70),
                         ("60 GB free on /nix, below the 70 GB build floor",))

    def test_free_bytes_of_a_missing_path_is_none(self):
        self.assertIsNone(run_headless.free_bytes(Path("/no/such/volume/here")))


class Finishing(unittest.TestCase):
    def test_commits_win_then_status_decides(self):
        ending = run_headless.ending
        self.assertEqual([ending("ok", 0), ending("failed", 0), ending("limit", 0)],
                         ["nothing", "failed", "failed"])
        self.assertEqual([ending("ok", 2), ending("failed", 1)], ["committed", "committed"])

    def test_each_ending_is_one_worktrees_call(self):
        args = run_headless.finish_args
        self.assertEqual(args("nothing", "/wt", "/l"), ("finish", "/wt"))
        self.assertEqual(args("failed", "/wt", "/l"), ("finish", "/wt", "--log", "/l"))
        self.assertEqual(args("failed", "/wt", None), ("finish", "/wt"))
        self.assertEqual(args("committed", "/wt", "/l"), ("clean", "/wt", "--apply"))

    def test_program_note_keeps_the_last_line(self):
        self.assertEqual(run_headless.program_note(("finish", "/wt"), 0, "a\nkept: unmerged\n"),
                         "worktrees finish /wt: exit 0: kept: unmerged")
        self.assertEqual(run_headless.program_note(("sweep", "--apply"), 1, ""),
                         "worktrees sweep --apply: exit 1")


class Summary(unittest.TestCase):
    """`--summary --job <job>` over a job's folder of outcome files."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        patcher = mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(self.state)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        self.folder = self.state / "coding-agent-headless" / "night"

    def write_outcomes(self, outcomes: dict[str, str]) -> None:
        self.folder.mkdir(parents=True)
        for label, text in outcomes.items():
            (self.folder / f"{label}.outcome.json").write_text(text)
        (self.folder / "alpha.status.json").write_text(json.dumps({"state": "running"}))
        (self.folder / "alpha.stream.jsonl").write_text('{"status": "ok"}\n')

    def summary(self, *extra: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run_headless.main(["--summary", "--job", "night", *extra])
        return code, out.getvalue()

    def test_counts_each_state_from_the_outcome_files_only(self):
        self.write_outcomes({
            "alpha": json.dumps({"status": "ok"}), "beta": json.dumps({"status": "ok"}),
            "gamma": json.dumps({"status": "failed"}), "delta": json.dumps({"status": "limit"}),
            "eps": "not json",
        })
        code, out = self.summary("--json")
        self.assertEqual(code, 0)
        record = json.loads(out)
        self.assertEqual(record["runs"], 5)
        self.assertEqual(record["folder"], str(self.folder))
        self.assertEqual(record["counts"],
                         {"ok": 2, "failed": 1, "skipped": 0, "limit": 1, "unreadable": 1})

    def test_prints_a_table_by_default(self):
        self.write_outcomes({"alpha": json.dumps({"status": "skipped"})})
        code, out = self.summary()
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertIn("1 runs", lines[0])
        self.assertEqual(lines[1].split(), ["state", "runs"])
        self.assertEqual([line.split() for line in lines[2:]],
                         [["ok", "0"], ["failed", "0"], ["skipped", "1"], ["limit", "0"]])

    def test_a_job_with_no_outcome_files_prints_zero_counts(self):
        code, out = self.summary("--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["counts"], {"ok": 0, "failed": 0, "skipped": 0, "limit": 0})
        self.folder.mkdir(parents=True)
        code, out = self.summary()
        self.assertEqual(code, 0)
        self.assertIn("0 runs", out)

    def test_log_dir_names_another_folder(self):
        other = self.state / "elsewhere"
        other.mkdir()
        (other / "a.outcome.json").write_text(json.dumps({"status": "failed"}))
        record = json.loads(self.summary("--json", "--log-dir", str(other))[1])
        self.assertEqual(record["counts"]["failed"], 1)

    def test_state_counts_keeps_unknown_states_after_the_known_ones(self):
        self.assertEqual(list(run_headless.state_counts(("zeta", "ok", "beta"))),
                         ["ok", "failed", "skipped", "limit", "beta", "zeta"])


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
        # `worktrees` sits in a folder of its own, off the PATH, so a run finds it
        # only through run_one's `program=True`, never a real one on this machine.
        self.worktrees = base / "tools" / "worktrees"
        self.worktrees.parent.mkdir()
        self.worktrees.write_text(FAKE_WORKTREES)
        self.worktrees.chmod(0o755)
        direnv = bin_dir / "direnv"
        direnv.write_text(FAKE_DIRENV)
        direnv.chmod(0o755)
        self.floor_file = base / "config" / "worktrees" / "floor"
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
                "--projects-root", str(self.projects), "--log-dir", str(self.logs),
                "--floor-file", str(self.floor_file)]

    def run_one(self, checkout: Path, *extra: str, mode: str = "ok",
                levels: tuple[int, ...] = (1,), platform: str = "linux",
                free_gb: float = 500, program: bool = False) -> tuple[int, str]:
        """main() in this process, for one checkout; returns its exit status and stdout.

        The memory pressure reader gives `levels` in turn, then repeats the last; `self.reads`
        counts its calls. `platform` stands in for sys.platform, `free_gb` for the free space
        on every volume, and `program` puts the stub `worktrees` in reach.
        """
        self.reads = 0

        def read() -> tuple[int, None]:
            self.reads += 1
            return levels[min(self.reads, len(levels)) - 1], None

        def find(name: str) -> str | None:
            return str(self.worktrees) if program and name == "worktrees" else None

        env = {**self.env, "FAKE_CLAUDE_MODE": mode}
        old = {k: os.environ.get(k) for k in [*env, "ANTHROPIC_API_KEY", "WORKTREES_FLOOR_BUILD_GB"]}
        os.environ.update(env)
        os.environ.pop("ANTHROPIC_API_KEY", None)
        if "WORKTREES_FLOOR_BUILD_GB" not in env:
            os.environ.pop("WORKTREES_FLOOR_BUILD_GB", None)
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
        # A floor of 0 GB, so this machine's own free space never holds the run.
        env = {**os.environ, **self.env, "FAKE_CLAUDE_MODE": "limit", "WORKTREES_FLOOR_BUILD_GB": "0"}
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
        self.assertFalse(any(self.record.iterdir()), "neither claude nor worktrees may have run")
        self.assertFalse(run_headless.worktree_path(self.beta, "t1").exists())

    def test_the_floor_is_read_from_the_floor_file(self):
        self.floor_file.parent.mkdir(parents=True)
        self.floor_file.write_text("WORKTREES_FLOOR_BUILD_GB=50\nWORKTREES_FLOOR_CLEANUP_ONLY_GB=25\n")
        self.assertEqual(self.run_one(self.beta, free_gb=60)[0], 0)
        self.floor_file.write_text("WORKTREES_FLOOR_BUILD_GB=100\n")
        code, out = self.run_one(self.beta, "--admission-timeout", "0", "--admission-poll", "0",
                                 free_gb=60)
        self.assertEqual(code, 3)
        self.assertIn("below the 100 GB build floor", json.loads(out)["result"])

    def test_the_variable_overrides_the_floor_file(self):
        self.floor_file.parent.mkdir(parents=True)
        self.floor_file.write_text("WORKTREES_FLOOR_BUILD_GB=100\n")
        self.env["WORKTREES_FLOOR_BUILD_GB"] = "10"
        self.assertEqual(self.run_one(self.beta, free_gb=60)[0], 0)

    def test_dry_run_shows_the_floor_and_the_shortfall(self):
        plan = json.loads(self.run_one(self.beta, "--dry-run", free_gb=60, program=True)[1])
        self.assertEqual(plan["build_floor_gb"], 70.0)
        self.assertEqual(len(plan["disk_short"]), 2, "the checkout's volume and /nix")
        self.assertEqual(plan["worktrees"], str(self.worktrees))

    def test_no_admission_starts_below_the_floor(self):
        self.assertEqual(self.run_one(self.beta, "--no-admission", "--admission-timeout", "0",
                                      free_gb=1)[0], 0)

    # Finishing the worktree.

    def worktrees_calls(self) -> list[tuple[str, str]]:
        """The stub `worktrees` calls, each as (working directory, arguments)."""
        path = self.record / "worktrees.txt"
        lines = path.read_text().splitlines() if path.exists() else []
        return [tuple(line.split("|", 1)) for line in lines]

    def test_a_run_that_changed_nothing_is_finished(self):
        self.assertEqual(self.run_one(self.alpha, program=True)[0], 0)
        wt = run_headless.worktree_path(self.alpha, "t1")
        self.assertEqual(self.worktrees_calls(),
                         [(str(self.alpha), "sweep --apply"), (str(self.alpha), f"finish {wt}")])
        self.assertEqual(self.outcome("alpha")["cleanup"], f"worktrees finish {wt}: exit 0: stub finish done")
        self.assertIn("[worktrees finish", self.stderr)

    def test_a_failed_run_is_finished_with_its_log(self):
        self.assertEqual(self.run_one(self.alpha, mode="fail", program=True)[0], 1)
        wt = run_headless.worktree_path(self.alpha, "t1")
        self.assertEqual(self.worktrees_calls()[-1],
                         (str(self.alpha), f"finish {wt} --log {self.logs / 'alpha.stream.jsonl'}"))

    def test_a_run_that_committed_is_cleaned_and_kept(self):
        self.assertEqual(self.run_one(self.alpha, mode="commit", program=True)[0], 0)
        wt = run_headless.worktree_path(self.alpha, "t1")
        self.assertEqual(self.worktrees_calls()[-1], (str(self.alpha), f"clean {wt} --apply"))
        self.assertTrue((wt / "work.txt").is_file())

    def test_the_programs_refusal_is_reported_not_fatal(self):
        self.env["FAKE_WORKTREES_EXIT"] = "1"
        self.assertEqual(self.run_one(self.alpha, program=True)[0], 0)
        self.assertIn("exit 1", self.outcome("alpha")["cleanup"])
        self.assertIn("worktrees sweep --apply: exit 1", " ".join(self.outcome("alpha")["notes"]))

    def test_keep_worktree_turns_off_the_sweep_and_the_finish(self):
        self.assertEqual(self.run_one(self.alpha, "--keep-worktree", program=True)[0], 0)
        self.assertEqual(self.worktrees_calls(), [])
        self.assertEqual(self.outcome("alpha")["cleanup"], "kept the worktree: --keep-worktree")

    def test_without_the_program_the_worktree_stays_and_the_outcome_says_so(self):
        self.assertEqual(self.run_one(self.alpha)[0], 0)
        self.assertTrue(run_headless.worktree_path(self.alpha, "t1").is_dir())
        self.assertEqual(self.outcome("alpha")["cleanup"],
                         "kept the worktree, nothing cleaned: worktrees is not on the PATH")
        self.assertIn("nothing cleaned", self.stderr)

    def test_a_run_in_the_checkout_finishes_nothing(self):
        self.assertEqual(self.run_one(self.alpha, "--where", "checkout", program=True)[0], 0)
        self.assertEqual(self.worktrees_calls(), [])
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
        self.assertIn((str(self.alpha), f"provision {wt}"), self.worktrees_calls())
        self.assertEqual((self.record / "direnv.txt").read_text().split()[:2], ["exec", str(wt)])

    def test_without_the_program_a_worktree_runs_without_direnv_exec(self):
        self.commit_envrc()
        self.assertEqual(self.run_one(self.alpha)[0], 0)
        self.assertFalse((self.record / "direnv.txt").exists())
        self.assertIn("started without direnv exec", " ".join(self.outcome("alpha")["notes"]))

    def test_a_failed_provision_runs_without_direnv_exec(self):
        self.commit_envrc()
        self.env["FAKE_WORKTREES_EXIT"] = "1"
        self.assertEqual(self.run_one(self.alpha, program=True)[0], 0)
        self.assertFalse((self.record / "direnv.txt").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
