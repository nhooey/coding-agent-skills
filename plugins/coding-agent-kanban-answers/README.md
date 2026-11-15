# coding-agent-kanban-answers

A Claude Code mod that makes the Decide items of the [`coding-agent-kanban-turn-responses` skill](../../skills/coding-agent-kanban-turn-responses/SKILL.md) clickable. A click writes the answer's reference, such as `9efb08a1.Decide.2.B`, into the prompt draft and never sends it, so you can pick several answers, add words of your own and press Enter when you're ready.

## Install

At the prompt of a terminal session:

```text
/plugin install coding-agent-kanban-answers --marketplace nhooey/coding-agent-skills
```

Answer `y` to add the marketplace, then choose a scope. From a shell:

```bash
claude plugin install coding-agent-kanban-answers --marketplace nhooey/coding-agent-skills
```

The mod reads the open items with the skill's `scripts/outstanding.py`, so the skill has to be installed too. It looks for the script in this order:

1. beside the mod in this repository, `skills/coding-agent-kanban-turn-responses/scripts/outstanding.py`, when the mod runs from a checkout (`claude --plugin-dir plugins/coding-agent-kanban-answers`, or a folder marketplace);
2. the project's `.claude/skills/coding-agent-kanban-turn-responses/`;
3. `~/.claude/skills/coding-agent-kanban-turn-responses/`.

It runs `python3` from your `PATH`.

## What it draws

### The band above the prompt

The band shows one open Decide item at a time:

```text
🧠 2/5 · Which cache to keep for the loader
[ A. Keep the disk cache ] [ B. Keep the memory cache ]
[ ◀ Prev ] [ Skip ] [ Next ▶ ] [ Recheck ] [ ✕ ]  ● [○] ○ ○ ○
```

| Control         | What it does                                                                                                                         |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| an option       | writes `<turn>.Decide.<n>.<letter>` into the draft, replacing the item's earlier answer there, and moves to the next unanswered item |
| a checkbox item | toggles its letter in one reference, `…Decide.3.A,C`, and stays on the item so you can pick more; `Next ▶` or `Skip` moves on        |
| `Skip`          | goes to the next item the draft doesn't answer                                                                                       |
| `◀ Prev`        | goes to the previous item, wrapping round                                                                                            |
| `Next ▶`        | goes to the next item, wrapping round                                                                                                |
| `Recheck`       | submits the skill's `recheck` command, which works the open items out afresh; the one button that sends a prompt                     |
| `✕`             | hides the band until a reply raises a Decide item it hasn't shown, or until you run `/answers`                                       |

The marks after the buttons show which items the draft answers, `●` answered and `○` not, the shown item in brackets. The option the draft picks is drawn as the primary button. The band refreshes when a reply finishes.

Once the band holds the keys (ctrl+x tab, or a click on it), each option's letter presses it, and `h`, `j`, `l` and `q` press `◀ Prev`, `Skip`, `Next ▶` and `✕`. An option whose letter is one of those four has no hotkey.

### `/answers`

Shows the band again after `✕`, at the first item the draft doesn't answer, and re-reads the open items.

There is no hotkey to bring the band back: the mod API binds a Button's `hotkey` or `action` only while the Button is drawn, and a dismissed band draws nothing.

### Buttons in the transcript

The mod registers the tool `kanban_options`, listed as `mcp__coding-agent-kanban-answers__kanban_options`. The skill tells the agent to call it with the turn's Decide items right before writing its final response, so the tool's row, with a row of option buttons per item, sits just above the reply. Its buttons write the draft as the band's do. Once a refresh finds an item no longer open, its row is dimmed, marked `(settled)`, and its buttons do nothing.

## Where the items come from

The mod never parses Markdown. It runs `outstanding.py --session <id> decide --json`, which lists each open Decide item as:

```json
{
  "turn": "9efb08a1",
  "list": "Decide",
  "number": 2,
  "summary": "Backlog cleanups to start",
  "kind": "checkbox",
  "ref": "9efb08a1.Decide.2",
  "options": [{ "letter": "A", "name": "Entry 1411, the matchers made one" }]
}
```

under `{"items": [...]}`. The `kanban_options` tool takes the same object. The skill's [scripts.md](../../skills/coding-agent-kanban-turn-responses/scripts.md) says what counts as open.

## Developing

From the repository's dev shell:

```bash
check-kanban-answers-mod
```

It runs [`scripts/check.sh`](scripts/check.sh): `claude plugin validate`, `tsc -p` and `claude plugin test`. `tsc` needs the Claude Code API declarations in `.claude-plugin/types/`, which the engine lays there when it loads the mod from a folder it watches; where none has, the script copies the running build's from the files its `plugin-authoring` skill wrote. To try the mod without installing it:

```bash
claude --plugin-dir plugins/coding-agent-kanban-answers
```

| File                                       | Holds                                                                               |
| ------------------------------------------ | ----------------------------------------------------------------------------------- |
| [`hooks/register.tsx`](hooks/register.tsx) | the hooks: the band, the tool and its row, `/answers`, the refresh after each reply |
| [`hooks/answers.ts`](hooks/answers.ts)     | the pure core: how a click changes the draft and how the band moves                 |
| [`types/index.d.ts`](types/index.d.ts)     | the item shape and the `$.state` contract                                           |
| [`tests/`](tests/)                         | the core's tests, and the band and tool row driven through the engine               |
