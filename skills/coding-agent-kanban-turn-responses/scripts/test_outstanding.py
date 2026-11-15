#!/usr/bin/env python3
"""Tests for outstanding.py's open Decide items, run from anywhere: `python3 -I scripts/test_outstanding.py`.

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
                "options": [{"letter": "Y", "name": "Ship it"}, {"letter": "N", "name": "Hold it"}],
            },
        )

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

    def test_a_reassess_turn_replaces_every_earlier_item(self) -> None:
        later = DECIDE_REPLY.split("2. **")[0]
        refs = self.open_refs(prompt(FIRST, "go"), reply(DECIDE_REPLY), prompt(SECOND, "reassess", 1), reply(later, 1))
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
        self.assertEqual(found["items"][0]["options"][0], {"letter": "A", "name": "Keep the disk cache"})


if __name__ == "__main__":
    unittest.main()
