#!/usr/bin/env python3
"""Tests for outstanding.py: `skills-dev test coding-agent-kanban-turn-responses`.

Standard library only. The core is tested directly, on turns built from transcript records in memory;
one test runs the command line on a transcript file.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
from datetime import timedelta
from unittest import mock

import outstanding
import reply_turns

SEP = "⠀"

DECIDE_REPLY = f"""Opening prose.

🧠 **Decide:**
▔▔▔▔▔▔▔▔▔▔
1. **Which cache to keep for the loader**
   A note on the whole item.
   🔘 A. **Keep the disk cache**: it survives restarts.
      ➕ Faster cold starts.
      ➖ Disk use.
   🔘 B. **Keep the memory cache**: simpler.
      ➕ Less code.
      ➖ Slow cold starts.
   {SEP}
2. **Backlog cleanups to start**
   Any of 3.
   🔲 A. **Entry 1411, the matchers made one**: one function.
      ➕ One behaviour.
      ➖ Tokens.
   🔲 B. **Entries 0550 and 0455, dead code**: delete it.
      ➕ Cheap.
      ➖ Tidiness only.
   🔲 C. **Entry 0988, the stale render**: fix it.
      ➕ Correct renders.
      ➖ Time.
   {SEP}
3. **Ship the release tonight?**
   👍 Y. **Ship it**: it goes out.
      ➕ Users get it.
      ➖ Risk.
   👎 N. **Hold it**: it waits.
      ➕ Safety.
      ➖ Delay.

📌 **Outstanding from previous turns:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧠 **Decide:**
- **An older decision** 🔖 0000aaaa₋₃
"""


GROUPED_REPLY = """Rechecked: 2 decisions open, in 2 topics.

**The atomic-reload database swap**
═══════════════════════════════
🧠 **Decide:**
▔▔▔▔▔▔▔▔▔▔
1. **Merge order for the swap**
   🔘 A. **Schema first**: a working base.
      ➕ Releasable.
      ➖ 3 reviews.
   🔘 B. **All at once**: one review.
      ➕ 1 review.
      ➖ One revert undoes all.

**The 2026 backup plan**
════════════════════
🧠 **Decide:**
▔▔▔▔▔▔▔▔▔▔
2. **Snapshot retention**
   🔘 A. **90 days**: a quarter.
      ➕ Audits.
      ➖ Storage.
   🔘 B. **30 days**: a month.
      ➕ Cheap.
      ➖ Short.
"""


def prompt(prompt_id: str, text: str, minute: int = 0, origin: str = "human", **extra: object) -> dict:
    return {
        "type": "user",
        "turnOrigin": origin,
        "promptId": prompt_id,
        "uuid": f"uuid-{prompt_id}",
        "timestamp": f"2026-11-16T10:{minute:02d}:00Z",
        "message": {"content": text},
        **extra,
    }


def queued(text: str, kind: str) -> dict:
    """A message that reached the session while a turn ran: the user's (`human`) or a report (`peer`, `task-notification`)."""
    return {"type": "attachment", "attachment": {"type": "queued_command", "prompt": text, "origin": {"kind": kind}}}


def shell_output(prompt_id: str, minute: int = 0) -> tuple[dict, dict]:
    """A `!` command the user ran: its input record, and its output, which the transcript keeps as a human prompt."""
    command = {"type": "user", "message": {"content": "<bash-input>git log</bash-input>"}}
    return command, prompt(prompt_id, "<bash-stdout>1234abc Fix</bash-stdout><bash-stderr></bash-stderr>", minute)


def reply(text: str, minute: int = 0) -> dict:
    return {
        "type": "assistant",
        "timestamp": f"2026-11-16T10:{minute:02d}:30Z",
        "message": {"content": [{"type": "text", "text": text}]},
    }


def turns(*records: dict) -> tuple[reply_turns.Turn, ...]:
    return outstanding.merge_repeats(reply_turns.turns_of(records))


FIRST = "9efb08a1-0000-4000-8000-000000000000"
SECOND = "b2c3d4e5-0000-4000-8000-000000000000"
THIRD = "c3d4e5f6-0000-4000-8000-000000000000"


class DecideItemsOfTextTest(unittest.TestCase):
    def setUp(self) -> None:
        self.items = outstanding.decide_items_of_text("9efb08a1", DECIDE_REPLY)

    def test_each_numbered_item_with_options_is_read(self) -> None:
        self.assertEqual([i.number for i in self.items], [1, 2, 3])

    def test_the_roll_up_bullets_are_not_items(self) -> None:
        self.assertNotIn("An older decision", [i.summary for i in self.items])

    def test_kinds_come_from_the_glyphs(self) -> None:
        self.assertEqual([i.kind for i in self.items], ["radio", "checkbox", "binary"])

    def test_options_carry_letter_and_name_without_the_colon(self) -> None:
        self.assertEqual(
            [(o.letter, o.name) for o in self.items[0].options],
            [("A", "Keep the disk cache"), ("B", "Keep the memory cache")],
        )

    def test_the_summary_keeps_its_question_mark(self) -> None:
        self.assertEqual(self.items[2].summary, "Ship the release tonight?")

    def test_the_reference_is_turn_list_and_number(self) -> None:
        self.assertEqual(self.items[1].ref, "9efb08a1.Decide.2")

    def test_the_json_shape(self) -> None:
        self.assertEqual(
            self.items[2].as_json(),
            {
                "turn": "9efb08a1",
                "list": "Decide",
                "number": 3,
                "summary": "Ship the release tonight?",
                "kind": "binary",
                "ref": "9efb08a1.Decide.3",
                "note": [],
                "options": [
                    {
                        "letter": "Y",
                        "name": "Ship it",
                        "glyph": "👍",
                        "consequence": "it goes out.",
                        "pros": ["Users get it."],
                        "cons": ["Risk."],
                        "notes": [],
                    },
                    {
                        "letter": "N",
                        "name": "Hold it",
                        "glyph": "👎",
                        "consequence": "it waits.",
                        "pros": ["Safety."],
                        "cons": ["Delay."],
                        "notes": [],
                    },
                ],
            },
        )

    def test_the_note_pros_and_cons_stop_at_the_item_and_list_ends(self) -> None:
        first, last = self.items[0], self.items[2]
        self.assertEqual(first.note, ("A note on the whole item.",))
        self.assertEqual(first.options[0].pros, ("Faster cold starts.",))
        self.assertEqual(first.options[1].cons, ("Slow cold starts.",))
        self.assertEqual(first.options[1].notes, ())
        self.assertEqual(last.options[1].notes, ())

    def test_an_item_without_options_is_left_out(self) -> None:
        text = "🧠 **Decide:**  \n▔▔▔▔▔▔▔▔▔▔\n1. **Something to think about**  \n   No options here.\n"
        self.assertEqual(outstanding.decide_items_of_text("9efb08a1", text), ())


