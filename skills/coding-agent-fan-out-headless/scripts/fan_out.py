#!/usr/bin/env python3
"""Run one prompt across many git checkouts, one headless Claude Code session each.

Each session starts with its checkout (or a git worktree of it) as the working
directory, so it loads that checkout's CLAUDE.md, skills, settings, hooks and
plugins, the Nix dev shell a plugin or `.envrc` provides among them, as a
session started there by hand would. The runs go in parallel; the script waits
for all of them and prints one line per checkout, then writes summary.json.

Where a run works (--where):
  worktree  (default) a git worktree of the checkout's HEAD, on the branch
            fan-out/<job>, at <checkout>.worktrees/fan-out-<job> beside it, so
            no run touches a working tree someone is using.
  checkout  the checkout itself.

Which session a run starts from (--session):
  continue  (default) the checkout's newest session, forked so the original is
            left as it was: `--continue --fork-session` in the checkout, or
            `--resume <its .jsonl> --fork-session` in a worktree, since a new
            worktree is a new directory with no sessions of its own. A checkout
            with no session gets a new one.
  new       always a new session.

A worktree holds only committed work, so a session continued in one may
remember edits that stayed behind, uncommitted, in the checkout. For a checkout
with uncommitted changes, --dirty decides what a continuing worktree run does:
  tell  (default) continue, and open the prompt with a note naming the
        uncommitted paths and saying their changes are not in the worktree.
  new   start a new session instead of continuing.
  skip  don't run in that checkout; commit or stash its work and rerun.

A run that fails on a usage limit stops the runner from starting any more; the
ones not started are reported as skipped. Each run's stream-json output and
stderr go to the log directory, one pair of files per checkout.

Examples:
  fan_out.py --dry-run --prompt 'Fix the failing tests' ~/git/a ~/git/b
  fan_out.py --job tidy --parallel 3 --prompt-file prompt.md ~/git/*/
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

PROJECTS_ROOT = Path.home() / ".claude" / "projects"
USAGE_LIMIT = re.compile(
    r"usage limit|limit reached|weekly limit|rate.?limit|\b429\b|resets? at",
    re.IGNORECASE,
)
RESULT_EXCERPT = 400


def project_key(path: Path) -> str:
    """The folder name Claude Code keeps a directory's sessions under."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def newest_session(checkout: Path, projects_root: Path = PROJECTS_ROOT) -> Path | None:
    """The checkout's most recently written session transcript, if it has one."""
    folder = projects_root / project_key(checkout)
    sessions = [p for p in folder.glob("*.jsonl") if p.is_file()]
    return max(sessions, key=lambda p: p.stat().st_mtime, default=None)


def worktree_path(checkout: Path, job: str) -> Path:
    return checkout.parent / f"{checkout.name}.worktrees" / f"fan-out-{job}"


def branch_name(job: str) -> str:
    return f"fan-out/{job}"


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


def unique_labels(checkouts: list[Path]) -> list[str]:
    seen: dict[str, int] = {}
    labels = []
    for checkout in checkouts:
        n = seen.get(checkout.name, 0)
        seen[checkout.name] = n + 1
        labels.append(checkout.name if n == 0 else f"{checkout.name}-{n + 1}")
    return labels


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
        f"Note from the fan-out runner: you are working in {workdir}, a git worktree made "
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


def plan_for(checkout: Path, label: str, prompt: str, args: argparse.Namespace) -> Plan:
    resume = newest_session(checkout, args.projects_root) if args.session == "continue" else None
    workdir = worktree_path(checkout, args.job) if args.where == "worktree" else checkout
    notes, skip = [], None
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
        f"fan-out {args.job}",
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
                command, notes, skip)


def run(plan: Plan, args: argparse.Namespace, stop: threading.Event) -> Outcome:
    checkout = Path(plan.checkout)
    outcome = Outcome(plan.label, plan.checkout, plan.workdir, "skipped",
                      resumed_from=plan.resume, notes=list(plan.notes))
    if plan.skip:
        outcome.result = f"not started: {plan.skip}"
        return outcome
    if stop.is_set():
        outcome.result = "not started: an earlier run hit a usage limit"
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
    command = env_wrapper(workdir) + plan.command
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
        stop.set()
    else:
        outcome.status = "failed"
    return outcome


