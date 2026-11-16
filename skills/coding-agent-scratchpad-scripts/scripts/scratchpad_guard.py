#!/usr/bin/env python3
"""scratchpad_guard: keep loose program files out of temporary directories.

A Claude Code hook, run by scratchpad-guard.sh with the hook's JSON input on
stdin. Standard library only, and Python 3.9 or later.

- PreToolUse on Bash, Write and Edit: finds a loose program file in a
  temporary directory being written, edited, run, made executable, or any file
  there being sourced. At the setting `remind` the call runs and the reason is
  added as context; at `deny` the call is denied with the reason; at `off`
  nothing is printed.
- SubagentStart: gives the subagent the rule in four lines, unless `off`.

A path counts when it is under a temporary root (/tmp, /private/tmp,
/var/folders, /private/var/folders, $TMPDIR, or the literal text `$TMPDIR` or
`${TMPDIR}`, which covers a session's `.../scratchpad/`), has a program
extension, and no folder between it and the root holds a project marker.

The setting is the line `Scratchpad guard: deny`, `remind` or `off` in
`~/.agents/skills/coding-agent-scratchpad-scripts.preferences.md`, overridden by
the same file under `.agents/skills/` in the project; `remind` when neither
has it.

Bash commands are read by pattern, not by a shell parser: a path built from a
variable (`"$S/x.py"`) isn't seen, and a whole quoted argument is one word, so
`echo "python3 /tmp/t.py"` runs nothing.

Every call of the hook pays for this module's start, so it imports nothing it
can do without (no `typing` or `pathlib`); annotations are never evaluated.
"""

from __future__ import annotations

import collections
import functools
import itertools
import json
import os
import posixpath
import re
import shlex
import sys
from collections.abc import Callable, Mapping, Sequence

SKILL = "coding-agent-scratchpad-scripts"
DEFAULT_SETTING = "remind"

FIXED_ROOTS = ("/tmp", "/private/tmp", "/var/folders", "/private/var/folders")
LITERAL_ROOTS = ("${TMPDIR}", "$TMPDIR")
PROGRAM_EXTENSIONS = frozenset(
    (".py", ".sh", ".bash", ".zsh", ".fish", ".js", ".mjs", ".cjs", ".ts", ".rb", ".pl", ".awk", ".sed", ".bb", ".clj")
)
MARKERS = (".git", "flake.nix", "package.json", "pyproject.toml", "Cargo.toml", "deps.edn")

INTERPRETERS = frozenset(("python", "python3", "bash", "sh", "zsh", "node", "bun", "deno", "ruby", "perl", "bb"))
VERSIONED_PYTHON = re.compile(r"^python3?(\.\d+)*$")
# Flags after which an interpreter runs code from its argument or a module, not a file.
INLINE_FLAGS = frozenset(("-c", "-e", "-E", "-m", "--eval", "-p", "--print"))
# Options whose value is the next word, so it isn't taken for the script.
VALUE_OPTIONS = frozenset(
    ("-W", "-X", "-r", "--require", "--import", "--loader", "--with", "--with-requirements", "--with-editable",
     "--python", "--project", "--directory", "--from", "--index", "--env-file", "--group", "--extra", "--package")
)
SUBCOMMAND_RUN = frozenset(("bun", "deno"))
COMMAND_PREFIXES = frozenset(("env", "exec", "time", "command", "nohup", "sudo", "nice"))
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
PUNCTUATION = frozenset("();<>|&")
WRITE_REDIRECTS = frozenset((">", ">>", ">|", "&>", "&>>"))
HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
SETTING_LINE = re.compile(r"^\W*scratchpad guard\W*(deny|remind|off)\W*$", re.IGNORECASE | re.MULTILINE)

WAYS_OUT = (
    "The scratchpad holds data, not programs. Instead: edit a file with the Edit or Write tool, never a generated "
    "script; run a one-off check inline, as a heredoc into `python3 -` (`python3 - <<'PYEOF'` ... `PYEOF`) with no "
    "file written; and make anything run twice a named tool in the project. Never `source` a generated file: put "
    "its commands in the Bash call. Data files (.md, .txt, .json, .log) in the scratchpad are fine."
)
SUBAGENT_RULES = "\n".join(
    (
        "Edit files with the Edit or Write tool, never with a generated script.",
        "Run a one-off check inline in the Bash call, such as a heredoc into `python3 -`, with no file written.",
        "Write no program files (.py, .sh, .js, ...) to the scratchpad or a temporary directory; "
        "anything run twice becomes a named tool in the project.",
        "Never `source` a generated file; put its commands in the Bash call.",
    )
)

# What the core needs from outside: $TMPDIR (str or None), and has_marker(folder) -> bool, the stat calls.
Context = collections.namedtuple("Context", ("tmpdir", "has_marker"))
# action is write, edit, redirect, tee, run, chmod or source.
Finding = collections.namedtuple("Finding", ("action", "path"))