class OpenDecideItemsTest(unittest.TestCase):
    def open_refs(self, *records: dict) -> list[str]:
        return [i.ref for i in outstanding.open_decide_items(turns(*records))]

    def test_every_item_of_the_last_reply_is_open(self) -> None:
        refs = self.open_refs(prompt(FIRST, "go"), reply(DECIDE_REPLY))
        self.assertEqual(refs, ["9efb08a1.Decide.1", "9efb08a1.Decide.2", "9efb08a1.Decide.3"])

    def test_an_answer_naming_the_turn_settles_its_item(self) -> None:
        refs = self.open_refs(
            prompt(FIRST, "go"), reply(DECIDE_REPLY), prompt(SECOND, "9efb08a.Decide.1.A 9efb08a1.Decide.2: A,C", 1)
        )
        self.assertEqual(refs, ["9efb08a1.Decide.3"])

    def test_an_answer_with_the_turn_after_it_settles_its_item(self) -> None:
        refs = self.open_refs(prompt(FIRST, "go"), reply(DECIDE_REPLY), prompt(SECOND, "Decide.3.N of 9efb08a1", 1))
        self.assertEqual(refs, ["9efb08a1.Decide.1", "9efb08a1.Decide.2"])

    def test_an_answer_naming_its_turn_after_it_settles_no_item_of_the_turn_before(self) -> None:
        for line in ("Decide.2: B of 9efb08a1", "Decide.2: B,C of 9efb08a1", "Decide.2.A, C from 9efb08a1"):
            with self.subTest(line=line):
                self.assertEqual(outstanding._answers_of_line(line, "b2c3d4e5"), frozenset({("9efb08a1", 2)}))

    def test_a_bare_answer_settles_the_turn_before_it(self) -> None:
        refs = self.open_refs(prompt(FIRST, "go"), reply(DECIDE_REPLY), prompt(SECOND, "Decide.1: B\n3. Y", 1))
        self.assertEqual(refs, ["9efb08a1.Decide.2"])

    def test_a_bare_answer_two_turns_later_settles_nothing_of_the_first(self) -> None:
        refs = self.open_refs(
            prompt(FIRST, "go"),
            reply(DECIDE_REPLY),
            prompt(SECOND, "something else", 1),
            reply("Done.", 1),
            prompt(THIRD, "Decide.1.A", 2),
        )
        self.assertEqual(refs, ["9efb08a1.Decide.1", "9efb08a1.Decide.2", "9efb08a1.Decide.3"])

    def test_an_answer_sent_while_a_turn_ran_settles_its_item(self) -> None:
        aside = {
            "type": "attachment",
            "attachment": {"type": "queued_command", "prompt": "Decide.2.B", "origin": {"kind": "human"}},
        }
        refs = self.open_refs(prompt(FIRST, "go"), reply(DECIDE_REPLY), prompt(SECOND, "something else", 1), aside)
        self.assertEqual(refs, ["9efb08a1.Decide.1", "9efb08a1.Decide.3"])

    def test_an_answer_in_words_settles_its_item_and_a_note_keeps_the_letters(self) -> None:
        refs = self.open_refs(
            prompt(FIRST, "go"),
            reply(DECIDE_REPLY),
            prompt(SECOND, "9efb08a1.Decide.1: A red one, please\n9efb08a1.Decide.3.N: not tonight", 1),
        )
        self.assertEqual(refs, ["9efb08a1.Decide.2"])

    def test_only_the_user_s_own_text_answers(self) -> None:
        answer = "9efb08a1.Decide.1.A"
        others = (
            prompt(SECOND, f'<agent-message from="a48bb">\n{answer}\n</agent-message>', 1, origin="peer"),
            prompt(SECOND, f"<task-notification>\n<summary>{answer}</summary>\n</task-notification>", 1, origin="task_notification"),
            prompt(SECOND, f"The mod sent:\n{answer}", 1, origin="system", pluginPrompt={"name": "mod", "text": answer}),
        )
        for other in others:
            with self.subTest(origin=other["turnOrigin"]):
                refs = self.open_refs(prompt(FIRST, "go"), reply(DECIDE_REPLY), other, queued(answer, "peer"))
                self.assertIn("9efb08a1.Decide.1", refs)

    def test_a_bare_answer_after_shell_output_settles_the_reply_before_it(self) -> None:
        refs = self.open_refs(prompt(FIRST, "go"), reply(DECIDE_REPLY), *shell_output(SECOND, 1), prompt(THIRD, "2. B", 2))
        self.assertEqual(refs, ["9efb08a1.Decide.1", "9efb08a1.Decide.3"])

    def test_a_reference_alone_answers_nothing(self) -> None:
        refs = self.open_refs(prompt(FIRST, "go"), reply(DECIDE_REPLY), prompt(SECOND, "see 9efb08a1.Decide.1 again", 1))
        self.assertIn("9efb08a1.Decide.1", refs)

    def test_a_question_answers_nothing(self) -> None:
        refs = self.open_refs(prompt(FIRST, "go"), reply(DECIDE_REPLY), prompt(SECOND, "9efb08a1.Decide.1.B? how would B work", 1))
        self.assertIn("9efb08a1.Decide.1", refs)

    def test_a_restated_item_is_open_once_under_its_latest_turn(self) -> None:
        restated = DECIDE_REPLY.replace("1. **Which cache", "4. **Which cache")
        refs = self.open_refs(
            prompt(FIRST, "go"), reply(DECIDE_REPLY), prompt(SECOND, "more", 1), reply(restated.split("2. **")[0], 1)
        )
        self.assertEqual(refs, ["9efb08a1.Decide.2", "9efb08a1.Decide.3", "b2c3d4e5.Decide.4"])

    def test_a_reassess_turn_replaces_every_earlier_item(self) -> None:
        later = DECIDE_REPLY.split("2. **")[0]
        for name in ("reassess", "recheck", "regenerate", "recalculate", "regen", "recalc", "reass"):
            with self.subTest(name=name):
                refs = self.open_refs(prompt(FIRST, "go"), reply(DECIDE_REPLY), prompt(SECOND, name, 1), reply(later, 1))
                self.assertEqual(refs, ["b2c3d4e5.Decide.1"])

    def test_the_slash_command_form_of_reassess(self) -> None:
        later = DECIDE_REPLY.split("2. **")[0]
        refs = self.open_refs(
            prompt(FIRST, "go"),
            reply(DECIDE_REPLY),
            prompt(SECOND, "/coding-agent-kanban-turn-responses recheck", 1),
            reply(later, 1),
        )
        self.assertEqual(refs, ["b2c3d4e5.Decide.1"])

    def test_an_open_turn_replaces_nothing(self) -> None:
        later = DECIDE_REPLY.split("2. **")[0].replace("1. **Which cache", "4. **Which cache")
        refs = self.open_refs(prompt(FIRST, "go"), reply(DECIDE_REPLY), prompt(SECOND, "restate", 1), reply(later, 1))
        self.assertEqual(refs, ["9efb08a1.Decide.2", "9efb08a1.Decide.3", "b2c3d4e5.Decide.4"])

    def test_a_reassess_grouped_by_topic_numbers_on_across_topics(self) -> None:
        refs = self.open_refs(prompt(FIRST, "go"), reply(DECIDE_REPLY), prompt(SECOND, "reassess", 1), reply(GROUPED_REPLY, 1))
        self.assertEqual(refs, ["b2c3d4e5.Decide.1", "b2c3d4e5.Decide.2"])
        answered = self.open_refs(
            prompt(FIRST, "go"),
            reply(DECIDE_REPLY),
            prompt(SECOND, "reassess", 1),
            reply(GROUPED_REPLY, 1),
            prompt(THIRD, "Decide.2: B", 2),
        )
        self.assertEqual(answered, ["b2c3d4e5.Decide.1"])

    def test_a_grouped_reply_keeps_each_item_its_own_number(self) -> None:
        items = outstanding.decide_items_of_text("b2c3d4e5", GROUPED_REPLY)
        self.assertEqual([(i.number, i.summary) for i in items], [(1, "Merge order for the swap"), (2, "Snapshot retention")])

    def test_a_topic_header_is_no_part_of_the_item_above(self) -> None:
        text = "**First topic**  \n═══════════\n👉 **Todo:**  \n▔▔▔▔▔▔▔▔\n1. **Run the benchmark**\n\n**Second topic**  \n════════════\n"
        self.assertEqual(outstanding.items_of_text(text), (("todo", False, "**Run the benchmark**"),))


