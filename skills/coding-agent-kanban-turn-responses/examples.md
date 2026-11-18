# Kanban turn response examples

_Worked examples of the [`coding-agent-kanban-turn-responses` skill](SKILL.md)'s shapes: a Decide list, two lists in one response, a `reassess` grouped by topic, the full 📌 roll-up and the count line that stands in for it._

## A Decide list

A checkbox item and a binary item. Each summary has its own line, ending in a hard line break, and each item is parted from the next by the separator line: the list's indent, one U+2800, and nothing else, directly under the item's last line. `scripts/lint_reply.py` finds no fault in it.

```text
🧠 **Decide:**  
▔▔▔▔▔▔▔▔▔▔
1. **Backlog cleanups to start, of 260 entries in the backlog**  
   Any of 2. Note on the whole decision: the figures, the words at issue, 🔗 [an example](url).
   🔲 A. **Entry 1411, the 4 quotation matchers made one**, on Sonnet: `decisions.quotation_found`, `quotation_occurs`, `packets.normalised` and `_lands` become one function.
      ➕ A citation lands or fails the same way in the loader, the render, the packet and the checks.
      ➖ About 0.5M-1M 1x tokens, and it waits for `case-law-load`, which edits the same code.
   🔲 B. **Entries 0550 and 0455, dead code**, on Haiku: delete `findings_sources.py`, and repoint code citing the 2 deleted plans.
      ➕ About 0.1M 1x tokens.
      ➖ Nothing gained but tidiness.
   ⠀
2. **Next decision, naming its subject?**  
   Its note.
   👍 Y. **Name what yes does**: consequence.
      ➕ What Y gains.
      ➖ What Y costs or risks.
   👎 N. **Name what no does**: consequence.
      ➕ What N gains.
      ➖ What N costs or risks.
```

## Two lists in one response

A list ends at a blank line. The blank line between the Done list's last separator line and the Todo header ends the Done list, so the Todo list numbers from 1 again. Without it, Markdown reads `👉 **Todo:**` and its underline as more of Done item 2's text, and the renderer numbers the Todo item 3. The same blank line goes before the 📌 roll-up or count line.

```text
✅ **Done:**  
▔▔▔▔▔▔▔▔
1. **Tokenizer fix in commit `a1b2c3d`**
   ⠀
2. **Test suite rerun after the fix**  
   412 passed and 0 failed, in 3 minutes.
   ⠀

👉 **Todo:**  
▔▔▔▔▔▔▔▔
1. **Rotate the `deploy-bot` key in the cloud console**  
   It was issued before the leak, and rotating it frees the release.

📌 Outstanding: 🧠 2
```

## A reassess grouped by topic

A `reassess` with 7 open items in 2 topics of at least 3 items and 1 left over. Each topic header is underlined with `═`, its lists follow in the usual order under it, and each list numbers on from where the same list ended in the topics above: the second topic's Decide list starts at 3, so `Decide.3` names one item. The topic with the most to decide or do comes first, and `Miscellaneous` last.

```text
**The atomic-reload database swap**  
═══════════════════════════════
👉 **Todo:**  
▔▔▔▔▔▔▔▔
1. **Run the reload benchmark on the staging box**  
   `make bench-reload` on `staging-2`; its timings settle Decide.1.

🧠 **Decide:**  
▔▔▔▔▔▔▔▔▔▔
1. **Merge order for the 3 `atomic-reload` pull requests**  
   🔘 A. **Schema, then loader, then the swap**: each lands on a working base.
      ➕ Every merge leaves master releasable.
      ➖ 3 review rounds instead of 1.
   🔘 B. **All 3 in one merge**: one review of the whole swap.
      ➕ One review round.
      ➖ A bad merge reverts all 3.
   ⠀
2. **Keep the old loader behind a flag for one release?**  
   👍 Y. **Keep `--legacy-loader` for one release**: a fallback while the swap beds in.
      ➕ A bad swap is undone by a flag, not a revert.
      ➖ 2 loaders to test until the flag goes.
   👎 N. **Delete the old loader with the swap**: one code path.
      ➕ Less code to test.
      ➖ A bad swap means a revert and a release.

**The 2026 backup plan**  
════════════════════
🔍 **Review:**  
▔▔▔▔▔▔▔▔▔▔
1. **#212 Nightly snapshot schedule**  
   🔗 [nhooey/infra#212](url): check the 02:00 window against the batch jobs.

👉 **Todo:**  
▔▔▔▔▔▔▔▔
2. **Rotate the `backup-bot` key in the cloud console**  
   It was issued before the leak; rotating it frees the first snapshot.

🧠 **Decide:**  
▔▔▔▔▔▔▔▔▔▔
3. **Snapshot retention for the nightly backups**  
   🔘 A. **90 days**: a quarter of history.
      ➕ Covers a quarterly audit.
      ➖ About 3 times the storage of 30 days.
   🔘 B. **30 days**: a month of history.
      ➕ The cheapest that covers a month-end restore.
      ➖ An audit past 30 days finds no snapshot.

**Miscellaneous**  
═════════════
🔍 **Review:**  
▔▔▔▔▔▔▔▔▔▔
2. **The README's new install section**  
   🔗 [README.md](url): check the 3 commands run as written.
```

## The full roll-up

Printed once the roll-up interval has passed; `outstanding.py render` drafts it, and the session prunes what is settled. A blank line before each group's header ends the group above it.

```text
📌 **Outstanding from previous turns:**  
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⏳ **Waiting:**  
- **Landing `atomic-reload` with 4 other branches,** entry 1419's whole-file database swap among them. 🔖 0f311c94₋₃

👉 **Todo:**  
- **The 2 API keys to rotate in the cloud console:** `deploy-bot` and `ci-runner`, both issued before the leak. 🔖 18e77cb3₋₁₇

🧠 **Decide:**  
- **The cache store for the build, given its 3 GB limit:** local disk, S3 or no cache. 🔖 9d2e7a10₋₂
```

## The count line

Printed in place of the full roll-up until the interval has passed; `outstanding.py render --counts` drafts it from the same items.

```text
📌 Outstanding: 🚧 4 · ⏳ 2 · 🔍 2 · 👉 1 · 🧠 5
```
