#!/usr/bin/env python3
"""Tests for reply_lint_hook.py and reply-lint-hook.sh: `skills-dev test coding-agent-kanban-turn-responses`.

Standard library only. The decision is tested on response texts in memory; the hook runs end to
end through bash on hook input JSON, with preferences files and a transcript in a temporary
directory.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

import lint_reply
import reply_lint_hook as hook

HERE = pathlib.Path(hook.__file__).resolve().parent
HOOK = HERE / "reply-lint-hook.sh"
BASH = shutil.which("bash")
S = lint_reply.SEPARATOR

HEADER = "✅ **Done:**  \n" + "▔" * 8 + "\n"
ITEMS = (
    "1. **The hook script**  \n"
    "   `scripts/reply_lint_hook.py`, in commit 1234abc.\n"
    "{gap}"
    "2. **The flake check**  \n"
    "   It runs the hook's tests.\n"
)
CLEAN = "The hook is in.\n\n" + HEADER + ITEMS.format(gap=f"   {S}\n")
NO_SEPARATOR = "The hook is in.\n\n" + HEADER + ITEMS.format(gap="")
NO_STATUS_LIST = "The steps:\n\n" + ITEMS.format(gap="")

PROMPT = {"type": "user", "turnOrigin": "human", "promptId": "0f311c94aa", "message": {"content": "go"}}
SKILL_CALL = {
    "type": "assistant",
    "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": hook.SKILL}}]},
}
SKILL_TEXT = {
    "type": "user",
    "isMeta": True,
    "message": {"content": [{"type": "text", "text": f"Base directory for this skill: /h/.claude/skills/{hook.SKILL}\n\n# K"}]},
}


def reply(text: str) -> dict:
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


def decision(text: str, setting: str, already_blocked: bool = False) -> dict | None:
    return hook.decide(hook.findings_of(text), setting, already_blocked)


class DecideTest(unittest.TestCase):
    def test_a_missing_separator_reminds_at_remind(self) -> None:
        output = decision(NO_SEPARATOR, "remind")
        self.assertEqual(set(output), {"systemMessage"})
        self.assertIn("[a]", output["systemMessage"])

    def test_a_missing_separator_blocks_at_block(self) -> None:
        output = decision(NO_SEPARATOR, "block")
        self.assertEqual(output["decision"], "block")
        self.assertIn("[a]", output["reason"])

    def test_a_second_failure_in_the_turn_is_not_blocked(self) -> None:
        output = decision(NO_SEPARATOR, "block", already_blocked=True)
        self.assertNotIn("decision", output)
        self.assertIn("[a]", output["systemMessage"])

    def test_a_clean_response_gets_nothing(self) -> None:
        self.assertEqual(hook.findings_of(CLEAN), ())
        for setting in hook.SETTINGS:
            self.assertIsNone(decision(CLEAN, setting))

    def test_a_response_with_no_status_list_gets_nothing(self) -> None:
        self.assertTrue(lint_reply.lint(NO_STATUS_LIST))
        self.assertEqual(hook.findings_of(NO_STATUS_LIST), ())
        self.assertIsNone(decision(NO_STATUS_LIST, "block"))

    def test_the_roll_up_alone_is_a_status_list(self) -> None:
        text = "📌 **Outstanding from previous turns:**\n" + "━" * 35 + "\n\n" + ITEMS.format(gap="")
        self.assertTrue(hook.findings_of(text))

    def test_off_says_nothing(self) -> None:
        self.assertIsNone(decision(NO_SEPARATOR, "off"))


class SettingTest(unittest.TestCase):
    def test_remind_is_the_default(self) -> None:
        self.assertEqual(hook.setting_of(()), "remind")
        self.assertEqual(hook.setting_of(("- Something else: yes\n",)), "remind")

    def test_the_project_file_wins(self) -> None:
        self.assertEqual(hook.setting_of(("- Reply lint: off\n", "- Reply lint: block\n")), "block")

    def test_bold_and_case_are_read(self) -> None:
        self.assertEqual(hook.setting_of(("- **Reply lint:** `Block`\n",)), "block")

    def test_an_unknown_value_is_ignored(self) -> None:
        self.assertEqual(hook.setting_of(("- Reply lint: off\n", "- Reply lint: deny\n")), "off")


class TranscriptTest(unittest.TestCase):
    def test_the_skill_tool_call_marks_the_skill_loaded(self) -> None:
        self.assertTrue(hook.skill_loaded((PROMPT, SKILL_CALL)))

    def test_a_plugin_namespaced_call_marks_it_too(self) -> None:
        call = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": f"p:{hook.SKILL}"}}]}}
        self.assertTrue(hook.skill_loaded((call,)))

    def test_the_base_directory_line_marks_the_skill_loaded(self) -> None:
        self.assertTrue(hook.skill_loaded((PROMPT, SKILL_TEXT)))

    def test_another_skill_or_a_mention_is_not_a_load(self) -> None:
        other = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": "humanizer"}}]}}
        mention = {"type": "user", "message": {"content": f"load {hook.SKILL} please"}}
        sibling = {"type": "user", "message": {"content": f"Base directory for this skill: /s/{hook.SKILL}-old"}}
        self.assertFalse(hook.skill_loaded((PROMPT, other, mention, sibling, reply(NO_SEPARATOR))))

    def test_a_half_written_line_is_skipped(self) -> None:
        text = json.dumps(PROMPT) + "\n\n[1]\n" + json.dumps(SKILL_CALL) + '\n{"type": "assi'
        self.assertEqual(hook.records_of(text), (PROMPT, SKILL_CALL))

    def test_the_transcript_stands_in_for_a_missing_message(self) -> None:
        records = (PROMPT, SKILL_CALL, reply("✅ working · 💤 the rest"), reply(NO_SEPARATOR))
        self.assertEqual(hook.response_of({}, records), NO_SEPARATOR)
        self.assertEqual(hook.response_of({"last_assistant_message": CLEAN}, records), CLEAN)
        self.assertEqual(hook.response_of({}, ()), "")


@unittest.skipIf(BASH is None, "bash is not on PATH")
class HookTest(unittest.TestCase):
    """The hook end to end: reply-lint-hook.sh on hook input, as the plugin runs it."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.home, self.project = root / "home", root / "project"
        self.home.mkdir()
        self.project.mkdir()
        self.transcript = root / "session.jsonl"
        self.write_transcript((PROMPT, SKILL_CALL, reply(NO_SEPARATOR)))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_transcript(self, records: tuple[dict, ...]) -> None:
        self.transcript.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

    def prefer(self, directory: pathlib.Path, setting: str) -> None:
        folder = directory / ".agents" / "skills"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{hook.SKILL}.preferences.md").write_text(f"- Reply lint: {setting}\n", encoding="utf-8")

    def run_hook(self, message: str | None = NO_SEPARATOR, active: bool = False, **extra: object) -> dict | None:
        payload = {
            "session_id": "s1",
            "hook_event_name": "Stop",
            "transcript_path": str(self.transcript),
            "cwd": str(self.project),
            "stop_hook_active": active,
            **({"last_assistant_message": message} if message is not None else {}),
            **extra,
        }
        env = {"PATH": os.environ.get("PATH", ""), "HOME": str(self.home), "CLAUDE_PROJECT_DIR": str(self.project)}
        done = subprocess.run(
            [BASH, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env=env, check=True
        )
        self.assertEqual(done.stderr, "")
        return json.loads(done.stdout) if done.stdout else None

    def test_remind_with_no_preferences(self) -> None:
        output = self.run_hook()
        self.assertEqual(set(output), {"systemMessage"})
        self.assertIn("[a]", output["systemMessage"])

    def test_block_once_per_turn(self) -> None:
        self.prefer(self.project, "block")
        self.assertEqual(self.run_hook()["decision"], "block")
        self.assertEqual(set(self.run_hook(active=True)), {"systemMessage"})

    def test_the_project_preference_overrides_the_users(self) -> None:
        self.prefer(self.home, "block")
        self.prefer(self.project, "off")
        self.assertIsNone(self.run_hook())

    def test_clean_and_unlisted_responses_pass(self) -> None:
        self.prefer(self.project, "block")
        self.assertIsNone(self.run_hook(CLEAN))
        self.assertIsNone(self.run_hook(NO_STATUS_LIST))

    def test_the_transcript_stands_in_for_a_missing_message(self) -> None:
        self.assertIn("[a]", self.run_hook(message=None)["systemMessage"])

    def test_a_session_that_never_loaded_the_skill_passes(self) -> None:
        self.prefer(self.project, "block")
        self.write_transcript((PROMPT, reply(NO_SEPARATOR)))
        self.assertIsNone(self.run_hook())
        self.write_transcript((PROMPT, {"type": "user", "message": {"content": f"what is {hook.SKILL}?"}}))
        self.assertIsNone(self.run_hook())

    def test_no_transcript_passes(self) -> None:
        self.transcript.unlink()
        self.assertIsNone(self.run_hook())

    def test_bad_input_passes(self) -> None:
        done = subprocess.run([BASH, str(HOOK)], input="not json", capture_output=True, text=True, check=True)
        self.assertEqual((done.stdout, done.stderr), ("", ""))


if __name__ == "__main__":
    unittest.main()
