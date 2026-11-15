#!/usr/bin/env python3
"""Run one headless Claude Code session with a prompt, inside one git checkout.

The session starts with the checkout (or a git worktree of it) as its working
directory, so it loads that checkout's CLAUDE.md, skills, settings, hooks and
plugins, the Nix dev shell a plugin or `.envrc` provides among them, as a
session started there by hand would.

This script handles one checkout. To run a prompt across many, the caller runs
it once per checkout, as many at a time as it likes, for example:
  xargs -P 4 -I{} run_headless.py --job tidy --prompt-file prompt.md {} < checkouts.txt

Where the session works (--where):
  worktree  (default) a git worktree of the checkout's HEAD, on the branch
            headless/<job>, at <checkout>.worktrees/headless-<job> beside it, so
            the run doesn't touch a working tree someone is using.
  checkout  the checkout itself.

Which session it starts from (--session):
  new       (default) a new session, so the prompt carries all the context.
  continue  the checkout's newest session, forked so the original is left as
            it was: `--continue --fork-session` in the checkout, or
            `--resume <its .jsonl> --fork-session` in a worktree, since a new
            worktree is a new directory with no sessions of its own. A checkout
            with no session gets a new one. When that session was written in
            the last --live-within minutes (default 10) it may still be
            running: the run warns, since its fork won't see what the live
            session does next.

A worktree holds only committed work, so a session continued in one may
remember edits that stayed behind, uncommitted, in the checkout. For a checkout
with uncommitted changes, --dirty decides what a continuing worktree run does:
  tell  (default) continue, and open the prompt with a note naming the
        uncommitted paths and saying their changes are not in the worktree.
  new   start a new session instead of continuing.
  skip  don't run; commit or stash the checkout's work and rerun.

Admission control: each session starts under `taskpolicy -c utility` on macOS,
so the scheduler favours interactive work and everything the session starts
inherits the class. Before it starts, the script reads the memory pressure
level, `kern.memorystatus_vm_pressure_level`: 1 (normal) starts the run, 2
(warning) or 4 (critical) holds it, checking again every few seconds and saying
so on a progress line. A run already going is never stopped. A level that can't
be read counts as 1, with a note.
  --no-admission         start at once, whatever the pressure
  --admission-timeout M  give up after M minutes of waiting, with status skipped

Output: progress lines go to stderr, each opening on the label: one when the
session starts, one every --progress-every seconds (default 60) with its time,
its tool calls so far and the tool it called last, and one when it ends. The
outcome goes to stdout as one JSON line and to <log-dir>/<label>.outcome.json:
status (ok, failed, limit or skipped), exit code, session_id, resumed_from,
turns, the start of the final result, the log path and notes. The session's
stream-json output and stderr are beside it.

Exit status:
  0    the session ended without an error
  1    it failed, or timed out
  2    bad arguments: not a git checkout, an empty prompt, ANTHROPIC_API_KEY set
  3    skipped, by --dirty skip or by --admission-timeout
  255  it hit a usage limit. xargs, GNU or BSD, starts no more runs after a
       command exits 255, so a fan-out through xargs stops there by itself.

Examples:
  run_headless.py --dry-run --prompt 'Fix the failing tests' ~/git/app
  run_headless.py --job tidy --prompt-file prompt.md --timeout 30 ~/git/app
"""

from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

PROJECTS_ROOT = Path.home() / ".claude" / "projects"
USAGE_LIMIT = re.compile(
    r"usage limit|limit reached|weekly limit|rate.?limit|\b429\b|resets? at",
    re.IGNORECASE,
)
RESULT_EXCERPT = 400
TOOL_USE = re.compile(r'"type":"tool_use","id":"[^"]*","name":"([^"]+)"')
PRESSURE_SYSCTL = b"kern.memorystatus_vm_pressure_level"
PRESSURE_NORMAL = 1
PRESSURE_LEVELS = frozenset({1, 2, 4})
ADMISSION_POLL_SECONDS = 5.0
START, WAIT, GIVE_UP = "start", "wait", "give_up"
EXIT = {"ok": 0, "failed": 1, "skipped": 3, "limit": 255}


def project_key(path: Path) -> str:
    """The folder name Claude Code keeps a directory's sessions under."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def newest_session(checkout: Path, projects_root: Path = PROJECTS_ROOT) -> Path | None:
    """The checkout's most recently written session transcript, if it has one."""
    folder = projects_root / project_key(checkout)
    sessions = [p for p in folder.glob("*.jsonl") if p.is_file()]
    return max(sessions, key=lambda p: p.stat().st_mtime, default=None)


