# coding-agent-kanban-turn-responses

A skill that makes every response from a coding agent look like a kanban board.
Between tool calls you get a one-line progress update. The final response sorts
the turn's results into fixed lists, so you can scan it once, see what is done,
and answer each decision by its number.

## Why

A long agent turn usually ends in paragraphs of prose. The one decision that
needs you is buried somewhere in them, and so is the command you are meant to
run. Once it scrolls away, it is gone. This skill fixes that:

- **Progress you can watch.** Each step carries a state emoji (✅ done, 🏃
  running, 💤 not started, ❌ failed), so a glance shows where the turn is.
- **The same order every time.** ✅ Done, 🚧 Open, 📝 Logged, 🤔 Waiting, ❓
  Questions, 🔍 Review, 👉 Todo, 🛑 Blocked. Each list holds only what is new
  this turn, and empty lists are left out.
- **Decisions you answer by reference.** Each Blocked item names the thing it
  decides, offers lettered options with the recommended one first, and gives
  each option a ➕ pro and a ➖ con. You can reply `Blocked.1: B`.
- **Nothing gets lost.** Open items from earlier turns roll up under 📌, either
  as one count line or, at an interval, as a full list grouped by kind.

## Example

A progress update between tool calls:

```text
✅ the failing test reproduced · 🏃 bisecting the parser change · 💤 the fix
```

The final response:

```text
The parser regression came from the tokenizer rewrite; the fix is committed.

✅ **Done:**
▔▔▔▔▔▔▔▔
1. **Tokenizer fix:** `src/lexer.rs` stops splitting `::` inside generics; commit `a1b2c3d`.
2. **Test suite:** 412 passed, 0 failed.

🛑 **Blocked:**
▔▔▔▔▔▔▔▔▔▔▔
1. **Whether to backport the `src/lexer.rs` tokenizer fix to the 2.x branch:**
   🔘 A. **Cherry-pick commit a1b2c3d onto 2.x**: one commit, CI reruns.
      ➕ 2.x users get the fix in the next patch release.
      ➖ 2.x has its own lexer tests, which may need updating.
   🔘 B. **Leave 2.x as it is**
      ➕ No work now.
      ➖ The `::` bug stays in 2.x.

📌 Outstanding: 🔍 1 · 👉 2
```

## Use

Install it with the repo's flake, either alone or with the other skills:

```bash
nix run github:nhooey/coding-agent-skills#install
```

Then tell the agent to load it every turn. In Claude Code, add this to
`~/.claude/CLAUDE.md`:

```markdown
At the start of every turn, as the main agent, load the
`coding-agent-kanban-turn-responses` skill and follow it for every response in
the turn.
```

Commands you can type during a session:

| You type           | The agent                                                   |
| ------------------ | ----------------------------------------------------------- |
| `pending`          | reprints the open Review, Todo and Blocked items as written |
| `reassess`         | works out afresh which earlier items are still open         |
| `Expand Blocked.2` | reprints that item in enough detail to act on               |
| `Blocked.1: B`     | picks option B of Blocked item 1                            |

[SKILL.md](SKILL.md) holds the full rules. It is the only file the agent loads
when the skill is invoked. The agent reads `examples.md`, `commands.md` and
`scripts.md` only when it needs them, and the install leaves this README out.
