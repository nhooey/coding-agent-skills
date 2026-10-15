---
name: coding-agent-kanban-turn-responses
description: "Every response in a turn is kanban-shaped. A progress update between tool calls is one line whose state emoji show what is done, running and next. The final response is up to 8 underlined, numbered lists of what is new this turn, in a fixed order: Done, Open, Logged, Waiting, the user's Questions answered, Review, Todo and Blocked. Whatever earlier turns left open closes it under 📌: in full, grouped by the same lists, once min(30 min, 5 × the average duration of the last 5 completed turns) has passed since the last full roll-up, and otherwise as one count line. Each Todo item is an action of the user's with its path and what it frees; each Blocked item and option names what it acts on so it reads alone, with lettered options and their pros and cons; multi-line items are parted by a U+00A0 line. `pending` reprints the open decisions as they were written; `reassess` works them out afresh; `Expand <item>` reprints one item at the depth its list needs to act on it. Load at the start of every turn, before the first response the user will read."
---

# Kanban turn responses

_Every response in a turn shows what is done, what is still open and what the user must do: a one-line progress update between tool calls, and in the final response up to 8 lists in a fixed order, then what earlier turns left open, under 📌 in full or as one count line._

A project may extend this skill with a skill of its own, adding its own backlog path, link rules or rulings; the project's skill wins where the two differ.

## Progress updates

A progress update is any text the agent writes between tool calls before the final response. It is one line, written only when something has changed: a step finished, a step started, or the plan changed. Each step it names opens on its state emoji, the steps parted by a space, `·` and a space, finished first:

```text
✅ the waiver clauses read · 🏃 checking the 2020 resolutions · 💤 the limitation sections
```

| Emoji | State                                        |
| ----- | -------------------------------------------- |
| ✅    | done                                         |
| 🏃    | running                                      |
| ⏳    | waiting on other work                        |
| 👀    | waiting on the user                          |
| 💤    | not started, nothing in its way              |
| ❌    | failed or abandoned, with why in a few words |

A step names its subject, never its category: "the 2020 resolutions", not "the documents". A progress update carries no lists, no 📌 roll-up and no decisions; anything that needs the user waits for the final response, unless the work cannot go on without it.

## The final response's lists

| Header, written exactly so | Holds, from this turn only                                                                                                                                                                        | Waits on         | Rolls up into 📌                                   |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------- | -------------------------------------------------- |
| ✅ **Done:**               | one item per change, with its file and commit; a clean check, with what it checked and the count                                                                                                  | nobody           | no                                                 |
| 🚧 **Open:**               | work started and not finished, scope left out, a hold that will not announce itself when it lifts                                                                                                 | the agent        | yes                                                |
| 📝 **Logged:**             | one item per entry written into the project's backlog, by index and title                                                                                                                         | the next agent   | no                                                 |
| 🤔 **Waiting:**            | a background shell, subagent, hand-off or expected message, and what the session does with its result                                                                                             | the thing itself | yes                                                |
| ❓ **Questions:**          | one item per question the user asked, the question as the summary, shortened or reworded where that reads better, the answer under it                                                             | nobody           | no                                                 |
| 🔍 **Review:**             | one item per thing put in front of the user to read, listen to or look at, with where to open it and what to look for                                                                             | the user         | yes, until the user's reply shows they reviewed it |
| 👉 **Todo:**               | one item per action asked of the user that is neither a choice nor a reading: a file to mark up, a prompt to paste, a command to run; each says what to do, where, by its path, and what it frees | the user         | yes                                                |
| 🛑 **Blocked:**            | one item per decision raised, and per judgement call taken instead of asked, its reversal an option                                                                                               | the user         | yes                                                |

An empty list is left out, and the final response opens on a line of prose. An answer takes the shape its information has: a comparison is a table, a sequence is numbered steps, parallel items are a list.

**A list holds only what is new this turn.** An item an earlier turn printed, unchanged since, is not printed in its list again; it rolls up into 📌. An item whose state changed this turn, a Waiting agent that reported or a Todo item whose prompt is now ready, is new again and is printed in its list with the change.

