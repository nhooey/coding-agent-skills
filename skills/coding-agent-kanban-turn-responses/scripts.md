# The transcript scripts

_What the scripts behind the [`coding-agent-kanban-turn-responses` skill](SKILL.md) read from the session's transcript, and the subcommands each takes._

Both read `~/.claude/projects/<slug>/<session>.jsonl`, the session from `CLAUDE_CODE_SESSION_ID`, overridden by `--session ID`, or the file itself by `--transcript FILE`. Run them by their path in this skill's `scripts/` directory. Their tests are in the coding-agent-skills repository, in `tests/coding-agent-kanban-turn-responses/`; `skills-dev test coding-agent-kanban-turn-responses` runs them in its dev shell, and `nix flake check` runs them too.

## What a turn is

A turn opens on every prompt the user sees a usage line for: a typed prompt, an agent's report (`<agent-message`) and a task notification. A `!` command's output, which the transcript keeps as a typed prompt opening on `<bash-stdout>` or `<bash-stderr>`, opens none, so an answer typed after it still answers the reply before it. A turn's reply is the text the session wrote up to the next such prompt, and the messages that reach the session while it runs belong to it: the user's own are its asides, and an agent's or a task's are its reports. A turn id is the first 8 characters of the prompt's `promptId`, `0f311c94`, shown on the prompt's usage line; the user names a list by it, `Decide.2 of 0f311c94`. Older replies used the last 6 characters of the prompt's uuid, `7c89a7`, and `find` still takes them. Both scripts read the headers earlier turns carry, `Unfinished` and `Open` beside `Pending`, `Questions` beside `Answers`, `To review` beside `Review`, `To do` beside `Todo`, `Decisions` and `Blocked` beside `Decide`, and `Still open from earlier` beside `Outstanding from previous turns`. A list's section ends at the next list header or at a topic header, the line above a `═` underline, so the lists of a reply grouped by topic are read one by one, each item by the number it was printed with.

## The `scripts/reply_turns.py` script

The one reader of turns and their reply sections.

| Subcommand                                 | Prints                                                                            |
| ------------------------------------------ | --------------------------------------------------------------------------------- |
| `id`                                       | the current turn's id                                                             |
| `list [-n N] [--grep TEXT]`                | one line per turn, newest last: id, timestamp, the prompt's first line            |
| `show ID [--prompt-only] [--section NAME]` | the turn's prompt and reply, or one section from every reply text                 |
| `decide [--since ID]`                      | each turn's Decide section, from turn ID inclusive; `decisions` and `blocked` too |
| `open [--since ID]`                        | each turn's Authorizations, Review, Todo and Decide sections, under the turn id   |

The global `--human-only` flag counts a typed prompt alone as a turn, folding agent reports and task notifications into the turn under way.

It runs from any directory: the transcript is looked up under the working directory's project first, then in whichever one project directory holds the session's `<session>.jsonl`.

## The `outstanding.py` script

[`outstanding.py`](scripts/outstanding.py), in this skill's `scripts/` directory, works out what the 📌 roll-up needs. It reads the Pending, Waiting, Authorizations, Review, Todo and Decide lists of every reply, the 📌 section's groups among them, through `reply_turns.py`.

| Subcommand                                              | Prints                                                                                                                                           |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `due [--now ISO]`                                       | `full` or `counts <time left>`, then the roll-up interval and the last full roll-up behind it                                                    |
| `render [--last N] [--since ID] [--counts]`             | a draft of the full roll-up, each item ending in its 🔖 tag, by default over the last 20 turns; `--counts` prints the draft's count line instead |
| `index [ID...] [--last N]`                              | each turn's relative index, as `-3` and `₋₃`; with no id, the last N turns                                                                       |
| `items [--since ID] [--lists L] [--latest] [--width W]` | `id  ₋ₖ  list  summary`, one line per item                                                                                                       |
| `grep PATTERN [...]`                                    | the same lines for items whose line matches the regex, ignoring case                                                                             |
| `decide [--json] [--width W]`                           | every open Decide item with its options, one line each; `--json` prints `{"items": [...]}`, for a tool to read                                   |