def worktree_path(checkout: Path, job: str) -> Path:
    return checkout.parent / f"{checkout.name}.worktrees" / f"headless-{job}"


def branch_name(job: str) -> str:
    return f"headless/{job}"


def env_wrapper(workdir: Path) -> list[str]:
    """`direnv exec` for a checkout that loads its environment through direnv.

    Without an `.envrc`, the checkout's environment reaches Claude Code the way
    it does in a manual session, through its plugins, so nothing wraps the run.
    """
    if (workdir / ".envrc").is_file() and shutil.which("direnv"):
        return ["direnv", "exec", str(workdir)]
    return []


def claude_command(
    prompt: str,
    name: str,
    *,
    where: str,
    resume: Path | None,
    model: str | None = None,
    effort: str | None = None,
    permission_mode: str = "auto",
    max_turns: int | None = None,
    extra: list[str] | None = None,
) -> list[str]:
    cmd = ["claude", "-p", prompt, "-n", name]
    if resume is not None:
        if where == "checkout":
            cmd += ["--continue", "--fork-session"]
        else:
            cmd += ["--resume", str(resume), "--fork-session"]
    if model:
        cmd += ["--model", model]
    if effort:
        cmd += ["--effort", effort]
    cmd += [
        "--permission-mode",
        permission_mode,
        "--permission-prompts",
        "none",
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    if max_turns is not None:
        cmd += ["--max-turns", str(max_turns)]
    return cmd + list(extra or [])


def parse_result(stream: str) -> dict | None:
    """The final `result` event of a stream-json run, if it got that far."""
    result = None
    for line in stream.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            result = event
    return result


def is_usage_limit(*texts: str) -> bool:
    return any(USAGE_LIMIT.search(t or "") for t in texts)


def git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )


def uncommitted(checkout: Path) -> list[str]:
    """Paths with uncommitted changes, untracked files included, ignored ones not."""
    out = git("status", "--porcelain", "--untracked-files=all", cwd=checkout)
    return [line[3:] for line in out.stdout.splitlines() if len(line) > 3]


def dirty_note(checkout: Path, workdir: Path, paths: list[str], limit: int = 50) -> str:
    """The note that opens the prompt of a continued run whose checkout is dirty."""
    shown = "\n".join(f"- {p}" for p in paths[:limit])
    more = f"\n- …and {len(paths) - limit} more" if len(paths) > limit else ""
    return (
        f"Note from the headless runner: you are working in {workdir}, a git worktree made "
        f"from the last commit of {checkout}. These paths had uncommitted changes there, "
        f"and those changes are not in this worktree:\n{shown}{more}\n"
        "Edits the earlier conversation made to them may be missing here, so read the "
        "files as they are before relying on what you remember.\n\n"
    )


def toplevel(path: Path) -> Path | None:
    out = git("rev-parse", "--show-toplevel", cwd=path)
    return Path(out.stdout.strip()) if out.returncode == 0 else None


def ensure_worktree(checkout: Path, job: str) -> tuple[Path, str]:
    """Create (or reuse, on a rerun of the same job) the run's worktree."""
    path, branch = worktree_path(checkout, job), branch_name(job)
    if (path / ".git").exists():
        return path, f"reused {path}"
    path.parent.mkdir(parents=True, exist_ok=True)
    has_branch = git("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", cwd=checkout)
    if has_branch.returncode == 0:
        out = git("worktree", "add", str(path), branch, cwd=checkout)
    else:
        out = git("worktree", "add", "-b", branch, str(path), "HEAD", cwd=checkout)
    if out.returncode != 0:
        raise RuntimeError(f"git worktree add failed: {out.stderr.strip()}")
    return path, f"created {path} on {branch}"


def allow_direnv(checkout: Path, worktree: Path) -> str | None:
    """Allow the worktree's `.envrc` when it is the checkout's, byte for byte.

    direnv trusts an `.envrc` by its path, so a new worktree's copy starts out
    blocked even though the user allowed the same file in the checkout.
    """
    main, copy = checkout / ".envrc", worktree / ".envrc"
    if not (main.is_file() and copy.is_file() and shutil.which("direnv")):
        return None
    if main.read_bytes() != copy.read_bytes():
        return "worktree .envrc differs from the checkout's; left blocked"
    subprocess.run(["direnv", "allow", str(worktree)], capture_output=True, check=False)
    return "allowed the worktree's .envrc, identical to the checkout's"


@dataclass
class Plan:
    label: str
    checkout: str
    workdir: str
    resume: str | None
    command: list[str]
    notes: list[str] = field(default_factory=list)
    skip: str | None = None
    prefix: list[str] = field(default_factory=list)