class CommandOfTest(unittest.TestCase):
    def test_each_name(self) -> None:
        for name, command in (
            *((n, "reassess") for n in ("reassess", "recheck", "regenerate", "recalculate")),
            *((n, "open") for n in ("open", "pending", "restate")),
        ):
            with self.subTest(name=name):
                self.assertEqual(outstanding.command_of(name), command)

    def test_a_prefix_no_other_command_shares(self) -> None:
        for prefix, command in (
            ("rea", "reassess"),
            ("rec", "reassess"),
            ("regen", "reassess"),
            ("recalc", "reassess"),
            ("reass", "reassess"),
            ("res", "open"),
            ("rest", "open"),
            ("pend", "open"),
            ("o", "open"),
        ):
            with self.subTest(prefix=prefix):
                self.assertEqual(outstanding.command_of(prefix), command)

    def test_a_prefix_shared_with_another_command_names_none(self) -> None:
        for prefix in ("r", "re", "RE"):
            with self.subTest(prefix=prefix):
                self.assertIsNone(outstanding.command_of(prefix))

    def test_a_word_that_is_no_prefix_names_none(self) -> None:
        for prompt_text in ("recall the plan", "reading list", "go", "", "opener", "regen2"):
            with self.subTest(prompt=prompt_text):
                self.assertIsNone(outstanding.command_of(prompt_text))

    def test_the_first_word_decides_case_and_trailing_punctuation_aside(self) -> None:
        self.assertEqual(outstanding.command_of("  Reassess, then stop"), "reassess")
        self.assertEqual(outstanding.command_of("restate."), "open")

    def test_the_slash_command_typed(self) -> None:
        self.assertEqual(outstanding.command_of("/coding-agent-kanban-turn-responses regen"), "reassess")
        self.assertEqual(outstanding.command_of("/coding-agent-kanban-turn-responses restate"), "open")
        self.assertIsNone(outstanding.command_of("/coding-agent-kanban-turn-responses re"))
        self.assertIsNone(outstanding.command_of("/other-skill reassess"))

    def test_the_command_name_form(self) -> None:
        def sent(name: str, args: str) -> str:
            return f"<command-message>{name}</command-message>\n<command-name>/{name}</command-name>\n<command-args>{args}</command-args>"

        self.assertEqual(outstanding.command_of(sent("coding-agent-kanban-turn-responses", "recalc")), "reassess")
        self.assertEqual(outstanding.command_of(sent("coding-agent-kanban-turn-responses", "pending")), "open")
        self.assertIsNone(outstanding.command_of(sent("coding-agent-kanban-turn-responses", "re")))
        self.assertIsNone(outstanding.command_of(sent("other-skill", "reassess")))


