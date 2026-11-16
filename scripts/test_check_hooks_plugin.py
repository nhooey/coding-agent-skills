#!/usr/bin/env python3
"""Tests for check_hooks_plugin.py, against plugin folders built in a temporary directory."""

import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import check_hooks_plugin  # noqa: E402

GOOD_COMMAND = 'bash "${CLAUDE_PLUGIN_ROOT}/scripts/hook.sh"'


def plugin(root, hooks, scripts=None, manifest=None):
    """Write a plugin folder under root and return its path."""
    root = pathlib.Path(root)
    (root / ".claude-plugin").mkdir()
    (root / "hooks").mkdir()
    (root / "scripts").mkdir()
    (root / ".claude-plugin" / "plugin.json").write_text(
        json.dumps(manifest if manifest is not None else {"name": "p", "version": "0.1.0"})
    )
    (root / "hooks" / "hooks.json").write_text(hooks if isinstance(hooks, str) else json.dumps(hooks))
    for name, text in (scripts if scripts is not None else {"hook.sh": "exit 0\n"}).items():
        (root / "scripts" / name).write_text(text)
    return root


def session_start(command=GOOD_COMMAND):
    return {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": command}]}]}}


class CheckHooksPlugin(unittest.TestCase):
    def problems(self, *args, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            return check_hooks_plugin.check(plugin(tmp, *args, **kwargs))

    def test_a_good_plugin_passes(self):
        self.assertEqual(self.problems(session_start()), [])

    def test_invalid_json_is_reported(self):
        self.assertTrue(any("hooks.json" in p for p in self.problems("{not json")))

    def test_a_manifest_without_a_version_is_reported(self):
        self.assertIn("plugin.json: no version", self.problems(session_start(), manifest={"name": "p"}))

    def test_an_unknown_event_is_reported(self):
        hooks = {"hooks": {"SessionBegin": session_start()["hooks"]["SessionStart"]}}
        self.assertIn("hooks.json: unknown event SessionBegin", self.problems(hooks))

    def test_a_command_not_run_through_bash_is_reported(self):
        found = self.problems(session_start('"${CLAUDE_PLUGIN_ROOT}/scripts/hook.sh"'))
        self.assertTrue(any("command is not" in p for p in found), found)

    def test_an_absolute_path_is_reported(self):
        found = self.problems(session_start("bash /nix/store/x/hook.sh"))
        self.assertTrue(any("command is not" in p for p in found), found)

    def test_a_missing_script_is_reported(self):
        found = self.problems(session_start(), scripts={})
        self.assertTrue(any("no scripts/hook.sh" in p for p in found), found)

    def test_a_script_no_hook_runs_is_reported(self):
        found = self.problems(session_start(), scripts={"hook.sh": "exit 0\n", "stray.sh": "exit 0\n"})
        self.assertIn("scripts/stray.sh: no hook runs it", found)

    def test_a_helper_a_hook_script_names_passes(self):
        scripts = {"hook.sh": 'exec python3 "$(dirname "$0")/helper.py"\n', "helper.py": "print(1)\n"}
        self.assertEqual(self.problems(session_start(), scripts=scripts), [])

    def test_a_python_helper_that_does_not_compile_is_reported(self):
        scripts = {"hook.sh": 'exec python3 "$(dirname "$0")/helper.py"\n', "helper.py": "def (:\n"}
        found = self.problems(session_start(), scripts=scripts)
        self.assertTrue(any(p.startswith("scripts/helper.py:") for p in found), found)

    def test_a_module_a_helper_imports_passes(self):
        scripts = {
            "hook.sh": 'exec python3 -I -S "$(dirname "$0")/helper.py"\n',
            "helper.py": "import json\nfrom lib import thing\n",
            "lib.py": "thing = 1\n",
        }
        self.assertEqual(self.problems(session_start(), scripts=scripts), [])

    def test_a_module_a_helper_imports_but_the_plugin_lacks_is_reported(self):
        scripts = {
            "hook.sh": '# helper.py hands its graph work to lib.py\nexec python3 -I -S "$(dirname "$0")/helper.py"\n',
            "helper.py": "import lib\n",
        }
        found = self.problems(session_start(), scripts=scripts)
        self.assertIn("scripts/helper.py: imports lib, but there is no scripts/lib.py", found)

    def test_a_script_bash_cannot_parse_is_reported(self):
        found = self.problems(session_start(), scripts={"hook.sh": "if then fi (\n"})
        self.assertTrue(any(p.startswith("scripts/hook.sh:") for p in found), found)

    def test_a_non_command_hook_is_reported(self):
        hooks = {"hooks": {"SessionStart": [{"hooks": [{"type": "prompt", "prompt": "x"}]}]}}
        found = self.problems(hooks)
        self.assertTrue(any("not a command hook" in p for p in found), found)


if __name__ == "__main__":
    unittest.main()