@dataclass
class Outcome:
    label: str
    checkout: str
    workdir: str
    status: str  # ok | failed | limit | skipped
    code: int | None = None
    session_id: str | None = None
    resumed_from: str | None = None
    turns: int | None = None
    result: str = ""
    log: str | None = None
    notes: list[str] = field(default_factory=list)


def elapsed(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m{secs:02d}s" if minutes else f"{secs}s"


# Admission control. The decision is pure; reading the level is the only effect.


def taskpolicy_prefix(platform: str) -> list[str]:
    """The command that starts a run in the utility scheduling class, on macOS only."""
    return ["taskpolicy", "-c", "utility"] if platform == "darwin" else []


def admission_decision(level: int, waited: float, timeout: float | None) -> str:
    """Start, wait or give up, from the pressure level and the seconds waited so far."""
    if level == PRESSURE_NORMAL:
        return START
    return GIVE_UP if timeout is not None and waited >= timeout else WAIT


def pressure_from_sysctl(status: int, value: int) -> tuple[int, str | None]:
    """The level a `sysctlbyname` call gave, or level 1 and a note when it gave none."""
    if status != 0:
        return PRESSURE_NORMAL, "memory pressure level unreadable (sysctl failed); counted as 1"
    if value not in PRESSURE_LEVELS:
        return PRESSURE_NORMAL, f"memory pressure level {value} is not 1, 2 or 4; counted as 1"
    return value, None


def load_libc() -> ctypes.CDLL:
    return ctypes.CDLL(None)


def read_pressure_level(
    platform: str = sys.platform, load: Callable[[], object] = load_libc
) -> tuple[int, str | None]:
    """The effect: the macOS memory pressure level and a note, or (1, a note) on any failure.

    Off macOS there is no such sysctl, so there is nothing to wait for: level 1, no note.
    """
    if platform != "darwin":
        return PRESSURE_NORMAL, None
    try:
        libc = load()
        value, size = ctypes.c_int(0), ctypes.c_size_t(ctypes.sizeof(ctypes.c_int))
        status = libc.sysctlbyname(
            PRESSURE_SYSCTL, ctypes.byref(value), ctypes.byref(size), None, ctypes.c_size_t(0)
        )
    except (OSError, AttributeError, ValueError, TypeError) as err:
        return PRESSURE_NORMAL, f"memory pressure level unreadable ({err}); counted as 1"
    return pressure_from_sysctl(status, value.value)


@dataclass(frozen=True)
class Admission:
    action: str  # start | give_up
    level: int
    waited: float
    notes: tuple[str, ...]


def await_admission(
    label: str,
    timeout: float | None,
    *,
    read: Callable[[], tuple[int, str | None]],
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    poll: float = ADMISSION_POLL_SECONDS,
) -> Admission:
    """The shell around admission_decision: read, say so while waiting, sleep, read again."""
    begin = clock()
    level, note = read()
    first_level = level
    notes = (note,) if note else ()
    while True:
        waited = clock() - begin
        action = admission_decision(level, waited, timeout)
        if action != WAIT:
            break
        say(f"waiting {label} {elapsed(waited)}: memory pressure level {level}")
        sleep(poll)
        level, _ = read()
    held = (f"waited {elapsed(waited)} at memory pressure before starting",) if first_level != PRESSURE_NORMAL else ()
    return Admission(action, level, waited, notes + held)


def tool_calls(log: Path) -> tuple[int, str | None]:
    """How many tools a run's stream-json log shows it calling, and the last one."""
    try:
        names = TOOL_USE.findall(log.read_text(errors="replace"))
    except OSError:
        return 0, None
    return len(names), names[-1] if names else None


def say(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


def heartbeat(label: str, log: Path, start: float, every: float, done: threading.Event) -> None:
    """Every `every` seconds until `done`, a line on how the session is going."""
    while not done.wait(every):
        calls, last = tool_calls(log)
        say(f"...     {label} {elapsed(time.monotonic() - start)}, {calls} tools"
            + (f", last {last}" if last else ""))


def live_note(session: Path | None, within_minutes: float) -> str | None:
    """A warning when the session to fork was written recently enough to still be running."""
    if session is None or within_minutes <= 0:
        return None
    age = time.time() - session.stat().st_mtime
    if age > within_minutes * 60:
        return None
    return (f"session {session.stem} was written {elapsed(age)} ago and may still be running; "
            "this run forks it and won't see what it does next")


def plan_for(checkout: Path, label: str, prompt: str, args: argparse.Namespace) -> Plan:
    resume = newest_session(checkout, args.projects_root) if args.session == "continue" else None
    workdir = worktree_path(checkout, args.job) if args.where == "worktree" else checkout
    notes, skip = [], None
    live = live_note(resume, args.live_within)
    if live:
        notes.append(live)
    dirty = uncommitted(checkout) if args.where == "worktree" and resume else []
    if dirty:
        if args.dirty == "tell":
            prompt = dirty_note(checkout, workdir, dirty) + prompt
            notes.append(f"{len(dirty)} uncommitted paths in the checkout; named them in the prompt")
        elif args.dirty == "new":
            resume = None
            notes.append(f"{len(dirty)} uncommitted paths in the checkout; starting a new session")
        else:
            skip = f"{len(dirty)} uncommitted paths in the checkout; commit or stash them and rerun"
    command = claude_command(
        prompt,
        f"headless {args.job}",
        where=args.where,
        resume=resume,
        model=args.model,
        effort=args.effort,
        permission_mode=args.permission_mode,
        max_turns=args.max_turns,
        extra=args.claude_arg,
    )
    if args.session == "continue" and resume is None and not dirty:
        notes.append("no earlier session; starting a new one")
    return Plan(label, str(checkout), str(workdir), str(resume) if resume else None,
                command, notes, skip, taskpolicy_prefix(sys.platform))


def run(plan: Plan, args: argparse.Namespace) -> Outcome:
    checkout = Path(plan.checkout)
    outcome = Outcome(plan.label, plan.checkout, plan.workdir, "skipped",
                      resumed_from=plan.resume, notes=list(plan.notes))
    if plan.skip:
        outcome.result = f"not started: {plan.skip}"
        return outcome
    if not args.no_admission:
        timeout = args.admission_timeout * 60 if args.admission_timeout is not None else None
        admission = await_admission(plan.label, timeout, read=read_pressure_level,
                                    poll=args.admission_poll)
        outcome.notes.extend(admission.notes)
        if admission.action == GIVE_UP:
            outcome.result = (f"not started: memory pressure level {admission.level} for "
                              f"{elapsed(admission.waited)}, past --admission-timeout")
            return outcome
    try:
        if args.where == "worktree":
            workdir, note = ensure_worktree(checkout, args.job)
            outcome.notes.append(note)
            direnv_note = allow_direnv(checkout, workdir)
            if direnv_note:
                outcome.notes.append(direnv_note)
        else:
            workdir = checkout
    except RuntimeError as err:
        outcome.status, outcome.result = "failed", str(err)
        return outcome

    log = args.log_dir / f"{plan.label}.stream.jsonl"
    err_log = args.log_dir / f"{plan.label}.stderr"
    outcome.log = str(log)
    command = plan.prefix + env_wrapper(workdir) + plan.command
    say(f"start   {plan.label}")
    start, done = time.monotonic(), threading.Event()
    if args.progress_every > 0:
        threading.Thread(target=heartbeat, daemon=True,
                         args=(plan.label, log, start, args.progress_every, done)).start()
    try:
        with log.open("w") as out, err_log.open("w") as err:
            proc = subprocess.run(
                command, cwd=workdir, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                timeout=args.timeout * 60 if args.timeout else None, check=False,
            )
        outcome.code = proc.returncode
    except subprocess.TimeoutExpired:
        outcome.status, outcome.result = "failed", f"timed out after {args.timeout} min"
        return outcome
    except FileNotFoundError as err:
        outcome.status, outcome.result = "failed", f"could not start: {err}"
        return outcome
    finally:
        done.set()
        took = time.monotonic() - start

    stream, stderr = log.read_text(errors="replace"), err_log.read_text(errors="replace")
    result = parse_result(stream) or {}
    text = str(result.get("result") or stderr.strip() or "no result event")
    outcome.session_id = result.get("session_id")
    outcome.turns = result.get("num_turns")
    outcome.result = text[:RESULT_EXCERPT]
    if outcome.code == 0 and result and not result.get("is_error"):
        outcome.status = "ok"
    elif is_usage_limit(text, stderr):
        outcome.status = "limit"
    else:
        outcome.status = "failed"
    outcome.notes.append(f"took {elapsed(took)}")
    return outcome


def default_log_root() -> Path:
    state = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(state) / "coding-agent-headless"


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        epilog=__doc__.split("\n\n", 1)[1],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("checkout", type=Path, help="the git checkout to run in")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--prompt", help="the prompt")
    src.add_argument("--prompt-file", type=Path, help="read the prompt from a file ('-' for stdin)")
    p.add_argument("--job", default=dt.datetime.now().strftime("%Y%m%d-%H%M%S"),
                   help="names the branch, worktree, session and log folder (default: a timestamp); "
                        "give every run of a fan-out the same one")
    p.add_argument("--label", help="names the log files and progress lines (default: the checkout's "
                                   "folder name); set it when two checkouts share a name")
    p.add_argument("--where", choices=["worktree", "checkout"], default="worktree")
    p.add_argument("--session", choices=["new", "continue"], default="new")
    p.add_argument("--live-within", type=float, default=10,
                   help="minutes: warn when continuing a session written this recently; 0 to never warn "
                        "(default: 10)")
    p.add_argument("--dirty", choices=["tell", "new", "skip"], default="tell",
                   help="a continuing worktree run in a checkout with uncommitted changes (default: tell)")
    p.add_argument("--model", help="passed to claude --model (default: your configured model)")
    p.add_argument("--effort", help="passed to claude --effort")
    p.add_argument("--permission-mode", default="auto", help="passed to claude (default: auto)")
    p.add_argument("--max-turns", type=int, help="passed to claude --max-turns")
    p.add_argument("--timeout", type=float, help="minutes before the session is killed")
    p.add_argument("--claude-arg", action="append", default=[],
                   help="one more argument for claude; repeat as needed")
    p.add_argument("--progress-every", type=float, default=60,
                   help="seconds between progress lines; 0 for none (default: 60)")
    p.add_argument("--log-dir", type=Path, help="default: $XDG_STATE_HOME/coding-agent-headless/<job>")
    p.add_argument("--no-admission", action="store_true",
                   help="start at once, whatever the memory pressure (the utility priority still applies)")
    p.add_argument("--admission-timeout", type=float, metavar="MINUTES",
                   help="give up after waiting this long for memory pressure to ease, "
                        "with status skipped (default: wait as long as it takes)")
    p.add_argument("--admission-poll", type=float, default=ADMISSION_POLL_SECONDS,
                   help=argparse.SUPPRESS)
    p.add_argument("--projects-root", type=Path, default=PROJECTS_ROOT, help=argparse.SUPPRESS)
    p.add_argument("--allow-api-key", action="store_true",
                   help="run even though ANTHROPIC_API_KEY is set, which bills the API")
    p.add_argument("--dry-run", action="store_true", help="print the plan and start nothing")
    args = p.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9._-]+", args.job):
        p.error("--job may hold only letters, digits, '.', '_' and '-'")
    if args.label is not None and not re.fullmatch(r"[A-Za-z0-9._-]+", args.label):
        p.error("--label may hold only letters, digits, '.', '_' and '-'")
    args.log_dir = args.log_dir or default_log_root() / args.job
    return args


def read_prompt(args: argparse.Namespace) -> str:
    if args.prompt is not None:
        return args.prompt
    if str(args.prompt_file) == "-":
        return sys.stdin.read()
    return args.prompt_file.read_text()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if os.environ.get("ANTHROPIC_API_KEY") and not args.allow_api_key and not args.dry_run:
        print("ANTHROPIC_API_KEY is set, so `claude -p` would bill the API instead of your "
              "subscription. Unset it, or pass --allow-api-key.", file=sys.stderr)
        return 2
    prompt = read_prompt(args)
    if not prompt.strip():
        print("the prompt is empty", file=sys.stderr)
        return 2
    path = args.checkout.expanduser()
    checkout = toplevel(path.resolve()) if path.is_dir() else None
    if checkout is None:
        print(f"not a git checkout: {args.checkout}", file=sys.stderr)
        return 2
    plan = plan_for(checkout, args.label or checkout.name, prompt, args)
    for note in plan.notes:
        if "may still be running" in note:
            say(f"warning {plan.label}: {note}")

    if args.dry_run:
        level, note = (None, None) if args.no_admission else read_pressure_level()
        print(json.dumps(asdict(plan) | {
            "command": plan.command[:2] + ["<prompt>"] + plan.command[3:],
            "pressure_level": level,
            "pressure_note": note,
        }))
        return 0

    args.log_dir.mkdir(parents=True, exist_ok=True)
    outcome = run(plan, args)
    first = outcome.result.splitlines()[0][:120] if outcome.result else ""
    turns = f" ({outcome.turns} turns)" if outcome.turns is not None else ""
    say(f"{outcome.status:7} {outcome.label}{turns}: {first}")
    line = json.dumps(asdict(outcome))
    (args.log_dir / f"{plan.label}.outcome.json").write_text(line + "\n")
    print(line, flush=True)
    return EXIT[outcome.status]


if __name__ == "__main__":
    sys.exit(main())