class CommandLineTest(unittest.TestCase):
    def test_decide_json_reads_the_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "session.jsonl"
            records = (prompt(FIRST, "go"), reply(DECIDE_REPLY), prompt(SECOND, "9efb08a1.Decide.2.B", 1))
            path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                status = outstanding.main(["--transcript", str(path), "decide", "--json"])
        self.assertEqual(status, 0)
        found = json.loads(out.getvalue())
        self.assertEqual([i["ref"] for i in found["items"]], ["9efb08a1.Decide.1", "9efb08a1.Decide.3"])
        self.assertEqual(
            {k: found["items"][0]["options"][0][k] for k in ("letter", "name", "glyph")},
            {"letter": "A", "name": "Keep the disk cache", "glyph": "🔘"},
        )


RULE = "━" * 35


class SubjectKeyTest(unittest.TestCase):
    def test_a_backlog_entry_is_its_key(self) -> None:
        self.assertEqual(outstanding.subject_key("Entries 0550 and 0455, dead code"), "entry 0550")

    def test_else_a_branch_shaped_code_span(self) -> None:
        self.assertEqual(outstanding.subject_key("Merge `README.md` and `atomic-reload` today"), "branch atomic-reload")

    def test_else_the_first_three_words_that_are_not_articles_or_prepositions(self) -> None:
        self.assertEqual(outstanding.subject_key("Ship the release to users tonight?"), "ship release users")
        self.assertEqual(
            outstanding.subject_key("Ship the release to users"), outstanding.subject_key("Ship release, users first")
        )


ITEMS_REPLY = f"""Prose.

🚧 **Pending:**  
▔▔▔▔▔▔▔▔▔▔▔
1. **Rework the loader**  
   It still reads twice.
   {SEP}
2. **Another one**: with its text beside it

✅ **Done:**  
1. **Not an item of any rolled-up list**

📌 **Outstanding from previous turns:**  
{RULE}
👉 **Todo:**  
- **Paste the prompt** 🔖 b2c3d4e5₋₁
"""


class ItemsOfTextTest(unittest.TestCase):
    def test_items_of_the_rolled_up_lists_and_the_pin_section(self) -> None:
        self.assertEqual(
            outstanding.items_of_text(ITEMS_REPLY),
            (
                ("pending", False, "**Rework the loader** It still reads twice."),
                ("pending", False, "**Another one**: with its text beside it"),
                ("todo", True, "**Paste the prompt** 🔖 b2c3d4e5₋₁"),
            ),
        )

    def test_an_item_s_summary_and_body(self) -> None:
        item = outstanding.Item("x", 0, "pending", "🔖 c3d4e5f6₋₂: **Another one**: with its text beside it")
        self.assertEqual((item.summary, item.body), ("Another one", ": with its text beside it"))

    def test_the_roll_up_s_tag_becomes_the_item_s_origin(self) -> None:
        found = outstanding.all_items(turns(prompt(FIRST, "go"), reply(ITEMS_REPLY)))
        self.assertEqual([(i.line, i.pinned, i.origin_id) for i in found if i.list_key == "todo"],
                         [("**Paste the prompt**", True, "b2c3d4e5")])


def pending(summary: str, body: str) -> str:
    return f"🚧 **Pending:**  \n▔▔▔▔▔▔▔▔▔▔▔\n1. **{summary}** {body}\n"