**A Review item stays open until the user's reply shows they reviewed it:** they comment on it, answer from it, or say they looked; a reply that only answers something else leaves it open. A review that is itself a choice goes in 🛑 Blocked, and a task that is not a reading goes in 👉 Todo.

## The shape

- **Header:** the header line ends in a hard line break, 2 trailing spaces. The line under it holds one `▔` U+2594 per column of the header, the emoji counting 2, so `🤔 **Waiting:**` takes 11. The first item follows on the next line.
- **Item:** `**Short summary:** sentence`, the summary naming its subject, never its category, the item to do first leading. A Done item comes from the commit or the run output, never from memory. No item points back with a phrase like "the quotes" or "those episodes": each names what it means, since what set it up has scrolled away.
- **Numbering:** each list numbers from 1 and nothing else in the final response is numbered except an item's own steps, so `Blocked.2` names one thing. A second final response to the same prompt continues the numbering.
- **Separator:** in every list, the 📌 roll-up included, a multi-line item, every Blocked item among them, is parted from each neighbour by a line holding the list's indent, then one U+00A0 (non-breaking space), and nothing else. Some terminal renderers drop an empty line, and a line of ordinary spaces is an empty line to them, so the separator must hold the U+00A0 itself. One-line items in a run of one-line items sit together, and the first item follows its header with no separator.