DESCRIPTIONS = {
    "write": "the Write tool would write the program file `{}`",
    "edit": "the Edit tool would change the program file `{}`",
    "redirect": "the command writes the program file `{}`",
    "tee": "the command writes the program file `{}`",
    "run": "the command runs the program file `{}`",
    "chmod": "the command makes the program file `{}` executable",
    "source": "the command sources `{}`, a file in a temporary directory",
}


# ---- paths


def temp_location(path: str, ctx: Context) -> tuple[str, str] | None:
    """The (root, path) a path lies under, $TMPDIR's literal text resolved where known, or None."""
    literal = next((lit for lit in LITERAL_ROOTS if path.startswith(lit + "/")), None)
    tmpdir = ctx.tmpdir.rstrip("/") if ctx.tmpdir else None
    if literal is not None:
        return (tmpdir, posixpath.normpath(tmpdir + path[len(literal):])) if tmpdir else (literal, path)
    if not path.startswith("/"):
        return None
    normal = posixpath.normpath(path)
    roots = FIXED_ROOTS + ((tmpdir,) if tmpdir else ())
    matching = [root for root in roots if normal.startswith(root + "/")]
    return (max(matching, key=len), normal) if matching else None


def folders_between(root: str, path: str) -> tuple[str, ...]:
    """The folders strictly below root that hold path, outermost first."""
    parts = path[len(root) + 1:].split("/")[:-1]
    return tuple(root + "/" + rel for rel in itertools.accumulate(parts, lambda a, b: a + "/" + b))


def loose_program(path: str, ctx: Context) -> str | None:
    """The path, resolved, if it is a loose program file under a temporary root."""
    location = temp_location(path, ctx)
    if location is None or posixpath.splitext(location[1])[1].lower() not in PROGRAM_EXTENSIONS:
        return None
    root, resolved = location
    return None if any(ctx.has_marker(folder) for folder in folders_between(root, resolved)) else resolved


def under_temp_root(path: str, ctx: Context) -> str | None:
    location = temp_location(path, ctx)
    return location[1] if location else None


# ---- Write and Edit


def file_path_findings(action: str, tool_input: Mapping, ctx: Context) -> tuple[Finding, ...]:
    path = tool_input.get("file_path")
    found = loose_program(path, ctx) if isinstance(path, str) else None
    return (Finding(action, found),) if found else ()


write_findings = functools.partial(file_path_findings, "write")
edit_findings = functools.partial(file_path_findings, "edit")


# ---- Bash


def without_heredoc_bodies(command: str) -> str:
    """The command with each heredoc's body and closing line removed, so its text isn't read as commands."""

    def step(state, line):
        kept, pending = state
        if pending:
            return (kept, pending[1:] if line.strip() == pending[0] else pending)
        return (kept + (line,), tuple(m.group(2) for m in HEREDOC.finditer(line)))

    kept, _ = functools.reduce(step, command.split("\n"), ((), ()))
    return "\n".join(kept)


def tokens(command: str) -> tuple[str, ...]:
    """Shell words and operators, newlines as `;`, with a rougher split when the quoting doesn't balance."""
    text = without_heredoc_bodies(command.replace("\\\n", " ")).replace("\n", " ; ")
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        return tuple(lexer)
    except ValueError:
        return tuple(re.findall(r"[();<>|&]+|[^\s();<>|&]+", text))


def is_operator(token: str | None) -> bool:
    return bool(token) and set(token) <= PUNCTUATION


def is_redirect(token: str | None) -> bool:
    return is_operator(token) and ("<" in token or ">" in token)


