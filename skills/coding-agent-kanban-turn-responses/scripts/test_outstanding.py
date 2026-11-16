#!/usr/bin/env python3
"""Tests for outstanding.py, run from anywhere: `python3 -I scripts/test_outstanding.py`.

Standard library only. The core is tested directly, on turns built from transcript records in memory;
one test runs the command line on a transcript file.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
from datetime import timedelta

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import outstanding  # noqa: E402
import reply_turns  # noqa: E402

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


def prompt(prompt_id: str, text: str, minute: int = 0) -> dict:
    return {
        "type": "user",
        "turnOrigin": "human",
        "promptId": prompt_id,
        "uuid": f"uuid-{prompt_id}",
        "timestamp": f"2026-11-16T10:{minute:02d}:00Z",
        "message": {"content": text},
    }


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

    def test_a_question_answers_nothing(self) -> None:
        refs = self.open_refs(prompt(FIRST, "go"), reply(DECIDE_REPLY), prompt(SECOND, "9efb08a1.Decide.1.B? how would B work", 1))
        self.assertIn("9efb08a1.Decide.1", refs)

    def test_a_restated_item_is_open_once_under_its_latest_turn(self) -> None:
        restated = DECIDE_REPLY.replace("1. **Which cache", "4. **Which cache")
        refs = self.open_refs(
            prompt(FIRST, "go"), reply(DECIDE_REPLY), prompt(SECOND, "more", 1), reply(restated.split("2. **")[0], 1)
        )
        self.assertEqual(refs, ["9efb08a1.Decide.2", "9efb08a1.Decide.3", "b2c3d4e5.Decide.4"])

    def test_a_recheck_turn_replaces_every_earlier_item(self) -> None:
        later = DECIDE_REPLY.split("2. **")[0]
        refs = self.open_refs(prompt(FIRST, "go"), reply(DECIDE_REPLY), prompt(SECOND, "recheck", 1), reply(later, 1))
        self.assertEqual(refs, ["b2c3d4e5.Decide.1"])

    def test_reassess_is_another_name_for_recheck(self) -> None:
        later = DECIDE_REPLY.split("2. **")[0]
        refs = self.open_refs(prompt(FIRST, "go"), reply(DECIDE_REPLY), prompt(SECOND, "reassess", 1), reply(later, 1))
        self.assertEqual(refs, ["b2c3d4e5.Decide.1"])

    def test_the_slash_command_form_of_recheck(self) -> None:
        later = DECIDE_REPLY.split("2. **")[0]
        refs = self.open_refs(
            prompt(FIRST, "go"),
            reply(DECIDE_REPLY),
            prompt(SECOND, "/coding-agent-kanban-turn-responses recheck", 1),
            reply(later, 1),
        )
        self.assertEqual(refs, ["b2c3d4e5.Decide.1"])


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

    def test_nothing_open_renders_nothing(self) -> None:
        self.assertEqual(self.render(prompt(FIRST, "go"), reply("Prose only.")), "")
        self.assertEqual(self.render(prompt(FIRST, "go"), reply("Prose only."), counts=True), "")


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
