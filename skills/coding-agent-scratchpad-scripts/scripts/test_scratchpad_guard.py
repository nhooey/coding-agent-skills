#!/usr/bin/env python3
"""Tests for scratchpad_guard.py: the core over a table of hook inputs, and the hook end to end through bash."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import scratchpad_guard as guard  # noqa: E402

TMPDIR = "/run/user/1000/tmp"
SCRATCHPAD = "/private/tmp/claude-501/-Users-x-proj/0a1b/scratchpad"
# Folders holding a project marker, in place of the stat calls.
PROJECTS = frozenset(
    (
        "/tmp/clone",  # a clone: .git
        "/tmp/wt",  # a worktree: a .git file
        "/tmp/repro",  # a reproduction: flake.nix
        "/private/var/folders/x/T/fixture",  # a test fixture made with git init
        "/tmp/artifact",  # an artifact's scripts beside its .html page
        TMPDIR + "/pkg",  # package.json
    )
)
CTX = guard.Context(TMPDIR, PROJECTS.__contains__)
NO_TMPDIR = guard.Context(None, PROJECTS.__contains__)


def write(path):
    return {"hook_event_name": "PreToolUse", "tool_name": "Write", "tool_input": {"file_path": path, "content": "x"}}


def edit(path):
    return {"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {"file_path": path}}


def bash(command):
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}}


def tool(name, **tool_input):
    return {"hook_event_name": "PreToolUse", "tool_name": name, "tool_input": tool_input}


# Each row: what it shows, the hook input, and the findings as (action, path).
MATCHES = (
    # Write and Edit, under each temporary root.
    ("Write to the scratchpad", write(f"{SCRATCHPAD}/fix1.py"), (("write", f"{SCRATCHPAD}/fix1.py"),)),
    ("Write to /tmp", write("/tmp/ed1.py"), (("write", "/tmp/ed1.py"),)),
    ("Write to /private/tmp", write("/private/tmp/a.sh"), (("write", "/private/tmp/a.sh"),)),
    ("Write to /var/folders", write("/var/folders/x/T/a.js"), (("write", "/var/folders/x/T/a.js"),)),
    ("Write to /private/var/folders", write("/private/var/folders/x/T/a.ts"), (("write", "/private/var/folders/x/T/a.ts"),)),
    ("Write to $TMPDIR's value", write(f"{TMPDIR}/a.rb"), (("write", f"{TMPDIR}/a.rb"),)),
    ("Edit in /tmp", edit("/tmp/fix_test2.py"), (("edit", "/tmp/fix_test2.py"),)),
    ("a .. that stays in /tmp", write("/tmp/x/../y.py"), (("write", "/tmp/y.py"),)),
    ("a project marker at the root itself doesn't count", write("/tmp/clone.py"), (("write", "/tmp/clone.py"),)),
    # Bash: redirects and tee.
    ("> into /tmp", bash("echo 'print(1)' > /tmp/t.py"), (("redirect", "/tmp/t.py"),)),
    (">> into /tmp", bash("echo x >>/tmp/t.sh"), (("redirect", "/tmp/t.sh"),)),
    ("cat heredoc > /tmp", bash("cat > /tmp/gen.py <<'EOF'\nprint(1)\nEOF"), (("redirect", "/tmp/gen.py"),)),
    ("tee into /tmp", bash("echo x | tee /tmp/t.py"), (("tee", "/tmp/t.py"),)),
    ("tee -a into /tmp", bash("echo x | tee -a /tmp/t.zsh >/dev/null"), (("tee", "/tmp/t.zsh"),)),
    # Bash: running one.
    ("python3", bash("python3 /tmp/t.py"), (("run", "/tmp/t.py"),)),
    ("python", bash("python /tmp/t.py arg"), (("run", "/tmp/t.py"),)),
    ("python3.12", bash("python3.12 /tmp/t.py"), (("run", "/tmp/t.py"),)),
    ("python3 -X", bash("python3 -X dev -u /tmp/t.py"), (("run", "/tmp/t.py"),)),
    ("bash", bash("bash /tmp/t.sh"), (("run", "/tmp/t.sh"),)),
    ("sh", bash("sh /tmp/t.sh"), (("run", "/tmp/t.sh"),)),
    ("zsh", bash("zsh /tmp/t.zsh"), (("run", "/tmp/t.zsh"),)),
    ("node", bash("node /tmp/t.mjs"), (("run", "/tmp/t.mjs"),)),
    ("bun", bash("bun /tmp/t.ts"), (("run", "/tmp/t.ts"),)),
    ("bun run", bash("bun run /tmp/t.ts"), (("run", "/tmp/t.ts"),)),
    ("deno run", bash("deno run -A /tmp/t.ts"), (("run", "/tmp/t.ts"),)),
    ("ruby", bash("ruby /tmp/t.rb"), (("run", "/tmp/t.rb"),)),
    ("perl", bash("perl /tmp/t.pl"), (("run", "/tmp/t.pl"),)),
    ("bb", bash("bb /tmp/t.clj"), (("run", "/tmp/t.clj"),)),
    ("uv run", bash("uv run --with requests /tmp/t.py"), (("run", "/tmp/t.py"),)),
    ("an absolute interpreter path", bash("/usr/bin/env python3 /tmp/t.py"), (("run", "/tmp/t.py"),)),
    ("as the command itself", bash("/tmp/t.sh --flag"), (("run", "/tmp/t.sh"),)),
    ("after an assignment", bash("FOO=1 python3 /tmp/t.py"), (("run", "/tmp/t.py"),)),
    ("after &&", bash("cd /x && python3 /tmp/t.py"), (("run", "/tmp/t.py"),)),
    ("on a second line", bash("ls\npython3 /tmp/t.py"), (("run", "/tmp/t.py"),)),
    ("a quoted path argument", bash('python3 "/tmp/t.py"'), (("run", "/tmp/t.py"),)),
    ("written then run", bash("cat >/tmp/t.py <<'X'\nimport os\nX\npython3 /tmp/t.py"), (("redirect", "/tmp/t.py"), ("run", "/tmp/t.py"))),
    # The literal $TMPDIR, resolved when known.
    ("literal $TMPDIR", bash("python3 $TMPDIR/t.py"), (("run", f"{TMPDIR}/t.py"),)),
    ("literal ${TMPDIR}, quoted", bash('python3 "${TMPDIR}/t.py"'), (("run", f"{TMPDIR}/t.py"),)),
    ("literal $TMPDIR, unknown", bash("echo x > $TMPDIR/t.py"), (("redirect", "$TMPDIR/t.py"),)),
    # source or ., whatever the extension.
    ("source", bash("source /tmp/env.sh"), (("source", "/tmp/env.sh"),)),
    (". of a .txt", bash(". /tmp/env.txt && make"), (("source", "/tmp/env.txt"),)),
    ("source inside a project", bash("source /tmp/clone/.venv/bin/activate"), (("source", "/tmp/clone/.venv/bin/activate"),)),
    # chmod adding execute.
    ("chmod +x", bash("chmod +x /tmp/t.sh"), (("chmod", "/tmp/t.sh"),)),
    ("chmod u+x,g+w", bash("chmod u+x,g+w /tmp/t.sh"), (("chmod", "/tmp/t.sh"),)),
    ("chmod 755", bash("chmod 0755 /tmp/t.py"), (("chmod", "/tmp/t.py"),)),
)

EXTENSIONS = (".py", ".sh", ".bash", ".zsh", ".fish", ".js", ".mjs", ".cjs", ".ts", ".rb", ".pl", ".awk", ".sed", ".bb", ".clj")

LETS_THROUGH = (
    # Data in the scratchpad.
    *(("data " + ext, write(f"{SCRATCHPAD}/notes{ext}")) for ext in (".md", ".txt", ".json", ".log", ".csv", ".diff", ".patch", ".html")),
    ("a named log", write(f"{SCRATCHPAD}/ci-run-4412-log.txt")),
    ("no extension", write("/tmp/Makefile")),
    ("> into a data file", bash("gh pr view 78 --json body > /tmp/pr-78-body.md")),
    ("python3 writes a data file", bash("python3 tools/report.py > /tmp/report.json")),
    # Inline checks.
    ("python3 - heredoc", bash("python3 - <<'PYEOF'\nopen('/tmp/x.py', 'w')\nimport subprocess; subprocess.run(['python3', '/tmp/t.py'])\nPYEOF")),
    ("node -e", bash("node -e 'require(\"/tmp/t.js\")'")),
    ("bash -c", bash("bash -c 'source /tmp/env.sh; /tmp/t.sh'")),
    ("python3 -c", bash('python3 -c "import runpy; runpy.run_path(\'/tmp/t.py\')"')),
    ("python3 -m", bash("python3 -m pytest /tmp/t.py")),
    # Reading.
    ("cat", bash("cat /tmp/t.py")),
    ("grep", bash("grep -n main /tmp/t.py")),
    ("diff", bash("diff /tmp/a.py /tmp/b.py")),
    ("the Read tool", tool("Read", file_path="/tmp/t.py")),
    ("chmod without execute", bash("chmod 644 /tmp/t.sh; chmod -x /tmp/u.sh")),
    # Work inside a project in a temporary directory.
    ("a clone", bash("bash /tmp/clone/scripts/build.sh")),
    ("a clone, written", write("/tmp/clone/scripts/build.sh")),
    ("a worktree", edit("/tmp/wt/src/main.py")),
    ("a reproduction with a flake.nix", bash("python3 /tmp/repro/t.py")),
    ("a git init fixture", write("/private/var/folders/x/T/fixture/hooks/pre-commit.sh")),
    ("an artifact beside its .html page", write("/tmp/artifact/app.js")),
    ("a package under $TMPDIR", bash(f"node {TMPDIR}/pkg/lib/index.js")),
    # Program files anywhere else.
    ("the project", write("/Users/x/proj/tools/report.py")),
    ("a skill's scripts/", bash("python3 /Users/x/.agents/skills/s/scripts/t.py")),
    ("home", bash("bash ~/bin/t.sh")),
    ("a relative path", bash("python3 scripts/t.py > out.py")),
    ("/tmpfoo isn't /tmp", write("/tmpfoo/t.py")),
    # The two pattern-matching risks.
    ("a path built from a variable isn't seen", bash('S=/tmp; python3 "$S/x.py"')),
    ("a path inside a quoted string argument isn't run", bash('echo "python3 /tmp/t.py"; git commit -m "drop python3 /tmp/t.py"')),
    # Unbalanced quoting still reads.
    ("unbalanced quotes", bash("echo 'it's /tmp/notes.txt")),
)


class Matches(unittest.TestCase):
    def test_each_row(self):
        for name, event, expected in MATCHES:
            with self.subTest(name):
                ctx = NO_TMPDIR if "unknown" in name else CTX
                found = guard.MATCHERS[event["tool_name"]](event["tool_input"], ctx)
                self.assertEqual(tuple(tuple(f) for f in found), expected)

    def test_every_program_extension(self):
        self.assertEqual(guard.PROGRAM_EXTENSIONS, frozenset(EXTENSIONS))
        for ext in EXTENSIONS + (".PY",):
            with self.subTest(ext):
                self.assertTrue(guard.write_findings(write(f"{SCRATCHPAD}/t{ext}")["tool_input"], CTX))

    def test_every_project_marker_is_looked_for(self):
        with tempfile.TemporaryDirectory() as tmp:
            for marker in guard.MARKERS + ("index.html",):
                with self.subTest(marker):
                    folder = pathlib.Path(tmp, marker.replace(".", "_"))
                    folder.mkdir()
                    (folder / marker).mkdir() if marker == ".git" else (folder / marker).write_text("")
                    self.assertTrue(guard.has_marker(str(folder)))
            self.assertFalse(guard.has_marker(tmp + "/missing"))


class LetsThrough(unittest.TestCase):
    def test_each_row(self):
        for name, event in LETS_THROUGH:
            with self.subTest(name):
                self.assertIsNone(guard.decide(event, "deny", CTX))


class Decisions(unittest.TestCase):
    def test_deny_denies_with_the_ways_out(self):
        out = guard.decide(bash("python3 /tmp/t.py"), "deny", CTX)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertEqual(out["permissionDecision"], "deny")
        for way_out in ("Edit or Write tool", "`python3 -`", "named tool in the project"):
            self.assertIn(way_out, out["permissionDecisionReason"])

    def test_remind_adds_context_and_never_denies(self):
        out = guard.decide(write(f"{SCRATCHPAD}/fix1.py"), "remind", CTX)["hookSpecificOutput"]
        self.assertNotIn("permissionDecision", out)
        self.assertIn("named tool in the project", out["additionalContext"])

    def test_off_prints_nothing(self):
        self.assertIsNone(guard.decide(bash("source /tmp/env.sh"), "off", CTX))

    def test_subagent_start_gives_four_lines(self):
        out = guard.decide({"hook_event_name": "SubagentStart"}, "remind", CTX)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "SubagentStart")
        lines = out["additionalContext"].splitlines()
        self.assertEqual(len(lines), 4)
        for words, line in zip(("Edit or Write tool", "inline", "no program files", "`source`"), lines):
            self.assertIn(words, line)
        self.assertEqual(guard.decide({"hook_event_name": "SubagentStart"}, "deny", CTX)["hookSpecificOutput"], out)

    def test_subagent_start_is_silent_at_off(self):
        self.assertIsNone(guard.decide({"hook_event_name": "SubagentStart"}, "off", CTX))

    def test_other_events_and_odd_input_print_nothing(self):
        for event in ({**bash("python3 /tmp/t.py"), "hook_event_name": "PostToolUse"}, {}, bash(None), write(3)):
            self.assertIsNone(guard.decide(event, "deny", CTX))

    def test_a_repeated_path_is_named_once(self):
        reason = guard.reason((guard.Finding("run", "/tmp/t.py"),) * 2)
        self.assertEqual(reason.count("/tmp/t.py"), 1)


class Setting(unittest.TestCase):
    def test_remind_is_the_default(self):
        self.assertEqual(guard.setting_from(("", "")), "remind")
        self.assertEqual(guard.setting_from(("- Tier: 1\n",)), "remind")

    def test_the_project_overrides_the_user(self):
        self.assertEqual(guard.setting_from(("Scratchpad guard: deny\n", "Scratchpad guard: off\n")), "off")
        self.assertEqual(guard.setting_from(("Scratchpad guard: deny\n", "")), "deny")

    def test_a_markdown_list_item(self):
        self.assertEqual(guard.setting_from(("- **Scratchpad guard:** Deny\n",)), "deny")

    def test_the_documented_choices_are_not_a_setting(self):
        self.assertEqual(guard.setting_from(("Scratchpad guard: deny | remind | off\n",)), "remind")


class Hook(unittest.TestCase):
    """scratchpad-guard.sh, run as the plugin runs it, with real files and preferences."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        self.project = self.tmp / "project"
        (self.project / ".agents" / "skills").mkdir(parents=True)
        (self.home / ".agents" / "skills").mkdir(parents=True)
        self.scratch = self.tmp / "scratchpad"
        self.scratch.mkdir()
        (self.tmp / "clone" / ".git").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def prefer(self, where, text):
        (where / ".agents" / "skills" / "coding-agent-scratchpad-scripts.preferences.md").write_text(text)

    def run_hook(self, event):
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self.home),
            "TMPDIR": str(self.tmp) + "/",
            "CLAUDE_PROJECT_DIR": str(self.project),
        }
        done = subprocess.run(
            ["bash", str(HERE / "scratchpad-guard.sh")],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        return json.loads(done.stdout)["hookSpecificOutput"] if done.stdout.strip() else None

    def checks(self):
        return {
            "write fix1.py": write(f"{self.scratch}/fix1.py"),
            "write a log": write(f"{self.scratch}/ci-run-4412-log.txt"),
            "python3 t.py": bash(f"python3 {self.tmp}/t.py"),
            "source env.sh": bash(f"source {self.tmp}/env.sh"),
            "python3 - heredoc": bash("python3 - <<'PYEOF'\nprint(1)\nPYEOF"),
            "bash in a clone": bash(f"bash {self.tmp}/clone/scripts/build.sh"),
        }

    def test_with_no_setting_it_reminds_and_never_denies(self):
        outputs = {name: self.run_hook(event) for name, event in self.checks().items()}
        for name in ("write fix1.py", "python3 t.py", "source env.sh"):
            self.assertIn("additionalContext", outputs[name], name)
            self.assertNotIn("permissionDecision", outputs[name], name)
        for name in ("write a log", "python3 - heredoc", "bash in a clone"):
            self.assertIsNone(outputs[name], name)

    def test_at_deny_from_the_project_it_denies(self):
        self.prefer(self.home, "Scratchpad guard: off\n")
        self.prefer(self.project, "Scratchpad guard: deny\n")
        outputs = {name: self.run_hook(event) for name, event in self.checks().items()}
        for name in ("write fix1.py", "python3 t.py", "source env.sh"):
            self.assertEqual(outputs[name]["permissionDecision"], "deny", name)
        for name in ("write a log", "python3 - heredoc", "bash in a clone"):
            self.assertIsNone(outputs[name], name)

    def test_at_off_from_the_user_it_is_silent(self):
        self.prefer(self.home, "Scratchpad guard: off\n")
        self.assertIsNone(self.run_hook(write(f"{self.scratch}/fix1.py")))
        self.assertIsNone(self.run_hook({"hook_event_name": "SubagentStart", "agent_type": "Explore"}))

    def test_subagent_start(self):
        out = self.run_hook({"hook_event_name": "SubagentStart", "agent_type": "Explore"})
        self.assertEqual(len(out["additionalContext"].splitlines()), 4)

    def test_input_with_no_temporary_root_exits_at_once(self):
        self.assertIsNone(self.run_hook(bash("python3 tools/report.py")))
        self.assertIsNone(self.run_hook(write("/Users/x/proj/fix1.py")))

    def test_input_that_is_not_json_prints_nothing(self):
        done = subprocess.run(
            ["bash", str(HERE / "scratchpad-guard.sh")], input="{ /tmp/t.py", capture_output=True, text=True, check=False
        )
        self.assertEqual((done.returncode, done.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