[examples.md](examples.md#a-blocked-list) draws a Blocked list with its separators.

## A Blocked item

- **Options:** they follow the item, recommended first, as `glyph letter. **name**: consequence`. The letter is a capital, `A`, `B`, `C`, or `Y` and `N` for a yes-or-no question, never a number or a lower-case letter: an answer like `1.B` then cannot be misread, since the number always names the item and the capital the option, and a typo lands on no option instead of the wrong one. The user answers by item and letter, `Blocked.1: B`, or by name; the AskUserQuestion picker, when it opens, lists the same options in the same order.
- **Pros and cons:** every option carries, indented under it, a ➕ line for what it gains and a ➖ line for what it costs; the recommended option's ➕ says why. ✅ and ❌ are kept for the Done header and the done and failed states, so a pro line never reads as finished work.
- **Notes:** a note on the whole item goes under its summary, and a note on one option under that option.
- **Each item and option stands alone.** Read with nothing above it, the summary names the thing decided and each option names what it acts on and what it does to it: the entry number and its title in a few words, the file, branch, table or step, the count. A label that only points back, "the 4 gate bugs", "the fix above", "part S", says what it points at in the same line, "entries 0819, 1375, 0988 and 1374, the stale-database and stale-render bugs".

| Glyph     | Kind                                                                         | Letters |
| --------- | ---------------------------------------------------------------------------- | ------- |
| 🔘        | radio: exactly one chosen, including a pair of courses answered with a label | A, B, C |
| 🔲        | checkbox: any number chosen, including none                                  | A, B, C |
| 👍 and 👎 | binary: one yes-or-no question, both lines written                           | Y and N |

## Earlier turns' items

The final response closes, before any ETA line, on what earlier turns left open and no later turn settled: every 🚧 Open, 🤔 Waiting, 🔍 Review, 👉 Todo and 🛑 Blocked item. It prints in full or as one count line, by the roll-up interval.

**The roll-up interval.** The full roll-up prints once min(30 min, 5 × the average duration of the last 5 completed turns) has passed since the last final response that printed it in full; otherwise the final response closes on one count line.

- A prompt is any turn the user sees a usage line for, an agent's report and a task notification included.
- A turn's duration runs from its prompt to the next turn's prompt, so it covers the final response and the user's reading, and only a turn the next prompt has closed is completed.
- A final response that printed the count line does not restart the clock, and a session with no full roll-up yet prints it in full.

`scripts/outstanding.py due` prints `full`, or `counts` with the time until the full roll-up is due.

**The count line** names each list by its glyph and count, in the lists' order, Open, Waiting, Review, Todo, Blocked, each list left out when empty: `📌 Outstanding: 🚧 4 · 🤔 2 · 🔍 2 · 👉 1 · 🛑 5`. `scripts/outstanding.py render --counts` drafts it.

**The full roll-up** has the header `📌 **Outstanding from previous turns:**`, underlined with `━` U+2501, one per column, 35 in all, so the heavier rule sets it apart from this turn's lists. Under it the items are grouped by the list they came from, each group under that list's own header, in the lists' order and with no underline. Each item is one bullet, never numbered, naming its subject in a line and never reprinting its options, and ends with its 🔖 tag. `scripts/outstanding.py render` drafts it, and the session prunes what is settled. [examples.md](examples.md#the-full-roll-up) draws one.

**The 🔖 tag** is `🔖`, a space, the turn id as plain text, and the relative index in Unicode subscript right beside it, `🔖 0f311c94₋₃`. Only a 📌 item carries it; the other lists print neither the turn id nor the index.

- **The turn id** is the first 8 characters of the `promptId` of the turn whose final response first printed the item; where an item was restated with changed substance, it is the turn that restated it.
- **The relative index** is that turn's position counting back from the current turn, 0, every turn the user sees a usage line for counted. It prints as `₋` U+208B then the digits `₀`-`₉` U+2080 to U+2089: `₋₁₇` is 17 turns back.

**Nothing open, nothing printed.** With nothing open the final response has neither the full roll-up nor the count line. A reassessing turn prints neither, since its lists replace every earlier turn's.

## The commands

| The user writes                                                   | The final response                                                        |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------- |
| `pending`, or `/coding-agent-kanban-turn-responses pending`       | reprints the open 🔍, 👉 and 🛑 items of earlier turns as written         |
| `reassess`, or `/coding-agent-kanban-turn-responses reassess`     | works out afresh which are still open, and prints them in their own lists |
| `Expand <list>.<n>[.<letter>]`, or an item from 📌 by its subject | reprints that item or option at the depth its list needs                  |

Read [commands.md](commands.md) before running any of them, and put their output into the 🔍 Review, 👉 Todo and 🛑 Blocked lists, never ❓ Questions.

## Around the lists

- **Turn ids and the scripts:** a turn id is the first 8 characters of the prompt's `promptId`, `0f311c94`, shown on the prompt's usage line; the user names a list by it, `Blocked.2 of 0f311c94`. The scripts sit in this skill's `scripts/` directory and use only the Python standard library: [`reply_turns.py`](scripts/reply_turns.py) reads turns and their sections, [`outstanding.py`](scripts/outstanding.py) works out the roll-up's interval, items and tags, and [`box_table.py`](scripts/box_table.py) draws a box table; [scripts.md](scripts.md) lists their subcommands. Run them by their path under `~/.claude/skills/coding-agent-kanban-turn-responses/scripts/`.
- **Time:** say how long work takes, never when it lands or goes out, and set no deadline.
- **Tables:** drawn in a `text` block with box-drawing lines, `─ │ ┌ ┬ ┐ ├ ┼ ┤ └ ┴ ┘`, which join without the gaps a Markdown table's dashes leave. Each column is padded to its widest cell, an emoji counting 2; `scripts/box_table.py` does it from tab-separated rows on stdin. A cell holding a state holds its emoji from the progress-update table, not a word.
- **Links:** every URL, a local served page as much as a web page, is a Markdown link opened by 🔗 and a space, `🔗 [the trial projection](http://127.0.0.1:8765/…)`, which most terminals make clickable. A bare URL is never printed, and a URL never goes inside a `text` block or a box table, where it cannot be clicked: the table's cell holds the label, and the link follows the table as a 🔗 line, or a list of them. Text the user copies, a command or a prompt, stays in its `text` block.
- **Glyphs:** the only ones in a response are the 8 header glyphs, `▔`, 📌, `━` and 🔖, the `·` between the count line's lists and a progress update's steps, the box-drawing lines, the 6 state emoji, the 4 option glyphs, ➕ and ➖ on a pro or con line, and 🔗 before a link. Each was checked to render at a width of 2 columns in JetBrains' JediTerm; a new one is checked the same way before it is used, since a glyph the terminal draws at the wrong width breaks every table it sits in.

## Rulings

| Ruling                    | The user's words                                                                                                                                                                      | What it set                                                                                                                                                                                                                                           |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-09-28                | "Output aggregated blocked that still apply"                                                                                                                                          | `pending`, the word, and its reprint as written                                                                                                                                                                                                       |
| 2026-10-04                |                                                                                                                                                                                       | ❓ for questions and 🛑 for Blocked; every header underlined with `▔`, chosen over the macron by eye; gapless table borders; emoji in place of state words; 🏃 for running in place of 🔄; 👉 **Todo** for what the user must do that is not a choice |
| 2026-10-04                | "put enough information inline each blocked item and each option, so it can be identified"                                                                                            | each Blocked item and option stands alone                                                                                                                                                                                                             |
| 2026-10-04 and 2026-10-05 | "use the NBSP to separate any multiline items in any category"                                                                                                                        | the U+00A0 separator; a reply that typed spaces there ran 2 multi-line Todo items together                                                                                                                                                            |
| 2026-10-05                | "Sort like this always: {Done, Waiting, Questions, Todo, Blocked}"                                                                                                                    | the lists' order, with Open and Logged kept beside Done and 🔍 Review before Todo                                                                                                                                                                     |
| 2026-10-05                | 🔍 To review: "keep track of them until it's clear that I've reviewed them"                                                                                                           | a Review item stays open until the user's reply shows they reviewed it                                                                                                                                                                                |
| 2026-10-05                | "Roll up every category in to `Still open...`, so each turn only the new stuff is printed in its main category."                                                                      | each list holds only what is new this turn                                                                                                                                                                                                            |
| 2026-10-05                | "denoted by some emoji and a thicker high underline, and … grouped by type"                                                                                                           | the full roll-up                                                                                                                                                                                                                                      |
| 2026-10-05                | "Make URLs clickable and denoted by a link emoji"                                                                                                                                     | the 🔗 link                                                                                                                                                                                                                                           |
| 2026-10-05                | "Work it in to the skill and refactor"                                                                                                                                                | the roll-up interval and the count line between full roll-ups; across 15 replies the full roll-up had been 51% of reply text                                                                                                                          |
| 2026-10-05                | "When I say 'Expand' for a particular item or its children (options, ...), give me enough-detail that I need to act on it, which depends on the heading that it's under."             | `Expand`                                                                                                                                                                                                                                              |
| 2026-10-13                | "What are some better emojis for pros/cons?", answered "1. A"                                                                                                                         | ➕ and ➖ on pro and con lines, in place of ✅ and ❌, which already meant Done and failed                                                                                                                                                            |
| 2026-10-13                | "Change "To review" to "Review""                                                                                                                                                      | the 🔍 header reads **Review**; the scripts still read "To review" in earlier turns                                                                                                                                                                   |
| 2026-10-13                | "Update the kanban response skill to use capital letters for the options (or Y/N if binary). The intent is to prevent typos or misunderstandings from being interpreted incorrectly." | options lettered with capitals, never numbered; replies had drifted to `1.`, `2.` options, so an answer like `1.1` named item and option with the same kind of mark                                                                                   |
| 2026-10-13                | "Perhaps this skill should also affect all turn responses? Using emojis so you can see as things are getting done, in the intermediate responses"                                     | the progress updates, and the skill's move out of one project into `~/.claude/skills` as `coding-agent-kanban-turn-responses`                                                                                                                         |

**Why:** the user reads a response once and acts on it. A fixed shape lets them see progress as it happens, find their questions, sort the rest by position and answer by reference. A list reprinted every turn is read every turn, so what has not changed rolls up out of the way, and between full roll-ups shrinks to one count line.

**How to apply:** between tool calls, write a one-line progress update when a step finishes or starts. In the final response, write this turn's new items in the non-empty lists, in the table's order, each header underlined and each multi-line item parted by a U+00A0 line. Then run `scripts/outstanding.py due`: on `full`, draft the roll-up with `scripts/outstanding.py render` and prune what is settled; on `counts`, close on the count line, `scripts/outstanding.py render --counts` corrected for what is settled.
