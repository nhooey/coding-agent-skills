# The transcript scripts

_What the scripts behind the [`coding-agent-kanban-turn-responses` skill](SKILL.md) read from the session's transcript, and the subcommands each takes._

Both read `~/.claude/projects/<slug>/<session>.jsonl`, the session from `CLAUDE_CODE_SESSION_ID`, overridden by `--session ID`, or the file itself by `--transcript FILE`. Run them by their path in this skill's `scripts/` directory.

## What a turn is

A turn opens on every prompt the user sees a usage line for: a typed prompt, an agent's report (`<agent-message`) and a task notification. Its reply is the text the session wrote up to the next such prompt. A turn id is the first 8 characters of the prompt's `promptId`, `0f311c94`, shown on the prompt's usage line; the user names a list by it, `Blocked.2 of 0f311c94`. Older replies used the last 6 characters of the prompt's uuid, `7c89a7`, and `find` still takes them. Both scripts read the headers earlier turns carry, `To do` beside `Todo`, and `Still open from earlier` beside `Outstanding from previous turns`.

## The `scripts/reply_turns.py` script

The one reader of turns and their reply sections.

| Subcommand                                 | Prints                                                                 |
| ------------------------------------------ | ---------------------------------------------------------------------- |
| `id`                                       | the current turn's id                                                  |
| `list [-n N] [--grep TEXT]`                | one line per turn, newest last: id, timestamp, the prompt's first line |
| `show ID [--prompt-only] [--section NAME]` | the turn's prompt and reply, or one section from every reply text      |
| `blocked [--since ID]`                     | each turn's Blocked section, from turn ID inclusive                    |
| `open [--since ID]`                        | each turn's Review, Todo and Blocked sections, under the turn id       |

The global `--human-only` flag counts a typed prompt alone as a turn, folding agent reports and task notifications into the turn under way.

It runs from any directory: the transcript is looked up under the working directory's project first, then in whichever one project directory holds the session's `<session>.jsonl`. Its tests run with `python3 -I scripts/test_reply_turns.py`, and `nix flake check` runs them too.

## The `outstanding.py` script

[`outstanding.py`](scripts/outstanding.py), in this skill's `scripts/` directory, works out what the 📌 roll-up needs. It reads the Open, Waiting, Review, Todo and Blocked lists of every reply, the 📌 section's groups among them, through `reply_turns.py`.

| Subcommand                                              | Prints                                                                                                                                           |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `due [--now ISO]`                                       | `full` or `counts <time left>`, then the roll-up interval and the last full roll-up behind it                                                    |
| `render [--last N] [--since ID] [--counts]`             | a draft of the full roll-up, each item ending in its 🔖 tag, by default over the last 20 turns; `--counts` prints the draft's count line instead |
| `index [ID...] [--last N]`                              | each turn's relative index, as `-3` and `₋₃`; with no id, the last N turns                                                                       |
| `items [--since ID] [--lists L] [--latest] [--width W]` | `id  ₋ₖ  list  summary`, one line per item                                                                                                       |
| `grep PATTERN [...]`                                    | the same lines for items whose line matches the regex, ignoring case                                                                             |

**What `due` measures.** The roll-up interval is min(30 min, 5 × the average duration of the last 5 completed turns, each from its prompt to the next), read as the 5 gaps between the last 6 prompts, the current turn's prompt closing the latest; under 2 prompts it is 30 min. The clock starts at the reply text that last printed the 📌 header with its `━` rule on the next line, by that text's own timestamp; a count line has no rule and never starts it. With no full roll-up in the transcript, `due` prints `full`.

**What `render` drafts.** The draft is a starting point and the session prunes it, since which items are still open is a judgement the script cannot make. It never reaches back before the latest `reassess` turn, whose lists replace every item before it; `items` and `grep` still read every turn. Each item carries the turn that raised it: the turn that first printed it, or the first turn of the latest run whose text after the bold summary is unchanged, so a restatement with changed substance moves the tag and a reworded summary alone does not. A restatement inside a 📌 section is a roll-up, and keeps the turn its own 🔖 tag names.

**How an item is matched across turns.** Within a list, 2 items are one when their subject keys match, so a reworded summary stays one item:

| The summary holds                                                        | Its key                                                                                                                                     |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `entry` or `entries` and a 3- or 4-digit number                          | `entry 1411`, the first number                                                                                                              |
| a code span shaped like a branch name, lowercase words joined by hyphens | `branch atomic-reload`, the first such span                                                                                                 |
| neither                                                                  | its first 3 words that are not articles or prepositions, lowercased: `landing alpha` for both _The landing of `alpha`_ and _Landing alpha!_ |

The key reads the summary alone, the bold text before its colon. Different items in one list that name the same branch or entry, or open on the same 3 words, merge in the draft, and the session splits them when it prunes.

## The `lint_reply.py` script

[`lint_reply.py`](scripts/lint_reply.py) reads no transcript: it checks a draft final response, on stdin or in the file named, for the separator lines and numbered items' summary lines the skill requires, and is run on every draft before it is sent. It prints `LINE: [k] message` per finding and exits 1 if there is any, else 0. Lines inside ``` or ~~~ fences are not read.

```text
python3 -I ~/.claude/skills/coding-agent-kanban-turn-responses/scripts/lint_reply.py draft.md
```

| Kind | Finding                                                                                           |
| ---- | ------------------------------------------------------------------------------------------------- |
| `a`  | a multi-line item followed by the next item of its list with no separator line                    |
| `b`  | a separator line between 2 one-line items, or right under a header's underline                    |
| `c`  | a line of only spaces, tabs or U+00A0, not empty, inside a list, where a separator line was meant |
| `d`  | a separator line whose indent is not its list's, the column its items' text starts at             |
| `e`  | a blank line directly above or below a separator line, which renders a double gap                 |
| `f`  | a numbered item with text after its bold summary on the same line                                 |
| `g`  | a numbered item's summary line with lines under it but no hard line break, 2 trailing spaces      |

A list is a run of `-`, `*`, `+`, `1.` or `1)` items at one indent, the 📌 roll-up's groups and an item's own steps among them, and a header or a line of prose at the item's indent ends it. Its tests run with `python3 -I scripts/test_lint_reply.py`, and `nix flake check` runs them too.