class RenderTest(unittest.TestCase):
    def render(self, *records: dict, counts: bool = False) -> str:
        args = outstanding.parser().parse_args(["render", *(["--counts"] if counts else [])])
        return outstanding.run(args, turns(*records))

    def records(self, third_body: str) -> tuple[dict, ...]:
        return (
            prompt(FIRST, "go"),
            reply(pending("Rework the loader", "It reads twice.")),
            prompt(SECOND, "more", 1),
            reply(pending("Rework the loader", "It reads twice.") + "\n👉 **Todo:**  \n1. **Paste the prompt** now.\n", 1),
            prompt(THIRD, "more", 2),
            reply(
                pending("Rework the loader", third_body)
                + f"\n📌 **Outstanding from previous turns:**  \n{RULE}\n👉 **Todo:**  \n- **Paste the prompt** 🔖 b2c3d4e5₋₁\n",
                2,
            ),
        )

    def test_an_item_restated_unchanged_keeps_the_turn_that_raised_it(self) -> None:
        self.assertEqual(
            self.render(*self.records("It reads twice.")),
            f"📌 **Outstanding from previous turns:**  \n{RULE}\n"
            "🚧 **Pending:**  \n- **Rework the loader** 🔖 9efb08a1₋₂\n"
            "\n"
            "👉 **Todo:**  \n- **Paste the prompt** 🔖 b2c3d4e5₋₁",
        )

    def test_an_item_restated_with_changed_substance_takes_the_restating_turn(self) -> None:
        self.assertIn("- **Rework the loader** 🔖 c3d4e5f6₀", self.render(*self.records("It reads three times.")))

    def test_counts_is_one_line_in_the_skill_s_order(self) -> None:
        self.assertEqual(self.render(*self.records("It reads twice."), counts=True), "📌 Outstanding: 🚧 1 · 👉 1")

    def test_render_starts_at_the_latest_recheck_turn(self) -> None:
        out = self.render(
            prompt(FIRST, "go"),
            reply(pending("Dropped by the recheck", "x")),
            prompt(SECOND, "recheck", 1),
            reply(pending("Rework the loader", "y"), 1),
        )
        self.assertNotIn("Dropped", out)
        self.assertIn("- **Rework the loader** 🔖 b2c3d4e5₀", out)

    def test_waiting_items_render_under_the_hourglass_header(self) -> None:
        waiting = "⏳ **Waiting:**  \n▔▔▔▔▔▔▔▔▔▔▔\n1. **The test run** in the background.\n"
        records = (prompt(FIRST, "go"), reply(waiting), prompt(SECOND, "more", 1), reply("Prose.", 1))
        self.assertIn("⏳ **Waiting:**  \n- **The test run** 🔖 9efb08a1₋₁", self.render(*records))
        self.assertEqual(self.render(*records, counts=True), "📌 Outstanding: ⏳ 1")

    def test_an_older_reply_s_thinking_face_waiting_header_still_parses(self) -> None:
        old = "🤔 **Waiting:**  \n▔▔▔▔▔▔▔▔▔▔▔\n1. **The test run** in the background.\n"
        records = (prompt(FIRST, "go"), reply(old), prompt(SECOND, "more", 1), reply("Prose.", 1))
        self.assertIn("⏳ **Waiting:**  \n- **The test run** 🔖 9efb08a1₋₁", self.render(*records))
        self.assertEqual(self.render(*records, counts=True), "📌 Outstanding: ⏳ 1")

    def test_authorization_items_render_under_the_key_header_between_waiting_and_review(self) -> None:
        text = (
            "⏳ **Waiting:**  \n▔▔▔▔▔▔▔▔▔▔▔\n1. **The test run**\n\n"
            "🔑 **Authorizations:**  \n▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔\n"
            "1. **1Password prompt for the merge token**  \n"
            "   - #12 Fix the loader\n"
            "   - #13 Bump the lock\n"
            f"   {SEP}\n\n"
            "🔍 **Review:**  \n▔▔▔▔▔▔▔▔▔▔\n1. **#14 The README**\n"
        )
        records = (prompt(FIRST, "go"), reply(text), prompt(SECOND, "more", 1), reply("Prose.", 1))
        self.assertIn(
            "⏳ **Waiting:**  \n- **The test run** 🔖 9efb08a1₋₁\n\n"
            "🔑 **Authorizations:**  \n- **1Password prompt for the merge token** 🔖 9efb08a1₋₁\n\n"
            "🔍 **Review:**  \n",
            self.render(*records),
        )
        self.assertEqual(self.render(*records, counts=True), "📌 Outstanding: ⏳ 1 · 🔑 1 · 🔍 1")

    def test_two_grants_of_one_kind_led_by_what_they_unblock_stay_two_items(self) -> None:
        def grant(summary: str) -> str:
            return f"🔑 **Authorizations:**  \n▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔\n1. **{summary}**\n"

        records = (
            prompt(FIRST, "go"),
            reply(grant("The `v2.4.0` tag's SSH signature")),
            prompt(SECOND, "more", 1),
            reply(grant("The `v2.5.0` tag's SSH signature"), 1),
            prompt(THIRD, "more", 2),
            reply("Prose.", 2),
        )
        self.assertEqual(self.render(*records, counts=True), "📌 Outstanding: 🔑 2")

    def test_the_authorizations_list_is_one_to_pick(self) -> None:
        self.assertEqual(outstanding.parse_lists("authorizations,todo"), ("authorizations", "todo"))

    def test_nothing_open_renders_nothing(self) -> None:
        self.assertEqual(self.render(prompt(FIRST, "go"), reply("Prose only.")), "")
        self.assertEqual(self.render(prompt(FIRST, "go"), reply("Prose only."), counts=True), "")


FOURTH = "d4e5f6a7-0000-4000-8000-000000000000"
REVIEW_REPLY = (
    "🔍 **Review:**  \n▔▔▔▔▔▔▔▔▔▔\n"
    "1. **🔗 [#21 Close the pane](https://github.com/nhooey/kanban/pull/21)**\n"
    "2. **nhooey/kanban#22 Bump the lock**, on top of nhooey/kanban#21\n"
    "3. **#23 The README**\n"
)


def waiting(summary: str) -> str:
    return f"⏳ **Waiting:**  \n▔▔▔▔▔▔▔▔▔▔▔\n1. **{summary}**\n"


def task_notification(task_id: str, status: str, summary: str) -> str:
    return (
        f"<task-notification>\n<task-id>{task_id}</task-id>\n<status>{status}</status>\n"
        f"<summary>{summary}</summary>\n</task-notification>"
    )


def render_with(*records: dict, merged: frozenset[str] = frozenset(), counts: bool = False) -> str:
    args = outstanding.parser().parse_args(["render", *(["--counts"] if counts else [])])
    return outstanding.run(args, turns(*records), merged=lambda refs: merged & refs)


