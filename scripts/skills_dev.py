#!/usr/bin/env python3
"""skills-dev mods: the commands for working on this repository's mods, in its dev shell.

  skills-dev mods check [MOD ...]  validate, type-check and test the mods under plugins/
  skills-dev mods try MOD          start Claude Code with a mod loaded from its folder

`skills-dev test` is the dev shell's own: flake.nix runs pytest and bash on every test, these tools'
tests among them.

Exit status: 0 when everything passed, 1 when a check failed or a needed file is missing,
2 on a usage error. Standard library only.
"""

from __future__ import annotations

import argparse
import glob
import os
import pathlib
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence

ROOT = pathlib.Path(os.environ.get("PRJ_ROOT") or pathlib.Path(__file__).resolve().parent.parent)

# Where a mod's Claude Code API declarations go, for `tsc -p`. The engine lays them there when it
# loads the mod from a folder it watches; `mods check` copies them in where none has.
LAID_TYPES = pathlib.Path(".claude-plugin/types/claude-code/index.d.ts")

Runner = Callable[[Sequence[str]], int]


def run(command: Sequence[str]) -> int:
    return subprocess.run(list(command), check=False).returncode


# ---- mods


def resolve_mods(root: pathlib.Path, names: Sequence[str]) -> list[pathlib.Path]:
    """The mods named, as folders or names under plugins/; with none, every mod there."""
    plugins = root / "plugins"
    if not names:
        return sorted(m.parent.parent for m in plugins.glob("*/.claude-plugin/plugin.json"))
    return [pathlib.Path(n).resolve() if pathlib.Path(n).is_dir() else plugins / n for n in names]


def newest(paths: Iterable[str], mtime: Callable[[str], float] = os.path.getmtime) -> str | None:
    """The most recently written of the paths, or None when there are none."""
    return max(paths, key=mtime, default=None)


def types_candidates(version: str, uid: int) -> list[str]:
    """The API declarations a running Claude Code build wrote for its plugin-authoring skill."""
    pattern = f"/tmp/claude-{uid}/bundled-skills/{version}/*/plugin-authoring/types/claude-code.d.ts"
    return [p for p in glob.glob(pattern) if os.path.isfile(p)]


def claude_version() -> str:
    out = subprocess.run(["claude", "--version"], check=True, capture_output=True, text=True).stdout
    return out.split()[0]


def lay_types(mod: pathlib.Path) -> bool:
    version = claude_version()
    source = newest(types_candidates(version, os.getuid()))
    if source is None:
        print(
            f"skills-dev mods check: no Claude Code {version} API types to lay in {mod}/.claude-plugin/types/.\n"
            "skills-dev mods check: load the plugin-authoring skill in a Claude Code session once, which writes"
            f" them, or start one with `skills-dev mods try {mod.name}`, then run this again.",
            file=sys.stderr,
        )
        return False
    laid = mod / LAID_TYPES
    laid.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, laid)
    print(f"skills-dev mods check: laid {source}", file=sys.stderr)
    return True


def check_steps(mod: pathlib.Path) -> list[tuple[str, list[str]]]:
    return [
        ("claude plugin validate", ["claude", "plugin", "validate", str(mod)]),
        ("tsc -p", ["tsc", "-p", str(mod)]),
        ("claude plugin test", ["claude", "plugin", "test", str(mod)]),
    ]


def cmd_mods_check(args: argparse.Namespace, root: pathlib.Path = ROOT, runner: Runner = run) -> int:
    mods = resolve_mods(root, args.mods)
    missing = [str(m) for m in mods if not (m / ".claude-plugin/plugin.json").is_file()]
    if missing:
        print(f"skills-dev mods check: not a mod: {', '.join(missing)}", file=sys.stderr)
        return 1
    for mod in mods:
        if not (mod / LAID_TYPES).is_file() and not lay_types(mod):
            return 1
        print(f"==== {mod.name}", flush=True)
        for title, command in check_steps(mod):
            print(f"== {title}", flush=True)
            if runner(command) != 0:
                return 1
    return 0


def cmd_mods_try(args: argparse.Namespace, root: pathlib.Path = ROOT, runner: Runner = run) -> int:
    (mod,) = resolve_mods(root, [args.mod])
    if not (mod / ".claude-plugin/plugin.json").is_file():
        print(f"skills-dev mods try: not a mod: {mod}", file=sys.stderr)
        return 1
    return runner(["claude", "--plugin-dir", str(mod), *args.claude_args])


# ---- arguments


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skills-dev",
        description="The commands for working on coding-agent-skills.",
        epilog="`skills-dev test` runs every test, `nix fmt` formats, and `nix flake check` runs "
        "the formatting check and every test in the sandbox.",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    mods = commands.add_parser("mods", help="check or try the Claude Code mods under plugins/")
    mods_commands = mods.add_subparsers(dest="mods_command", required=True, metavar="COMMAND")

    check = mods_commands.add_parser(
        "check",
        help="validate, type-check and test the mods",
        description="Run `claude plugin validate`, `tsc -p` and `claude plugin test` on each mod, one after another, "
        "stopping at the first failure. Where no Claude Code engine has laid a mod's API declarations, copies them "
        "from the ones the running build wrote for its plugin-authoring skill. Needs `claude` and `tsc` on PATH.",
    )
    check.add_argument("mods", nargs="*", metavar="MOD", help="a mod's folder, or its name under plugins/ (default: every mod)")
    check.set_defaults(func=cmd_mods_check)

    try_ = mods_commands.add_parser(
        "try",
        help="start Claude Code with a mod loaded from its folder, without installing it",
        description="Run `claude --plugin-dir MOD`, passing on any arguments after MOD.",
    )
    try_.add_argument("mod", metavar="MOD", help="a mod's folder, or its name under plugins/")
    try_.add_argument("claude_args", nargs=argparse.REMAINDER, metavar="ARG", help="passed on to claude")
    try_.set_defaults(func=cmd_mods_try)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
