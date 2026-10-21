---
name: coding-agent-kanban-turn-responses
description: "Every response in a turn is kanban-shaped. A progress update between tool calls is one line whose state emoji show what is done, running and next. The final response is up to 8 underlined, numbered lists of what is new this turn, in a fixed order: Done, Open, Logged, Waiting, Questions answered, Review, Todo and Blocked, each numbered item's bold summary on its own line, then what earlier turns left open under 📌, in full on an interval and otherwise as one count line. Blocked items and their capital-lettered options each read alone, with pros and cons; an answer that asks a question is answered in its item, restated, never taken as a choice; multi-line items are parted by a separator line; `scripts/lint_reply.py` checks the summaries, separators, options and header underlines. `pending` reprints open decisions as written, `reassess` works them out afresh, and `Expand <item>` reprints one item in depth. Load at the start of every turn, before the first response the user will read."
---

# Kanban turn responses

_Every response in a turn shows what is done, what is still open and what the user must do: a one-line progress update between tool calls, and in the final response up to 8 lists in a fixed order, then what earlier turns left open, under 📌 in full or as one count line._

A project may extend this skill with a skill of its own, or with its preferences file ([Your preferences](#your-preferences)), adding its own backlog path or link rules; the project's wins where the two differ.

How a response renders in a terminal, its box tables, glyph widths, hard line breaks, separator lines and links, follows `markdown-hygiene-terminal-rendering`; this skill says only which of those a turn response uses and where.

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
| ❓ **Questions:**          | one item per question the user asked that names no listed item, the question as the summary, shortened or reworded where that reads better, the answer under it                                   | nobody           | no                                                 |
| 🔍 **Review:**             | one item per thing put in front of the user to read, listen to or look at, with where to open it and what to look for                                                                             | the user         | yes, until the user's reply shows they reviewed it |
| 👉 **Todo:**               | one item per action asked of the user that is neither a choice nor a reading: a file to mark up, a prompt to paste, a command to run; each says what to do, where, by its path, and what it frees | the user         | yes                                                |
| 🛑 **Blocked:**            | one item per decision raised, and per judgement call taken instead of asked, its reversal an option                                                                                               | the user         | yes                                                |

An empty list is left out, and the final response opens on a line of prose. An answer takes the shape its information has: a comparison is a table, a sequence is numbered steps, parallel items are a list.

**A list holds only what is new this turn.** An item an earlier turn printed, unchanged since, is not printed in its list again; it rolls up into 📌. An item whose state changed this turn, a Waiting agent that reported, a Todo item whose prompt is now ready or an item whose question was answered, is new again and is printed in its list with the change.

A review that is itself a choice goes in 🛑 Blocked, and a task that is not a reading goes in 👉 Todo.

## The shape

- **Header:** the header line ends in a hard line break. The line under it holds one `▔` U+2594 per column of the header, the emoji counting 2, so `🤔 **Waiting:**` takes 11. The first item follows on the next line.
- **Item:** a numbered item opens on its summary, in bold, alone on its line and ending in a hard line break; the rest of the item starts on the line beneath, at the column the summary starts at. The summary is a phrase, or the question for a Question or a Blocked item, with no trailing colon, since nothing follows it on its line. It names its subject, never its category, and the item to do first leads. A summary that says all there is, such as a check that passed, is the whole item. A bullet, such as a 📌 roll-up item, keeps its summary and text on one line. A Done item comes from the commit or the run output, never from memory. No item points back with a phrase like "the quotes" or "those episodes": each names what it means by its label, as `writing-hygiene-refer-by-canonical-label` says, since what set it up has scrolled away.
- **Numbering:** each list numbers from 1 and nothing else in the final response is numbered except an item's own steps, so `Blocked.2` names one thing. A second final response to the same prompt continues the numbering.
- **Separator:** in every list, the 📌 roll-up included, a multi-line item is parted from each neighbour by the separator line of `markdown-hygiene-terminal-rendering`: the list's indent, U+2800 `⠀`, and nothing else, directly under the item's last line, with no blank line beside it. Since a summary has its line to itself, every item with more than its summary is multi-line, every Blocked item among them. Items that are only their summary sit together, and the first item follows its header with no separator. `scripts/lint_reply.py` holds the character as `SEPARATOR`.

[examples.md](examples.md#a-blocked-list) draws a Blocked list in this shape. Before sending a final response, run `scripts/lint_reply.py` on the draft and fix every line it reports: a missing or misplaced separator, a whitespace line where one belongs, a blank line beside one, text after a numbered item's summary, a summary line with no hard line break, a list among a Blocked item's options, or a header underline of the wrong width.

## A Blocked item

- **Options:** they follow the item's summary and its note, recommended first, each on one line, as `glyph letter. **name**: consequence`. The letter is a capital, `A`, `B`, `C`, or `Y` and `N` for a yes-or-no question, never a number or a lower-case letter: an answer like `1.B` then cannot be misread, since the number always names the item and the capital the option, and a typo lands on no option instead of the wrong one. The AskUserQuestion picker, when it opens, lists the same options in the same order.
- **Pros and cons:** every option carries, indented under it, a ➕ line for what it gains and a ➖ line for what it costs; the recommended option's ➕ says why. ✅ and ❌ are kept for the Done header and the done and failed states, so a pro line never reads as finished work.
- **Notes:** a note on the whole item is the line under its summary, and a note on one option goes under that option, in plain lines at its ➕ and ➖ lines' indent. A note among the options is never a `-` or `1.` list: the option lines are plain lines of the item's paragraph, so a list there captures every line after it, the later options among them, and prints them at its own indent.
- **Each item and option stands alone.** Read with nothing above it, the summary names the thing decided and each option names what it acts on and what it does to it: the entry number and its title in a few words, the file, branch, table or step, the count. A label that only points back, "the 4 gate bugs", "the fix above", "part S", says what it points at in the same line, "entries 0819, 1375, 0988 and 1374, the stale-database and stale-render bugs".

| Glyph     | Kind                                                                         | Letters |
| --------- | ---------------------------------------------------------------------------- | ------- |
| 🔘        | radio: exactly one chosen, including a pair of courses answered with a label | A, B, C |
| 🔲        | checkbox: any number chosen, including none                                  | A, B, C |
| 👍 and 👎 | binary: one yes-or-no question, both lines written                           | Y and N |

## The user's answers

- **By reference:** the user names an item by its list and number, `Blocked.2`, an option by its letter, `Blocked.2: B` or `2. B`, and either by its name. An item of an earlier turn carries that turn's id, from its usage line, before or after: `0f311c94.Blocked.2` or `Blocked.2 of 0f311c94`; with no id, the last final response is meant. An answer to an item of a turn that `reassess` replaced is read against the reassessed item that took it in.
- **A question is never a choice.** An answer holding a question mark or any question, `Blocked.1?`, `B?`, "how would B work?", "why not C?", asks about the item and picks nothing, even when it names an option. Restate the item in its own list, whatever the list, with the answer as the note under its summary and its options rewritten where the answer changes them; the item stays open until the user answers it without a question. A question goes in ❓ Questions only when it names no listed item.
- **A Review item stays open until the user's reply shows they reviewed it:** they comment on it, answer from it, or say they looked; a reply that only answers something else leaves it open.

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

- **Turn ids and the scripts:** a turn id is the first 8 characters of the prompt's `promptId`, `0f311c94`, shown on the prompt's usage line. The scripts sit in this skill's `scripts/` directory and use only the Python standard library: [`reply_turns.py`](scripts/reply_turns.py) reads turns and their sections, [`outstanding.py`](scripts/outstanding.py) works out the roll-up's interval, items and tags, [`box_table.py`](scripts/box_table.py) draws a box table, and [`lint_reply.py`](scripts/lint_reply.py) checks a draft's separator, summary, option and underline lines; [scripts.md](scripts.md) lists their subcommands. Run them by their path under `~/.claude/skills/coding-agent-kanban-turn-responses/scripts/`.
- **Time:** say how long work takes, never when it lands or goes out, and set no deadline.
- **Tables:** a box table in a `text` block, as `markdown-hygiene-terminal-rendering` draws it; `scripts/box_table.py` draws one from tab-separated rows on stdin. A cell holding a state holds its emoji from the progress-update table, not a word.
- **Links:** every URL, a local served page as much as a web page, is a Markdown link opened by 🔗 and a space, `🔗 [the trial projection](http://127.0.0.1:8765/…)`, kept out of `text` blocks and box tables as `markdown-hygiene-terminal-rendering` says: a table's cell holds the label, and the link follows the table as a 🔗 line, or a list of them.
- **Glyphs:** the only ones in a response are the 8 header glyphs, `▔`, 📌, `━` and 🔖, the `·` between the count line's lists and a progress update's steps, the box-drawing lines, the 6 state emoji, the 4 option glyphs, ➕ and ➖ on a pro or con line, 🔗 before a link, and the separator character. A new one is width-checked as `markdown-hygiene-terminal-rendering` says before it is used.

## Why and how to apply

**Why:** the user reads a response once and acts on it. A fixed shape lets them see progress as it happens, find their questions, sort the rest by position and answer by reference. A list reprinted every turn is read every turn, so what has not changed rolls up out of the way, and between full roll-ups shrinks to one count line.

**How to apply:** read the user's answers first: a choice is acted on, and a question about an item is answered in that item, restated in its list. Between tool calls, write a one-line progress update when a step finishes or starts. In the final response, write this turn's new items in the non-empty lists, in the table's order, each header underlined, each numbered item's summary on a line of its own, and each multi-line item parted by a separator line. Then run `scripts/outstanding.py due`: on `full`, draft the roll-up with `scripts/outstanding.py render` and prune what is settled; on `counts`, close on the count line, `scripts/outstanding.py render --counts` corrected for what is settled. Last, run `scripts/lint_reply.py` on the whole draft and fix every line it reports before sending it.

## When to apply

Load this skill at the start of every turn, before the first response the user will read, and follow it for every response in the turn: each progress update and the final response.

## Your preferences

!`cat "${CLAUDE_SKILL_DIR}/../coding-agent-kanban-turn-responses.preferences.md" "${CLAUDE_PROJECT_DIR}/.agents/skills/coding-agent-kanban-turn-responses.preferences.md" 2>/dev/null || true`

If your agent doesn't run the line above, read these files yourself if they
exist: `coding-agent-kanban-turn-responses.preferences.md` next to this skill's folder, then
`.agents/skills/coding-agent-kanban-turn-responses.preferences.md` in the project. A project's
file overrides the user's, and the user's overrides this skill's defaults.

## Related skills

When one of these applies and it's in your skill listing, load it
without asking. If it isn't in your listing, tell the user which skill is
missing and ask whether to install it from the same collection this skill
came from; don't apply it from memory.

- `markdown-hygiene-terminal-rendering`: how box tables, glyph widths, hard line breaks, separator lines and links render in a terminal.
- `writing-hygiene-refer-by-canonical-label`: name each thing by one label every time, never pointing back with a vague phrase.
- `coding-agent-skill-references`: how a skill names other skills and reads its preferences files.
