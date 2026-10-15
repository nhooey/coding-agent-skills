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
The parser regression came from the tokenizer rewrite; the fix is committed,
and the 2.x backport is your call.

✅ **Done:**  
▔▔▔▔▔▔▔▔
1. **Tokenizer fix:** `src/lexer.rs` stops splitting `::` inside generics;
   commit `a1b2c3d`.
    
2. **Test suite:** 412 passed, 0 failed.

🚧 **Open:**  
▔▔▔▔▔▔▔▔
1. **The same `::` split in `src/macro_lexer.rs`:** not fixed yet; it needs
   the macro tests to run first.

📝 **Logged:**  
▔▔▔▔▔▔▔▔▔▔
1. **Entry 0412, the lexer's error recovery after an unclosed `<`:** found
   while bisecting, left for the next agent.

🤔 **Waiting:**  
▔▔▔▔▔▔▔▔▔▔▔
1. **CI on the `fix-generics` branch:** when it passes, the branch is merged.

❓ **Questions:**  
▔▔▔▔▔▔▔▔▔▔▔▔
1. **Why did the bug show only in release builds?** The release profile
   enables the `fast-lex` feature, the only path into the rewritten tokenizer.

🔍 **Review:**  
▔▔▔▔▔▔▔▔▔▔
1. **The new error for an unclosed generic:** run
   `cargo run -- check tests/fixtures/unclosed.rs` and check that the caret
   points at the `<`.

👉 **Todo:**  
▔▔▔▔▔▔▔
1. **Add `CARGO_REGISTRY_TOKEN` to the repo's Actions secrets:** Settings →
   Secrets and variables → Actions; it frees the 2.x patch release.

🛑 **Blocked:**  
▔▔▔▔▔▔▔▔▔▔▔
1. **Whether to backport the `src/lexer.rs` tokenizer fix to the 2.x branch:**
   🔘 A. **Cherry-pick commit a1b2c3d onto 2.x**: one commit, CI reruns.
      ➕ 2.x users get the fix in the next patch release.
      ➖ 2.x has its own lexer tests, which may need updating.
   🔘 B. **Leave 2.x as it is**
      ➕ No work now.
      ➖ The `::` bug stays in 2.x.
    
2. **Seeds for `::` in nested generics in the lexer's fuzz corpus:**
   👍 Y. **Add 3 seeds to `fuzz/corpus/lexer`**
      ➕ The fuzzer guards the case from now on.
      ➖ Each fuzz run takes about 10% longer.
   👎 N. **Rely on the unit test in `tests/lexer.rs`**
      ➕ Fuzz runs stay as they are.
      ➖ Variants of the bug that the unit test misses go unnoticed.

📌 Outstanding: 🔍 1 · 👉 2
```

The 📌 line counts what earlier turns left open; this turn's own items join it from the next turn on.

## Answering it

Each list asks something different of you. Lists you only read need no reply; the rest you answer by list and number, in one line each:

| List         | Your reply                                                    | What happens                                                            |
| ------------ | ------------------------------------------------------------- | ----------------------------------------------------------------------- |
| ✅ Done      | nothing                                                       | a record of the turn; it never rolls up                                 |
| 🚧 Open      | nothing                                                       | the agent finishes it later; it stays under 📌 until then               |
| 📝 Logged    | nothing                                                       | the entry waits in the backlog for the next agent                       |
| 🤔 Waiting   | nothing                                                       | the agent reports when it lands; it stays under 📌 until then           |
| ❓ Questions | nothing                                                       | your question, answered; it never rolls up                              |
| 🔍 Review    | comment on it, or say you looked: `Review.1 looks right`      | it closes once your reply shows you reviewed it                         |
| 👉 Todo      | do it, then say so: `Todo.1 done`                             | it closes, and the agent starts the work it freed                       |
| 🛑 Blocked   | the item and a letter: `Blocked.1: A`, or short, `1. A, 2. Y` | the agent acts on your choice; a checkbox item takes several, `3. A, C` |

For the example above, this reply settles everything that waits on you:

```text
Blocked.1: A
Blocked.2: Y
Review.1: the caret is right.
Todo.1 done.
```

The next turn cherry-picks `a1b2c3d` onto 2.x, adds the fuzz seeds and starts the patch release. The Review, Todo and Blocked items leave 📌 for good; the Open and Waiting items stay there until the agent reports them done. An item from an earlier turn takes that turn's id, from its usage line: `Blocked.2 of 0f311c94: B`.

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
