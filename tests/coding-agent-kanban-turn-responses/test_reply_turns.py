#!/usr/bin/env python3
"""Tests for reply_turns.py: `skills-dev test coding-agent-kanban-turn-responses`.

Standard library only. The turn reader, the lookups and the section splitter are tested on records
in memory; the command line runs on a transcript file.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import tempfile
import unittest

import reply_turns

SESSION = "8907a830-6e25-4a1b-ab2b-80ec191e55ac"


class TranscriptPathTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = tempfile.TemporaryDirectory()
        self.projects = pathlib.Path(self.home.name) / ".claude" / "projects"

    def tearDown(self) -> None:
        self.home.cleanup()

    def write(self, slug: str, session: str = SESSION) -> pathlib.Path:
        path = self.projects / slug / f"{session}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        return path

    def lookup(self, cwd: str, transcript: str | None = None) -> pathlib.Path:
        return reply_turns.transcript_path(transcript, SESSION, cwd, self.home.name)

    def test_project_root_names_its_own_project(self) -> None:
        path = self.write("-Users-a-repo")
        self.assertEqual(self.lookup("/Users/a/repo"), path)

    def test_worktree_names_the_main_checkout(self) -> None:
        path = self.write("-Users-a-repo")
        self.assertEqual(self.lookup("/Users/a/repo/.worktrees/branch"), path)

    def test_any_other_directory_finds_the_one_project_holding_the_session(self) -> None:
        path = self.write("-Users-a-repo")
        self.write("-Users-a-other", session="another-session")
        self.assertEqual(self.lookup("/nix/store/abc-skill/share/scripts"), path)

    def test_a_session_in_two_projects_is_not_guessed(self) -> None:
        self.write("-Users-a-repo")
        self.write("-Users-a-other")
        self.assertEqual(self.lookup("/tmp"), self.projects / "-tmp" / f"{SESSION}.jsonl")

    def test_no_transcript_anywhere_names_the_working_directory_s_path(self) -> None:
        self.assertEqual(self.lookup("/tmp"), self.projects / "-tmp" / f"{SESSION}.jsonl")

    def test_transcript_flag_wins(self) -> None:
        self.write("-Users-a-repo")
        self.assertEqual(self.lookup("/Users/a/repo", "/x/y.jsonl"), pathlib.Path("/x/y.jsonl"))


def prompt(prompt_id: str, text: str, origin: str = "human", **extra: object) -> dict:
    return {
        "type": "user",
        "turnOrigin": origin,
        "promptId": prompt_id,
        "uuid": UUIDS[prompt_id],
        "timestamp": "2026-11-16T10:00:00Z",
        "message": {"content": text},
        **extra,
    }


def reply(text: str, **extra: object) -> dict:
    return {
        "type": "assistant",
        "timestamp": "2026-11-16T10:00:30Z",
        "message": {"content": [{"type": "text", "text": text}, {"type": "tool_use", "id": "t", "name": "Bash"}]},
        **extra,
    }


def tool_result() -> dict:
    return {"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok"}]}}


FIRST = "aaaa1111-0000-4000-8000-000000000000"
SECOND = "bbbb2222-0000-4000-8000-000000000000"
THIRD = "aaaa1199-0000-4000-8000-000000000000"
# The prompt records' uuids, unrelated to their prompt ids; earlier replies named a turn by the last 6.
UUIDS = {FIRST: "5e1d-0c3f9e", SECOND: "77aa-d4b081", THIRD: "9b02-e6c27a"}

RECORDS = (
    {"type": "assistant", "message": {"content": [{"type": "text", "text": "before any prompt"}]}},
    prompt(FIRST, "first prompt\nsecond line"),
    reply("one"),
    tool_result(),
    reply("two"),
    reply("sidechain", isSidechain=True),
    prompt(SECOND, "a sidechain prompt", isSidechain=True),
    prompt(SECOND, "a summary", isCompactSummary=True),
    prompt(SECOND, "<agent-message from x>", origin="peer"),
    reply("   "),
    reply("three"),
    prompt(THIRD, "<task-notification>", origin="task_notification"),
)


class TurnsOfTest(unittest.TestCase):
    def test_human_peer_and_task_notification_prompts_open_turns(self) -> None:
        turns = reply_turns.turns_of(RECORDS)
        self.assertEqual([t.id for t in turns], ["aaaa1111", "bbbb2222", "aaaa1199"])

    def test_a_reply_is_its_turn_s_non_sidechain_text_blocks(self) -> None:
        turns = reply_turns.turns_of(RECORDS)
        self.assertEqual([t.replies for t in turns], [("one", "two"), ("three",), ()])
        self.assertEqual(turns[0].reply_times, ("2026-11-16T10:00:30Z",) * 2)
        self.assertEqual(turns[0].prompt, "first prompt\nsecond line")

    def test_a_message_sent_while_a_turn_ran_is_one_of_its_asides(self) -> None:
        aside = {
            "type": "attachment",
            "attachment": {"type": "queued_command", "prompt": "Decide.1.Y", "origin": {"kind": "human"}},
        }
        peer = {"type": "attachment", "attachment": {**aside["attachment"], "origin": {"kind": "peer"}}}
        turns = reply_turns.turns_of((prompt(FIRST, "go"), reply("one"), aside, peer))
        self.assertEqual(turns[0].asides, ("Decide.1.Y",))

    def test_a_report_sent_while_a_turn_ran_is_one_of_its_reports(self) -> None:
        def queued(text: str, kind: str | None) -> dict:
            origin = {"origin": {"kind": kind}} if kind else {}
            return {"type": "attachment", "attachment": {"type": "queued_command", "prompt": text, **origin}}

        records = (
            prompt(FIRST, "go"),
            queued("<task-notification>done</task-notification>", "task-notification"),
            queued("<agent-message>pushed</agent-message>", "peer"),
            queued("Decide.1.Y", "human"),
            queued("<task-notification>a hook was skipped</task-notification>", None),
        )
        turns = reply_turns.turns_of(records)
        self.assertEqual(
            turns[0].reports, ("<task-notification>done</task-notification>", "<agent-message>pushed</agent-message>")
        )
        self.assertEqual(turns[0].asides, ("Decide.1.Y",))

    def test_only_a_prompt_the_user_typed_is_their_own(self) -> None:
        submitted = prompt(SECOND, "reassess", origin="system", pluginPrompt={"name": "some-mod", "text": "reassess"})
        turns = reply_turns.turns_of(RECORDS[:-1] + (submitted,))
        self.assertEqual([(t.id, t.is_own) for t in turns], [("aaaa1111", True), ("bbbb2222", False), ("bbbb2222", False)])

    def test_a_prompt_the_kanban_pane_submits_is_the_user_s_own(self) -> None:
        submitted = prompt(
            SECOND, "1. A", origin="system", pluginPrompt={"name": "coding-agent-kanban-turns", "text": "1. A"}
        )
        turns = reply_turns.turns_of((prompt(FIRST, "go"), submitted))
        self.assertEqual([(t.prompt, t.is_own) for t in turns], [("go", True), ("1. A", True)])

    def test_shell_output_opens_no_turn(self) -> None:
        records = (
            prompt(FIRST, "go"),
            reply("one"),
            {"type": "user", "message": {"content": "<bash-input>git log</bash-input>"}},
            prompt(SECOND, "<bash-stdout>1234abc Fix</bash-stdout><bash-stderr></bash-stderr>"),
            prompt(THIRD, "<bash-stderr>fatal: not a git repository</bash-stderr>"),
        )
        for human_only in (False, True):
            with self.subTest(human_only=human_only):
                self.assertEqual([t.id for t in reply_turns.turns_of(records, human_only)], ["aaaa1111"])

    def test_a_prompt_a_plugin_submitted_opens_a_turn_with_the_text_it_sent(self) -> None:
        submitted = prompt(
            SECOND,
            "The some-mod plugin sent a message:\nreassess\n\nThis is how Claude Code…",
            origin="system",
            pluginPrompt={"name": "some-mod", "text": "reassess"},
        )
        system = prompt(THIRD, "a system prompt", origin="system")
        turns = reply_turns.turns_of((prompt(FIRST, "go"), reply("one"), submitted, reply("two"), system))
        self.assertEqual([(t.id, t.prompt) for t in turns], [("aaaa1111", "go"), ("bbbb2222", "reassess")])
        self.assertEqual(turns[1].replies, ("two",))

    def test_human_only_folds_other_prompts_into_the_turn_under_way(self) -> None:
        turns = reply_turns.turns_of(RECORDS, human_only=True)
        self.assertEqual([(t.id, t.replies) for t in turns], [("aaaa1111", ("one", "two", "three"))])


class FindTest(unittest.TestCase):
    turns = reply_turns.turns_of(RECORDS)

    def test_a_prompt_id_prefix_finds_its_turn(self) -> None:
        self.assertEqual(reply_turns.find(self.turns, "bbbb").id, "bbbb2222")

    def test_the_uuid_s_last_six_characters_find_its_turn(self) -> None:
        self.assertEqual(reply_turns.find(self.turns, "d4b081").id, "bbbb2222")
        self.assertEqual(reply_turns.find(self.turns, "0c3f9e").id, "aaaa1111")

    def test_an_ambiguous_id_names_the_candidates(self) -> None:
        with self.assertRaisesRegex(reply_turns.TurnError, r"ambiguous, matching aaaa1111 \(\w+\), aaaa1199"):
            reply_turns.find(self.turns, "aaaa11")

    def test_an_unknown_or_empty_id_matches_nothing(self) -> None:
        for ident in ("ffff", ""):
            with self.subTest(ident=ident), self.assertRaisesRegex(reply_turns.TurnError, "matches no turn of 3"):
                reply_turns.find(self.turns, ident)

    def test_current_is_the_last_turn(self) -> None:
        self.assertEqual(reply_turns.current(self.turns).id, "aaaa1199")
        with self.assertRaisesRegex(reply_turns.TurnError, "no turn"):
            reply_turns.current(())


REPLY = """Opening prose, in no section.

