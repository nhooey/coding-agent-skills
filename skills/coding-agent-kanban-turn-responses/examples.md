# Kanban turn response examples

_Worked examples of the [`coding-agent-kanban-turn-responses` skill](SKILL.md)'s shapes: a Blocked list, the full 📌 roll-up and the count line that stands in for it._

## A Blocked list

A checkbox item and a binary item, each multi-line item parted from the next by a line holding the list's indent and one U+00A0, and nothing else.

```text
🛑 **Blocked:**
▔▔▔▔▔▔▔▔▔▔▔
1. **Backlog cleanups to start, of 260 entries in the backlog:** any of 2.
   Note on the whole decision: the figures, the words at issue, 🔗 [an example](url).
   🔲 A. **Entry 1411, the 4 quotation matchers made one**, on Sonnet: `decisions.quotation_found`, `quotation_occurs`, `packets.normalised` and `_lands` become one function.
      ➕ A citation lands or fails the same way in the loader, the render, the packet and the checks.
      ➖ About 0.5M-1M 1x tokens, and it waits for `case-law-load`, which edits the same code.
   🔲 B. **Entries 0550 and 0455, dead code**, on Haiku: delete `findings_sources.py`, and repoint code citing the 2 deleted plans.
      ➕ About 0.1M 1x tokens.
      ➖ Nothing gained but tidiness.

2. **Next decision, naming its subject:** sentence.
   👍 Y. **Name what yes does**: consequence.
      ➕ What Y gains.
      ➖ What Y costs or risks.
   👎 N. **Name what no does**: consequence.
      ➕ What N gains.
      ➖ What N costs or risks.
```

## The full roll-up

Printed once the roll-up interval has passed; `outstanding.py render` drafts it, and the session prunes what is settled.

```text
📌 **Outstanding from previous turns:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤔 **Waiting:**
- **Landing `atomic-reload` with 4 other branches,** entry 1419's whole-file database swap among them. 🔖 0f311c94₋₃
👉 **Todo:**
- **The 2 API keys to rotate in the cloud console:** `deploy-bot` and `ci-runner`, both issued before the leak. 🔖 18e77cb3₋₁₇
🛑 **Blocked:**
- **The cache store for the build, given its 3 GB limit:** local disk, S3 or no cache. 🔖 9d2e7a10₋₂
```

## The count line

Printed in place of the full roll-up until the interval has passed; `outstanding.py render --counts` drafts it from the same items.

```text
📌 Outstanding: 🚧 4 · 🤔 2 · 🔍 2 · 👉 1 · 🛑 5
```