def simple_commands(words: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """The words split at `;`, `&&`, `||`, `|`, `&` and parentheses; redirects stay with their command."""
    groups = itertools.groupby(words, lambda w: is_operator(w) and not is_redirect(w))
    return tuple(tuple(group) for separator, group in groups if not separator)


def is_prefix_word(word: str) -> bool:
    """An assignment or a command such as `env` or `time` that runs the words after it."""
    return bool(ASSIGNMENT.match(word)) or posixpath.basename(word) in COMMAND_PREFIXES


def argv_and_targets(command: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The command's words without redirects, and the files its `>`, `>>` and `&>` write."""
    triples = tuple(zip((None,) + command[:-1], command, command[1:] + (None,)))
    targets = tuple(word for prev, word, _ in triples if prev in WRITE_REDIRECTS)
    argv = tuple(
        word
        for prev, word, nxt in triples
        if not is_redirect(word) and not is_redirect(prev) and not (word.isdigit() and is_redirect(nxt))
    )
    return tuple(itertools.dropwhile(is_prefix_word, argv)), targets


def script_argument(args: tuple[str, ...]) -> str | None:
    """The first word an interpreter would run as a file, or None when it runs inline code or a module."""

    def step(state, word):
        skip_next, found = state
        if found is not None or skip_next:
            return (False, found)
        if word in INLINE_FLAGS:
            return (False, "")
        if word in VALUE_OPTIONS:
            return (True, None)
        return (False, None) if word.startswith("-") and word != "-" else (False, word)

    _, found = functools.reduce(step, args, (False, None))
    return found or None


def interpreter_args(argv: tuple[str, ...]) -> tuple[str, ...] | None:
    """The interpreter's arguments when the command is an interpreter (or `uv run`), else None."""
    name = posixpath.basename(argv[0])
    if name == "uv":
        return argv[2:] if argv[1:2] == ("run",) else None
    if name not in INTERPRETERS and not VERSIONED_PYTHON.match(name):
        return None
    return argv[2:] if name in SUBCOMMAND_RUN and argv[1:2] == ("run",) else argv[1:]


def adds_execute(mode: str) -> bool:
    if re.fullmatch(r"0?[0-7]{3}", mode):
        return any(int(digit) & 1 for digit in mode[-3:])
    return any(re.fullmatch(r"[ugoa]*[+=][rwxXst]*[xX][rwxXst]*", part) for part in mode.split(","))


def command_findings(argv: tuple[str, ...], targets: tuple[str, ...], ctx: Context) -> tuple[Finding, ...]:
    def loose(action, paths):
        return tuple(Finding(action, found) for found in (loose_program(p, ctx) for p in paths) if found)

    redirects = loose("redirect", targets)
    if not argv:
        return redirects
    name, args = posixpath.basename(argv[0]), argv[1:]
    operands = tuple(a for a in args if not a.startswith("-"))
    if name == "tee":
        return redirects + loose("tee", operands)
    if name in ("source", "."):
        sourced = under_temp_root(args[0], ctx) if args else None
        return redirects + ((Finding("source", sourced),) if sourced else ())
    if name == "chmod":
        return redirects + (loose("chmod", operands[1:]) if operands and adds_execute(operands[0]) else ())
    interpreted = interpreter_args(argv)
    if interpreted is not None:
        script = script_argument(interpreted)
        return redirects + (loose("run", (script,)) if script else ())
    return redirects + loose("run", argv[:1])


def bash_findings(tool_input: Mapping, ctx: Context) -> tuple[Finding, ...]:
    command = tool_input.get("command")
    if not isinstance(command, str):
        return ()
    commands = (argv_and_targets(c) for c in simple_commands(tokens(command)))
    return tuple(itertools.chain.from_iterable(command_findings(argv, targets, ctx) for argv, targets in commands))


MATCHERS: Mapping[str, Callable[[Mapping, Context], tuple[Finding, ...]]] = {
    "Write": write_findings,
    "Edit": edit_findings,
    "Bash": bash_findings,
}


# ---- decision


def setting_from(texts: Sequence[str]) -> str:
    """The setting in the last of the preferences texts that has one, or the default."""
    found = [matches[-1].lower() for matches in (SETTING_LINE.findall(text) for text in texts) if matches]
    return found[-1] if found else DEFAULT_SETTING


def reason(findings: tuple[Finding, ...]) -> str:
    unique = tuple(dict.fromkeys(findings))
    what = "; ".join(DESCRIPTIONS[f.action].format(f.path) for f in unique)
    return f"Scratchpad guard (`{SKILL}`): {what}. {WAYS_OUT}"


def pre_tool_use(findings: tuple[Finding, ...], setting: str) -> dict | None:
    if not findings or setting == "off":
        return None
    if setting == "deny":
        decision = {"permissionDecision": "deny", "permissionDecisionReason": reason(findings)}
    else:
        decision = {"additionalContext": "This call goes ahead, but don't repeat it. " + reason(findings)}
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", **decision}}


def decide(event: Mapping, setting: str, ctx: Context) -> dict | None:
    """The hook's JSON output for one input, or None to print nothing."""
    name = event.get("hook_event_name")
    if name == "SubagentStart":
        return None if setting == "off" else {
            "hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": SUBAGENT_RULES}
        }
    if name != "PreToolUse":
        return None
    matcher = MATCHERS.get(event.get("tool_name"))
    tool_input = event.get("tool_input")
    findings = matcher(tool_input, ctx) if matcher and isinstance(tool_input, Mapping) else ()
    return pre_tool_use(findings, setting)


# ---- shell


def has_marker(folder: str) -> bool:
    try:
        return any(os.path.lexists(os.path.join(folder, m)) for m in MARKERS) or any(
            name.endswith(".html") for name in os.listdir(folder)
        )
    except OSError:
        return False


def read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as file:
            return file.read()
    except (OSError, UnicodeDecodeError):
        return ""


def preferences_texts(event: Mapping) -> tuple[str, ...]:
    project = os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or "."
    name = f".agents/skills/{SKILL}.preferences.md"
    return (read_text(os.path.join(os.path.expanduser("~"), name)), read_text(os.path.join(project, name)))


def main() -> int:
    try:
        event = json.loads(sys.stdin.read())
    except ValueError:
        return 0
    if not isinstance(event, dict):
        return 0
    output = decide(event, setting_from(preferences_texts(event)), Context(os.environ.get("TMPDIR"), has_marker))
    if output is not None:
        print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