✅ **Done:**  
▔▔▔▔▔▔▔▔
1. **Fixed the loader**

📋 **To review:**  
- **The pull request**

🧠 **Decisions:**  
1. **Which cache**

Still open from earlier
🧠 **Decide:**  
- **An old one**
"""


class SectionsTest(unittest.TestCase):
    def test_each_header_opens_a_section_and_the_stop_line_closes_one(self) -> None:
        self.assertEqual(
            reply_turns.sections(REPLY),
            (
                ("Done", "✅ **Done:**  \n▔▔▔▔▔▔▔▔\n1. **Fixed the loader**"),
                ("To review", "📋 **To review:**  \n- **The pull request**"),
                ("Decisions", "🧠 **Decisions:**  \n1. **Which cache**"),
                ("Decide", "🧠 **Decide:**  \n- **An old one**"),
            ),
        )

    def test_a_topic_header_closes_the_section_above_it(self) -> None:
        text = (
            "**First topic**  \n═══════════\n🧠 **Decide:**  \n▔▔▔▔▔▔▔▔▔▔\n1. **Merge order**\n\n"
            "**Second topic**  \n════════════\n🧠 **Decide:**  \n▔▔▔▔▔▔▔▔▔▔\n2. **Retention**\n"
        )
        self.assertEqual(
            reply_turns.sections(text),
            (
                ("Decide", "🧠 **Decide:**  \n▔▔▔▔▔▔▔▔▔▔\n1. **Merge order**"),
                ("Decide", "🧠 **Decide:**  \n▔▔▔▔▔▔▔▔▔▔\n2. **Retention**"),
            ),
        )

    def test_a_header_is_matched_by_name_not_glyph(self) -> None:
        self.assertEqual(reply_turns.sections("🙃 **Todo:**  \n1. **x**")[0][0], "Todo")
        self.assertEqual(reply_turns.sections("🙃 **Nothing:**  \n1. **x**"), ())

    def test_open_reads_authorizations_first_of_the_lists_waiting_on_the_user(self) -> None:
        text = (
            "🔍 **Review:**  \n▔▔▔▔▔▔▔▔▔▔\n1. **#14 The README**\n\n"
            "🔑 **Authorizations:**  \n▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔\n1. **SSH signing prompt for the push**\n"
        )
        self.assertEqual(reply_turns.sections(text)[1][0], "Authorizations")
        turns = reply_turns.turns_of((prompt(FIRST, "go"), reply(text)))
        self.assertEqual(
            reply_turns.render_sections(turns, None, reply_turns.OPEN_SECTIONS),
            "== aaaa1111 ==\n"
            "🔑 **Authorizations:**  \n▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔\n1. **SSH signing prompt for the push**\n\n"
            "🔍 **Review:**  \n▔▔▔▔▔▔▔▔▔▔\n1. **#14 The README**",
        )

    def test_render_sections_gathers_named_sections_under_each_turn_id(self) -> None:
        turns = reply_turns.turns_of((prompt(FIRST, "go"), reply(REPLY), prompt(SECOND, "more"), reply("prose only")))
        self.assertEqual(
            reply_turns.render_sections(turns, None, reply_turns.DECISIONS),
            "== aaaa1111 ==\n🧠 **Decide:**  \n- **An old one**\n\n🧠 **Decisions:**  \n1. **Which cache**",
        )
        self.assertEqual(reply_turns.render_sections(turns, "bbbb", reply_turns.DECISIONS), "")


class CommandLineTest(unittest.TestCase):
    def run_main(self, *args: str) -> tuple[int, str, str]:
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "session.jsonl"
            path.write_text("\n".join(json.dumps(r) for r in RECORDS), encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                status = reply_turns.main(["--transcript", str(path), *args])
        return status, out.getvalue(), err.getvalue()

    def test_id_prints_the_current_turn(self) -> None:
        self.assertEqual(self.run_main("id")[:2], (0, "aaaa1199\n"))

    def test_list_prints_each_turn_s_first_prompt_line(self) -> None:
        status, out, _ = self.run_main("list", "-n", "2")
        self.assertEqual(
            (status, out.splitlines()),
            (0, ["bbbb2222  2026-11-16T10:00:00Z  <agent-message from x>", "aaaa1199  2026-11-16T10:00:00Z  <task-notification>"]),
        )
        self.assertEqual(self.run_main("list", "--grep", "FIRST")[1], "aaaa1111  2026-11-16T10:00:00Z  first prompt\n")

    def test_show_prints_the_prompt_then_the_reply(self) -> None:
        self.assertEqual(self.run_main("show", "aaaa1111")[1], "first prompt\nsecond line\n\n--- reply ---\n\none\n\ntwo\n")
        self.assertEqual(self.run_main("show", "aaaa1111", "--prompt-only")[1], "first prompt\nsecond line\n")

    def test_a_bad_id_exits_1_naming_it(self) -> None:
        status, out, err = self.run_main("show", "ffff")
        self.assertEqual((status, out), (1, ""))
        self.assertIn("'ffff' matches no turn", err)

    def test_a_missing_transcript_exits_1(self) -> None:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            status = reply_turns.main(["--transcript", "/nonexistent/x.jsonl", "id"])
        self.assertEqual(status, 1)
        self.assertIn("no transcript at /nonexistent/x.jsonl", err.getvalue())


if __name__ == "__main__":
    unittest.main()