**What `due` measures.** The roll-up interval is min(30 min, 5 × the average duration of the last 5 completed turns, each from its prompt to the next), read as the 5 gaps between the last 6 prompts, the current turn's prompt closing the latest; under 2 prompts it is 30 min. The clock starts at the reply text that last printed the 📌 header with its `━` rule on the next line, by that text's own timestamp; a count line has no rule and never starts it. With no full roll-up in the transcript, `due` prints `full`.

**What a `reassess` turn is.** A turn whose prompt opens on `reassess`, `recheck`, `regenerate` or `recalculate`, or on a prefix of one of them that is a prefix of no other command's name, bare, after `/coding-agent-kanban-turn-responses`, or as that slash command's `<command-args>`. `pending`, `open`, `restate` and their own prefixes name `open`, so `re` names neither.

**What `render` drafts.** The draft is a starting point and the session prunes it, since which items are still open is mostly a judgement the script cannot make. It leaves out the items it can tell are settled:

- a Review item once every pull request it names with its repository, as a GitHub URL or `owner/repo#N`, has merged, asked of `gh api graphql` in one call; a bare `#N` is never looked up, and a `gh` that is missing, fails or takes over 20 seconds settles nothing;
- a Decide item once the user answers its latest restatement, read as `decide` reads answers;
- a Waiting item once a report names it in a turn after the last that printed it in its own list. A report is an agent's message or a cross-session message, or a task notification for a finished task or an expired Monitor, whether it opened the turn or came while the turn ran; it names the item where the item's summary holds the sending session's name, the agent's id, or the task's id or quoted name, or where the report holds a code span of the summary shaped like a branch name.

A 📌 roll-up's restatement of a settled item reopens nothing, so a roll-up copied from an earlier draft can't keep it alive. A summary cut to `--width` counts a Markdown link's label alone, and a cut inside a link shortens its label and keeps the link whole. It never reaches back before the latest `reassess` turn, whose lists replace every item before it; `items` and `grep` still read every turn. Each item carries the turn that raised it: the turn that first printed it, or the first turn of the latest run whose text after the bold summary is unchanged, so a restatement with changed substance moves the tag and a reworded summary alone does not. A restatement inside a 📌 section is a roll-up, and keeps the turn its own 🔖 tag names.

**How an item is matched across turns.** Within a list, 2 items are one when their subject keys match, so a reworded summary stays one item:

| The summary holds                                                        | Its key                                                                                                                                     |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `entry` or `entries` and a 3- or 4-digit number                          | `entry 1411`, the first number                                                                                                              |
| a code span shaped like a branch name, lowercase words joined by hyphens | `branch atomic-reload`, the first such span                                                                                                 |
| neither                                                                  | its first 3 words that are not articles or prepositions, lowercased: `landing alpha` for both _The landing of `alpha`_ and _Landing alpha!_ |

The key reads the summary alone, the bold text before its colon. Different items in one list that name the same branch or entry, or open on the same 3 words, merge in the draft, and the session splits them when it prunes.

**What `decide` counts as open.** A numbered item of a reply's own Decide list that carries at least one option line, read since the latest `reassess` turn, at its latest restatement by subject key, and answered by no later prompt the user typed and by no message the user sent while a later turn ran; an agent's report, a task notification or a mod's prompt answers nothing. An answer, on a line holding no question mark, is an option letter after the item's reference, `9efb08a1.Decide.2.B` with or without a note after it, `…Decide.2.B: <note>`, a turn-id prefix of 6 or more characters as good as the whole, `Decide.2: B,C of 9efb08a1`, or, in the prompt right after the reply, `Decide.2.B` or a line `2. B`, several on one line parted by `/`, `;` or `,`, `1. A / 3. B`; or words after a colon, `9efb08a1.Decide.2: <words>`. Letters after a colon or a space count as letters only where they end the line or another reference follows, so `Decide.2: A red one` is an answer in words, not option A. Each JSON item holds `turn`, `list` (`Decide`), `number`, `summary`, `kind` (`radio` or `checkbox`, from the option glyphs, or `binary` for an item with 👍 and 👎 options, which `lint_reply.py` reports but earlier turns may hold), `ref` (`<turn>.Decide.<n>`), `note` (the lines under its summary) and `options`, each `{letter, name, glyph, consequence, pros, cons, notes}`.