class SettledReviewTest(unittest.TestCase):
    def records(self) -> tuple[dict, ...]:
        return (prompt(FIRST, "go"), reply(REVIEW_REPLY), prompt(SECOND, "more", 1), reply("Prose.", 1))

    def test_the_pull_requests_an_item_names(self) -> None:
        refs = outstanding.pull_requests_of(REVIEW_REPLY)
        self.assertEqual(refs, frozenset({"nhooey/kanban#21", "nhooey/kanban#22"}))

    def test_a_merged_pull_request_settles_its_review_item(self) -> None:
        out = render_with(*self.records(), merged=frozenset({"nhooey/kanban#21"}))
        self.assertNotIn("Close the pane", out)
        # #22 names #21 too, but #22 itself is open; #23 names no repository, so nothing settles it
        self.assertIn("nhooey/kanban#22 Bump the lock", out)
        self.assertIn("#23 The README", out)

    def test_an_item_settles_once_every_pull_request_it_names_has_merged(self) -> None:
        both = frozenset({"nhooey/kanban#21", "nhooey/kanban#22"})
        self.assertEqual(render_with(*self.records(), merged=both, counts=True), "📌 Outstanding: 🔍 1")

    def test_no_merged_pull_request_keeps_every_item(self) -> None:
        self.assertEqual(render_with(*self.records(), counts=True), "📌 Outstanding: 🔍 3")

    def test_the_graphql_response_names_the_merged_ones(self) -> None:
        ordered = ("nhooey/kanban#21", "nhooey/kanban#22", "nhooey/kanban#24")
        response = json.dumps(
            {"data": {"pr0": {"pullRequest": {"state": "MERGED"}}, "pr1": {"pullRequest": {"state": "OPEN"}}, "pr2": None}}
        )
        self.assertEqual(outstanding.merged_of_response(ordered, response), frozenset({"nhooey/kanban#21"}))
        for broken in ("", "not json", "[]", '{"data": null}'):
            with self.subTest(response=broken):
                self.assertEqual(outstanding.merged_of_response(ordered, broken), frozenset())


class SettledReviewCommandLineTest(unittest.TestCase):
    """`render` asks `gh` which pull requests merged, and keeps every Review item when `gh` fails or is missing."""

    def render(self, gh: str | None) -> tuple[int, str, str]:
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            path = root / "session.jsonl"
            records = (prompt(FIRST, "go"), reply(REVIEW_REPLY), prompt(SECOND, "more", 1), reply("Prose.", 1))
            path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
            bin_dir = root / "bin"
            bin_dir.mkdir()
            calls = root / "calls"
            if gh is not None:
                stub = bin_dir / "gh"
                stub.write_text(
                    f"#!{sys.executable}\nimport sys\n"
                    f"open({str(calls)!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n{gh}\n",
                    encoding="utf-8",
                )
                stub.chmod(0o755)
            out = io.StringIO()
            with mock.patch.dict(os.environ, {"PATH": str(bin_dir)}), contextlib.redirect_stdout(out):
                status = outstanding.main(["--transcript", str(path), "render", "--counts"])
            return status, out.getvalue().strip(), calls.read_text(encoding="utf-8") if calls.exists() else ""

    def test_the_merged_pull_request_gh_reports_settles_its_item(self) -> None:
        response = {"data": {"pr0": {"pullRequest": {"state": "MERGED"}}, "pr1": {"pullRequest": {"state": "OPEN"}}}}
        status, out, calls = self.render(f"print({json.dumps(json.dumps(response))})")
        self.assertEqual((status, out), (0, "📌 Outstanding: 🔍 2"))
        self.assertIn("api graphql", calls)
        self.assertIn('owner: "nhooey", name: "kanban") { pullRequest(number: 21)', calls)

    def test_a_failing_gh_keeps_every_item(self) -> None:
        self.assertEqual(self.render("sys.exit(1)")[:2], (0, "📌 Outstanding: 🔍 3"))

    def test_a_missing_gh_keeps_every_item(self) -> None:
        self.assertEqual(self.render(None)[:2], (0, "📌 Outstanding: 🔍 3"))


class SettledDecideTest(unittest.TestCase):
    def test_numbered_answers_on_one_line(self) -> None:
        for line in ("1. A / 3. Y", "1. A; 3. Y", "1. A, 3. Y", "1.A/3.Y"):
            with self.subTest(line=line):
                self.assertEqual(
                    outstanding._answers_of_line(line, "9efb08a1"), frozenset({("9efb08a1", 1), ("9efb08a1", 3)})
                )
        self.assertEqual(outstanding._answers_of_line("2. A, C", "9efb08a1"), frozenset({("9efb08a1", 2)}))
        self.assertEqual(outstanding._answers_of_line("1. A / 3. Y?", "9efb08a1"), frozenset())

    def test_an_answered_decide_item_leaves_the_draft(self) -> None:
        for answer in ("9efb08a1.Decide.1.A", "Decide.1: B", "1. A", "1. A / 3. Y"):
            with self.subTest(answer=answer):
                records = (prompt(FIRST, "go"), reply(DECIDE_REPLY), prompt(SECOND, answer, 1), reply("Prose.", 1))
                out = render_with(*records)
                self.assertNotIn("Which cache to keep", out)
                self.assertIn("Backlog cleanups to start", out)

    def test_answers_to_items_1_and_3_leave_item_2(self) -> None:
        records = (prompt(FIRST, "go"), reply(DECIDE_REPLY), prompt(SECOND, "1. A / 3. Y", 1), reply("Prose.", 1))
        # the 📌 roll-up's "An older decision" was never answered
        self.assertEqual(render_with(*records, counts=True), "📌 Outstanding: 🧠 2")

    def test_an_answer_holding_a_question_leaves_its_item_open(self) -> None:
        records = (prompt(FIRST, "go"), reply(DECIDE_REPLY), prompt(SECOND, "1. B? how would B work", 1), reply("Prose.", 1))
        self.assertIn("Which cache to keep", render_with(*records))

    def test_a_roll_up_restating_an_answered_item_does_not_reopen_it(self) -> None:
        roll_up = (
            f"Prose.\n\n📌 **Outstanding from previous turns:**  \n{RULE}\n🧠 **Decide:**  \n"
            "- **Which cache to keep for the loader** 🔖 9efb08a1₋₁\n"
        )
        records = (prompt(FIRST, "go"), reply(DECIDE_REPLY), prompt(SECOND, "Decide.1: A", 1), reply(roll_up, 1))
        self.assertNotIn("Which cache to keep", render_with(*records))


