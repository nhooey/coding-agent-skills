#!/usr/bin/env python3
"""Tests for skills_dev.py, run from anywhere: `python3 -I scripts/test_skills_dev.py`.

Standard library only. The commands take the repository root and the runner as arguments, so these
build a throwaway tree and record the commands instead of running them.
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import skills_dev  # noqa: E402


def parse(*argv: str):
    return skills_dev.build_parser().parse_args(argv)


def usage_error(*argv: str) -> int:
    with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
        try:
            parse(*argv)
        except SystemExit as exit:
            return exit.code
    return 0


def help_text(*argv: str) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.suppress(SystemExit):
        parse(*argv, "--help")
    return out.getvalue()


class Recorder:
    def __init__(self, fail: set[str] = frozenset()) -> None:
        self.calls: list[list[str]] = []
        self.fail = fail

    def __call__(self, command) -> int:
        self.calls.append(list(command))
        return 1 if any(part.endswith(name) for part in command for name in self.fail) else 0


class Tree:
    """A throwaway repository: two skills with script tests, and two mods."""

    def __enter__(self) -> pathlib.Path:
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        for path in [
            "skills/alpha/scripts/alpha.py",
            "skills/alpha/scripts/test_alpha.py",
            "skills/alpha/scripts/test_hook.sh",
            "skills/alpha/scripts/test_data.json",
            "skills/beta/scripts/test_beta.py",
            "skills/gamma/SKILL.md",
            "plugins/one/.claude-plugin/plugin.json",
            f"plugins/one/{skills_dev.LAID_TYPES}",
            "plugins/two/.claude-plugin/plugin.json",
            f"plugins/two/{skills_dev.LAID_TYPES}",
            "plugins/notamod/README.md",
        ]:
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).touch()
        return root

    def __exit__(self, *exc) -> None:
        self.tmp.cleanup()


def quiet(function, *args, **kwargs) -> tuple[int, str]:
    err = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
        status = function(*args, **kwargs)
    return status, err.getvalue()


class ParserTest(unittest.TestCase):
    def test_a_command_is_required(self) -> None:
        self.assertEqual(usage_error(), 2)
        self.assertEqual(usage_error("mods"), 2)

    def test_unknown_commands_are_usage_errors(self) -> None:
        self.assertEqual(usage_error("build"), 2)
        self.assertEqual(usage_error("mods", "install"), 2)

    def test_test_takes_any_number_of_skills(self) -> None:
        self.assertEqual(parse("test").skills, [])
        self.assertEqual(parse("test", "a", "b").skills, ["a", "b"])
        self.assertIs(parse("test").func, skills_dev.cmd_test)

    def test_mods_check_takes_any_number_of_mods(self) -> None:
        self.assertEqual(parse("mods", "check").mods, [])
        self.assertEqual(parse("mods", "check", "one").mods, ["one"])
        self.assertIs(parse("mods", "check").func, skills_dev.cmd_mods_check)

    def test_mods_try_needs_one_mod_and_passes_the_rest_on(self) -> None:
        self.assertEqual(usage_error("mods", "try"), 2)
        args = parse("mods", "try", "one", "--model", "x")
        self.assertEqual((args.mod, args.claude_args), ("one", ["--model", "x"]))

    def test_help_lists_the_command_tokens_on_every_level(self) -> None:
        top = help_text()
        self.assertIn("test", top)
        self.assertIn("mods", top)
        self.assertIn("check", help_text("mods"))
        self.assertIn("try", help_text("mods"))
        self.assertIn("SKILL", help_text("test"))
        self.assertIn("MOD", help_text("mods", "check"))


class TestCommandTest(unittest.TestCase):
    def test_python_tests_run_isolated_and_shell_tests_under_bash(self) -> None:
        self.assertEqual(skills_dev.test_command(pathlib.Path("s/test_a.py")), ["python3", "-I", "s/test_a.py"])
        self.assertEqual(skills_dev.test_command(pathlib.Path("s/test_b.sh")), ["bash", "s/test_b.sh"])

    def test_other_files_are_not_tests(self) -> None:
        for name in ["s/a.py", "s/test_data.json", "s/hook.sh"]:
            self.assertIsNone(skills_dev.test_command(pathlib.Path(name)))


class FindTestsTest(unittest.TestCase):
    def test_every_skills_tests_in_order_when_none_is_named(self) -> None:
        with Tree() as root:
            found = [pathlib.Path(c[-1]).relative_to(root).as_posix() for c in skills_dev.find_tests(root, [])]
        self.assertEqual(
            found,
            ["skills/alpha/scripts/test_alpha.py", "skills/alpha/scripts/test_hook.sh", "skills/beta/scripts/test_beta.py"],
        )

    def test_only_the_named_skills(self) -> None:
        with Tree() as root:
            found = [pathlib.Path(c[-1]).name for c in skills_dev.find_tests(root, ["beta"])]
        self.assertEqual(found, ["test_beta.py"])


class CmdTestTest(unittest.TestCase):
    def test_runs_every_test_and_passes(self) -> None:
        with Tree() as root:
            runner = Recorder()
            status, _ = quiet(skills_dev.cmd_test, parse("test"), root, runner)
        self.assertEqual(status, 0)
        self.assertEqual(len(runner.calls), 3)

    def test_keeps_going_after_a_failure_then_names_it_and_fails(self) -> None:
        with Tree() as root:
            runner = Recorder(fail={"test_alpha.py"})
            status, err = quiet(skills_dev.cmd_test, parse("test"), root, runner)
        self.assertEqual(status, 1)
        self.assertEqual(len(runner.calls), 3)
        self.assertIn("FAILED skills/alpha/scripts/test_alpha.py", err)

    def test_an_unknown_skill_fails_before_running_anything(self) -> None:
        with Tree() as root:
            runner = Recorder()
            status, err = quiet(skills_dev.cmd_test, parse("test", "nope"), root, runner)
        self.assertEqual((status, runner.calls), (1, []))
        self.assertIn("no such skill: nope", err)

    def test_a_skill_with_no_tests_fails(self) -> None:
        with Tree() as root:
            status, err = quiet(skills_dev.cmd_test, parse("test", "gamma"), root, Recorder())
        self.assertEqual(status, 1)
        self.assertIn("no script tests", err)


class ResolveModsTest(unittest.TestCase):
    def test_every_folder_with_a_manifest_when_none_is_named(self) -> None:
        with Tree() as root:
            self.assertEqual([m.name for m in skills_dev.resolve_mods(root, [])], ["one", "two"])

    def test_a_name_is_looked_up_under_plugins(self) -> None:
        with Tree() as root:
            self.assertEqual(skills_dev.resolve_mods(root, ["two"]), [root / "plugins" / "two"])

    def test_a_folder_is_taken_as_it_is(self) -> None:
        with Tree() as root:
            folder = root / "plugins" / "one"
            self.assertEqual(skills_dev.resolve_mods(root, [str(folder)]), [folder.resolve()])


class NewestTest(unittest.TestCase):
    def test_the_latest_written_path(self) -> None:
        times = {"a": 1.0, "b": 3.0, "c": 2.0}
        self.assertEqual(skills_dev.newest(["a", "b", "c"], times.__getitem__), "b")

    def test_none_when_there_are_no_paths(self) -> None:
        self.assertIsNone(skills_dev.newest([], lambda p: 0.0))


class CmdModsTest(unittest.TestCase):
    def test_check_runs_the_three_steps_on_each_mod(self) -> None:
        with Tree() as root:
            runner = Recorder()
            status, _ = quiet(skills_dev.cmd_mods_check, parse("mods", "check"), root, runner)
            one, two = str(root / "plugins/one"), str(root / "plugins/two")
        self.assertEqual(status, 0)
        self.assertEqual(
            runner.calls,
            [
                ["claude", "plugin", "validate", one],
                ["tsc", "-p", one],
                ["claude", "plugin", "test", one],
                ["claude", "plugin", "validate", two],
                ["tsc", "-p", two],
                ["claude", "plugin", "test", two],
            ],
        )

    def test_check_stops_at_the_first_failure(self) -> None:
        with Tree() as root:
            runner = Recorder(fail={"one"})
            status, _ = quiet(skills_dev.cmd_mods_check, parse("mods", "check"), root, runner)
        self.assertEqual((status, len(runner.calls)), (1, 1))

    def test_check_refuses_a_folder_that_is_not_a_mod(self) -> None:
        with Tree() as root:
            runner = Recorder()
            status, err = quiet(skills_dev.cmd_mods_check, parse("mods", "check", "notamod"), root, runner)
        self.assertEqual((status, runner.calls), (1, []))
        self.assertIn("not a mod", err)

    def test_try_starts_claude_with_the_mod_and_the_arguments_after_it(self) -> None:
        with Tree() as root:
            runner = Recorder()
            status, _ = quiet(skills_dev.cmd_mods_try, parse("mods", "try", "one", "-c"), root, runner)
            one = str(root / "plugins/one")
        self.assertEqual((status, runner.calls), (0, [["claude", "--plugin-dir", one, "-c"]]))

    def test_try_refuses_a_folder_that_is_not_a_mod(self) -> None:
        with Tree() as root:
            runner = Recorder()
            status, _ = quiet(skills_dev.cmd_mods_try, parse("mods", "try", "notamod"), root, runner)
        self.assertEqual((status, runner.calls), (1, []))


if __name__ == "__main__":
    unittest.main()