def default_log_root() -> Path:
    state = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(state) / "coding-agent-fan-out"


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        epilog=__doc__.split("\n\n", 1)[1],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("checkouts", nargs="+", type=Path, help="git checkouts to run in")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--prompt", help="the prompt for every run")
    src.add_argument("--prompt-file", type=Path, help="read the prompt from a file ('-' for stdin)")
    p.add_argument("--job", default=dt.datetime.now().strftime("%Y%m%d-%H%M%S"),
                   help="names the branch, worktree, sessions and log folder (default: a timestamp)")
    p.add_argument("--where", choices=["worktree", "checkout"], default="worktree")
    p.add_argument("--session", choices=["continue", "new"], default="continue")
    p.add_argument("--dirty", choices=["tell", "new", "skip"], default="tell",
                   help="a continuing worktree run in a checkout with uncommitted changes (default: tell)")
    p.add_argument("--parallel", type=int, default=4, help="runs at a time (default: 4)")
    p.add_argument("--model", help="passed to claude --model (default: your configured model)")
    p.add_argument("--effort", help="passed to claude --effort")
    p.add_argument("--permission-mode", default="auto", help="passed to claude (default: auto)")
    p.add_argument("--max-turns", type=int, help="passed to claude --max-turns")
    p.add_argument("--timeout", type=float, help="minutes before a run is killed")
    p.add_argument("--claude-arg", action="append", default=[],
                   help="one more argument for claude; repeat as needed")
    p.add_argument("--log-dir", type=Path, help="default: $XDG_STATE_HOME/coding-agent-fan-out/<job>")
    p.add_argument("--projects-root", type=Path, default=PROJECTS_ROOT, help=argparse.SUPPRESS)
    p.add_argument("--allow-api-key", action="store_true",
                   help="run even though ANTHROPIC_API_KEY is set, which bills the API")
    p.add_argument("--dry-run", action="store_true", help="print each run's plan and start nothing")
    args = p.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9._-]+", args.job):
        p.error("--job may hold only letters, digits, '.', '_' and '-'")
    if args.parallel < 1:
        p.error("--parallel must be at least 1")
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
        print("ANTHROPIC_API_KEY is set, so every `claude -p` run would bill the API "
              "instead of your subscription. Unset it, or pass --allow-api-key.", file=sys.stderr)
        return 2
    prompt = read_prompt(args)
    if not prompt.strip():
        print("the prompt is empty", file=sys.stderr)
        return 2

    checkouts = []
    for path in args.checkouts:
        top = toplevel(path.expanduser().resolve()) if path.expanduser().is_dir() else None
        if top is None:
            print(f"not a git checkout: {path}", file=sys.stderr)
            return 2
        if top not in checkouts:
            checkouts.append(top)
    plans = [plan_for(c, label, prompt, args) for c, label in zip(checkouts, unique_labels(checkouts))]

    if args.dry_run:
        for plan in plans:
            print(json.dumps(asdict(plan) | {"command": plan.command[:2] + ["<prompt>"] + plan.command[3:]}))
        return 0

    args.log_dir.mkdir(parents=True, exist_ok=True)
    print(f"{len(plans)} runs, {args.parallel} at a time; logs in {args.log_dir}", flush=True)
    stop = threading.Event()
    outcomes: list[Outcome] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as pool:
        futures = {pool.submit(run, plan, args, stop): plan for plan in plans}
        for future in concurrent.futures.as_completed(futures):
            outcome = future.result()
            outcomes.append(outcome)
            print(f"{outcome.status:7} {outcome.label}: {outcome.result.splitlines()[0][:120] if outcome.result else ''}",
                  flush=True)

    order = {plan.label: i for i, plan in enumerate(plans)}
    outcomes.sort(key=lambda o: order[o.label])
    summary = args.log_dir / "summary.json"
    summary.write_text(json.dumps([asdict(o) for o in outcomes], indent=2) + "\n")
    counts = {s: sum(o.status == s for o in outcomes) for s in ("ok", "failed", "limit", "skipped")}
    print(" · ".join(f"{n} {s}" for s, n in counts.items() if n) + f"; summary in {summary}")
    return 0 if counts["ok"] == len(outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())