class SettledWaitingTest(unittest.TestCase):
    def test_a_completed_task_notification_naming_the_task_settles_its_item(self) -> None:
        records = (
            prompt(FIRST, "go"),
            reply(waiting("Watcher on #143 (`b8a83gfv0`)") + "\n" + pending("Rework the loader", "x")),
            prompt(SECOND, task_notification("b8a83gfv0", "completed", 'Background command "watch" completed'), 1),
            reply("Prose.", 1),
        )
        self.assertEqual(render_with(*records, counts=True), "📌 Outstanding: 🚧 1")

    def test_an_agent_report_naming_the_item_s_branch_settles_it(self) -> None:
        report = '<agent-message from="a48bb9142825233bb">\n  Pushed branch outstanding-settled-items at 1234abc.\n</agent-message>'
        records = (
            prompt(FIRST, "go"),
            reply(waiting("The implementer, on branch `outstanding-settled-items`")),
            prompt(SECOND, report, 1),
            reply("Prose.", 1),
        )
        self.assertEqual(render_with(*records), "")

    def test_a_message_from_the_session_the_item_names_settles_it(self) -> None:
        message = (
            '<cross-session-message from="uds:/tmp/x.sock" from-name="github-config" from-mode="prompting">\n'
            "Done.\n</cross-session-message>"
        )
        records = (prompt(FIRST, "go"), reply(waiting("github-config: the two fixes")), prompt(SECOND, message, 1), reply("Prose.", 1))
        self.assertEqual(render_with(*records), "")

    def test_a_report_naming_something_else_settles_nothing(self) -> None:
        message = (
            '<cross-session-message from="uds:/tmp/x.sock" from-name="MyNixOS" from-mode="prompting">\n'
            "FYI.\n</cross-session-message>"
        )
        records = (prompt(FIRST, "go"), reply(waiting("github-config: the two fixes")), prompt(SECOND, message, 1), reply("Prose.", 1))
        self.assertEqual(render_with(*records, counts=True), "📌 Outstanding: ⏳ 1")

    def test_a_report_sent_while_a_turn_ran_settles_its_item(self) -> None:
        reports = (
            queued(task_notification("b8a83gfv0", "completed", 'Background command "watch" completed'), "task-notification"),
            queued('<agent-message from="b8a83gfv0">\n  Pushed.\n</agent-message>', "peer"),
        )
        for report in reports:
            with self.subTest(kind=report["attachment"]["origin"]["kind"]):
                records = (
                    prompt(FIRST, "go"),
                    reply(waiting("Watcher on #143 (`b8a83gfv0`)")),
                    prompt(SECOND, "more", 1),
                    report,
                    reply("Prose.", 1),
                )
                self.assertEqual(render_with(*records), "")

    def test_a_task_still_running_settles_nothing(self) -> None:
        for note in (
            task_notification("b8a83gfv0", "completed", 'Agent "x" is waiting on its own background work'),
            "<task-notification>\n<task-id>b8a83gfv0</task-id>\n<summary>Monitor event</summary>\n"
            "<event>CHECK ok</event>\n</task-notification>",
        ):
            with self.subTest(note=note):
                records = (prompt(FIRST, "go"), reply(waiting("Watcher (`b8a83gfv0`)")), prompt(SECOND, note, 1), reply("Prose.", 1))
                self.assertEqual(render_with(*records, counts=True), "📌 Outstanding: ⏳ 1")

    def test_an_item_its_own_list_restates_after_the_report_stays_open(self) -> None:
        records = (
            prompt(FIRST, "go"),
            reply(waiting("Watcher (`b8a83gfv0`)")),
            prompt(SECOND, task_notification("b8a83gfv0", "completed", "done"), 1),
            reply(waiting("Watcher (`b8a83gfv0`)") + "   Re-armed.\n", 1),
            prompt(THIRD, "more", 2),
            reply("Prose.", 2),
        )
        self.assertEqual(render_with(*records, counts=True), "📌 Outstanding: ⏳ 1")

    def test_a_roll_up_restating_it_after_the_report_does_not_reopen_it(self) -> None:
        roll_up = (
            f"Prose.\n\n📌 **Outstanding from previous turns:**  \n{RULE}\n⏳ **Waiting:**  \n"
            "- **Watcher (`b8a83gfv0`)** 🔖 9efb08a1₋₂\n"
        )
        records = (
            prompt(FIRST, "go"),
            reply(waiting("Watcher (`b8a83gfv0`)")),
            prompt(SECOND, task_notification("b8a83gfv0", "failed", "gone"), 1),
            reply("Prose.", 1),
            prompt(THIRD, "more", 2),
            reply(roll_up, 2),
            prompt(FOURTH, "more", 3),
        )
        self.assertEqual(render_with(*records), "")