## The `lint_reply.py` script

[`lint_reply.py`](scripts/lint_reply.py) reads no transcript: it checks a draft final response, on stdin or in the file named, for the separator lines, numbered items' summary lines, Decide options, header underlines and table placement the skill requires, and is run on every draft before it is sent. It prints `LINE: [k] message` per finding and exits 1 if there is any, else 0. Lines inside ``` or ~~~ fences are not read.

```text
python3 -I ~/.claude/skills/coding-agent-kanban-turn-responses/scripts/lint_reply.py draft.md
```

| Kind | Finding                                                                                                                          |
| ---- | -------------------------------------------------------------------------------------------------------------------------------- |
| `a`  | a multi-line item followed by the next item of its list with no separator line                                                   |
| `b`  | a separator line between 2 one-line items, or right under a header's underline                                                   |
| `c`  | a line of only spaces, tabs or U+00A0, not empty, inside a list, where a separator line was meant                                |
| `d`  | a separator line whose indent is not its list's, the column its items' text starts at                                            |
| `e`  | a blank line directly above a separator line, or below one where the list goes on                                                |
| `f`  | a numbered item with text after its bold summary on the same line                                                                |
| `g`  | a numbered item's summary line with lines under it but no hard line break, 2 trailing spaces                                     |
| `h`  | a `-` or `1.` list line among a Decide item's options, after its first option line                                               |
| `i`  | a header underline, `▔`, `━` or a topic header's `═`, whose width is not the header's, its emoji counting 2 and `**` not counted |
| `j`  | a header or line of prose directly under a list, which Markdown reads as more of its last item                                   |
| `k`  | a table indented under a list item, which prints as raw pipe rows instead of a drawn table                                       |
| `l`  | a table with no blank line above it, or a line directly under its last row, drawn as one more row                                |
| `m`  | a list under a topic header that does not number on from where the same list ended in the topics before                          |
| `n`  | a Decide option with a 👍 or 👎 glyph, or lettered `Y` or `N`; a yes-or-no question is a 🔘 radio item with `A` and `B`          |

A list is a run of `-`, `*`, `+`, `1.` or `1)` items at one indent, the 📌 roll-up's groups and an item's own steps among them, and may start above 1 under a topic header. A blank line ends it; a header or a line of prose left of its items' text, written with no blank line before it, is a `j`.

## The `reply_lint_hook.py` script

[`reply_lint_hook.py`](scripts/reply_lint_hook.py) is the skill's Stop hook. The `coding-agent-skills-hooks` plugin runs it in every session through [`reply-lint-hook.sh`](scripts/reply-lint-hook.sh), with `lint_reply.py` and `reply_turns.py` copied in beside it. The shell script exits at once when the session's transcript never names the skill. The Python acts only when the transcript shows the skill loaded, by a Skill tool call naming it or its "Base directory for this skill:" line, so a session that never loaded the skill is never checked. It reads the hook's input on stdin and lints its `last_assistant_message`, or, where that is missing, the current turn's last reply text in `transcript_path`, read through `reply_turns.py`. It always exits 0.

| `Reply lint` | Findings in a response with a list header or a 📌 roll-up                                                                                                     |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `remind`     | printed as a `systemMessage`, shown to the user; the turn ends. The default                                                                                   |
| `block`      | `decision: "block"` with the findings as the `reason`, so the session writes the response again; when `stop_hook_active` is set, the turn ends as at `remind` |
| `off`        | nothing                                                                                                                                                       |

The setting is the last valid `Reply lint:` line in the user's preferences file, `~/.agents/skills/coding-agent-kanban-turn-responses.preferences.md`, then the project's, the same file under `.agents/skills/` in `CLAUDE_PROJECT_DIR` or the hook's `cwd`. A `block` reason or `systemMessage` reaches the session only through the hook's output: a Stop hook has no way to add text to the model's context without continuing the turn.