class CutTest(unittest.TestCase):
    # 45 columns as shown: the label is 34, `🔗 ` 2 and ` and more` 9
    LINKED = "🔗 [#21 Close the pane and split nodes](https://github.com/nhooey/kanban/pull/21) and more"

    def test_a_cut_inside_a_link_keeps_the_link_and_shortens_its_label(self) -> None:
        self.assertEqual(outstanding._cut(self.LINKED, 20), "🔗 [#21 Close the pan…](https://github.com/nhooey/kanban/pull/21)")

    def test_the_width_counts_a_link_s_label_alone(self) -> None:
        self.assertEqual(outstanding._cut(self.LINKED, 45), self.LINKED)
        self.assertEqual(outstanding._cut(self.LINKED, 44), self.LINKED[:-2] + "…")

    def test_a_cut_right_after_a_link_puts_the_ellipsis_outside_it(self) -> None:
        self.assertEqual(outstanding._cut(self.LINKED, 37), self.LINKED.split(")")[0] + ")…")

    def test_text_without_a_link_cuts_as_before(self) -> None:
        self.assertEqual(outstanding._cut("abcdefgh", 5), "abcd…")
        self.assertEqual(outstanding._cut("abcdefgh", 8), "abcdefgh")
        self.assertEqual(outstanding._cut("a [b] (c) [d]", 5), "a [b…")

    def test_render_never_leaves_a_broken_link(self) -> None:
        records = (prompt(FIRST, "go"), reply(REVIEW_REPLY.replace("Close the pane", "Close the pane " + "x" * 120)))
        self.assertRegex(
            render_with(*records), r"- \*\*🔗 \[#21 Close the pane x+…\]\(https://github\.com/nhooey/kanban/pull/21\)\*\* 🔖"
        )


FULL = f"Done.\n\n📌 **Outstanding from previous turns:**  \n{RULE}\n🚧 **Pending:**  \n- **x** 🔖 9efb08a1₋₁\n"


class DueTest(unittest.TestCase):
    def test_the_interval_is_five_times_the_average_gap(self) -> None:
        found = turns(prompt(FIRST, "a", 0), prompt(SECOND, "b", 1), prompt(THIRD, "c", 3))
        self.assertEqual(outstanding.interval(found), timedelta(minutes=7, seconds=30))

    def test_the_interval_is_capped_at_30_minutes_and_is_30_without_a_gap(self) -> None:
        self.assertEqual(outstanding.interval(turns(prompt(FIRST, "a", 0), prompt(SECOND, "b", 10))), timedelta(minutes=30))
        self.assertEqual(outstanding.interval(turns(prompt(FIRST, "a"))), timedelta(minutes=30))

    def test_the_interval_reads_only_the_last_six_prompts(self) -> None:
        ids = [f"{n:08x}-0000-4000-8000-000000000000" for n in range(7)]
        minutes = [0, 50, 51, 52, 53, 54, 55]
        found = turns(*(prompt(i, "p", m) for i, m in zip(ids, minutes)))
        self.assertEqual(outstanding.interval(found), timedelta(minutes=5))

    def test_only_the_header_with_its_rule_is_a_full_roll_up(self) -> None:
        self.assertTrue(outstanding.prints_full(FULL))
        self.assertFalse(outstanding.prints_full("📌 Outstanding: 🚧 1"))
        self.assertFalse(outstanding.prints_full("📌 **Outstanding from previous turns:**  \nno rule"))

    def due(self, now: str) -> str:
        found = turns(
            prompt(FIRST, "a", 0),
            reply("go", 0),
            prompt(SECOND, "b", 1),
            reply(FULL, 1),
            prompt(THIRD, "c", 2),
            reply("Done.\n\n📌 Outstanding: 🚧 1", 2),
        )
        return outstanding.render_due(found, outstanding.instant(now))

    def test_counts_until_the_interval_has_passed_since_the_last_full_roll_up(self) -> None:
        self.assertEqual(
            self.due("2026-11-16T10:03:30Z"),
            "counts 3min  interval 5min, last full roll-up 2min ago in b2c3d4e5",
        )

    def test_full_once_it_has_and_a_count_line_does_not_reset_the_clock(self) -> None:
        self.assertEqual(
            self.due("2026-11-16T10:07:30Z"),
            "full  interval 5min, last full roll-up 6min ago in b2c3d4e5",
        )

    def test_full_when_no_reply_has_printed_one(self) -> None:
        found = turns(prompt(FIRST, "a", 0), reply("go", 0))
        self.assertEqual(
            outstanding.render_due(found, outstanding.instant("2026-11-16T10:00:40Z")),
            "full  interval 30min, no full roll-up yet",
        )

    def test_duration_units(self) -> None:
        cases = {timedelta(seconds=-5): "0sec", timedelta(seconds=45): "45sec", timedelta(seconds=60): "1min", timedelta(minutes=12): "12min",
                 timedelta(minutes=65): "1h 5min"}
        for span, text in cases.items():
            with self.subTest(span=span):
                self.assertEqual(outstanding.duration(span), text)


class TurnsTest(unittest.TestCase):
    def test_a_repeated_prompt_record_folds_its_replies_into_the_first(self) -> None:
        found = turns(prompt(FIRST, "go"), reply("one"), prompt(SECOND, "x", 1), reply("two", 1),
                      prompt(FIRST, "go"), reply("three", 2))
        self.assertEqual([(t.id, t.replies) for t in found], [("9efb08a1", ("one", "three")), ("b2c3d4e5", ("two",))])

    def test_index_and_its_subscript_count_back_from_the_current_turn(self) -> None:
        found = turns(prompt(FIRST, "a"), prompt(SECOND, "b"), prompt(THIRD, "c"))
        self.assertEqual([outstanding.index_of(found, t) for t in found], [-2, -1, 0])
        self.assertEqual((outstanding.subscript(-12), outstanding.subscript(0)), ("₋₁₂", "₀"))


if __name__ == "__main__":
    unittest.main()
