---
name: coding-agent-session-recap
description: When the user asks to summarize, recap, or read back the current conversation, render the back-and-forth as alternating one-line entries prefixed with 🗣 (U+1F5E3 speaking head) for the user and 🤖 (U+1F916 robot face) for the assistant. One sentence per turn, intent + outcome, chronological order, no tool-call mechanics or monitor noise. Triggers on phrasings like "summarize the session," "recap our conversation," "what did we do," "transcript of the back-and-forth," or any explicit request for an emoji-prefixed dialogue readback.
---

# Render session as alternating 🗣 / 🤖 dialogue

When the user asks for a recap of the current conversation, render the
session like a script:

```
🗣 <user's request, one sentence>
🤖 <assistant's response, one sentence>
🗣 …
🤖 …
```

Use this exact glyph pair — 🗣 (U+1F5E3 speaking head) for the user, 🤖
(U+1F916 robot face) for the assistant. They map cleanly to "human voice"
vs "machine voice" and read top-to-bottom as dialogue. Don't substitute
other emoji (no 👤 / 💬, no 🧑 / 🦾) — the asymmetry of "speech bubble +
machine" is what makes the format scan.

## What each line carries

- **🗣 line** — the _intent_ of the user's turn, compressed to one
  sentence. "Make a branch and open a PR" is fine; quoting the user
  verbatim is not the goal.
- **🤖 line** — what the assistant _did_ and the relevant outcome.
  Lead with the action ("Opened PR #16", "Edited X", "Ran cleanup"),
  add a clause for the result if any ("PR merged before the amend
  landed", "all 8 checks green"). Don't restate the assistant's
  full prose.

One sentence per line. No sub-bullets, no hedges, no quoted tool
output.

## What to leave out

- **Tool-call mechanics** — `git push`, `gh pr create`, file paths,
  branch names. Mention a branch/PR number only when it's part of the
  user-facing narrative ("opened PR #17"), not as plumbing.
- **Monitor notifications and check-run events** — collapse into the
  surrounding 🤖 line ("PR opened; checks green") rather than giving
  each event its own line.
- **The assistant's internal deliberation** — questions it asked
  itself before answering don't belong here.
- **Confirmations the user typed only to unblock a question**
  ("yes go ahead", "sure") — fold into the next 🤖 line. If the
  confirmation carried new information ("yes, and also rename X"),
  keep the 🗣 line.
- **Long quoted output the user pasted** — paraphrase in a clause
  ("user shared the TUI hint bar text"); don't reproduce the paste.

## Course corrections deserve their own line

When the user pushes back on the assistant's approach — _"don't write
memories, write to the skill instead"_, _"rewrite the commit message
to focus on the why"_, _"that's not what I meant, do X"_ — that's the
load-bearing turn of the session. Keep it as its own 🗣 line, and have
the next 🤖 line acknowledge the change of direction, not just the new
output.

This is what makes the recap useful as a postmortem: the reader can
see where the path forked, not just where it ended.

## Ordering and grouping

- **Chronological, not topical.** The format is a script, so each
  turn appears in the order it happened. Reordering by topic loses
  the back-and-forth.
- **Collapse adjacent turns of the same role.** If the assistant
  spoke twice in a row (e.g. tool result then text reply, or two
  monitor reactions), fold into one 🤖 line. Same for the user if
  they sent two messages in quick succession.

## When to apply

- User asks for a summary, recap, readback, or transcript of the
  current session.
- User asks "what did we do today / in this conversation?"
- User asks to paste a session summary into a PR description,
  ticket, or stand-up note and wants the dialogue shape.
- User explicitly names the format ("with the robot and speech bubble
  emojis", "as a back-and-forth").

Don't volunteer this format unprompted — sessions get recapped on
request, not by default. For ad-hoc _"what's the state of X?"_
questions during a session, answer directly; the recap format is
for end-of-session retrospectives.

## Example (excerpt)

From a session that opened a PR, hit a merge race, then course-
corrected into a skill edit:

```
🗣 Make a branch for the current changes and open a PR.
🤖 Opened PR #16; armed a CI-checks monitor.

🗣 Rewrite the commit message to focus on "why," and force-push.
🤖 Amended locally, but the force-push failed — PR #16 had already
   merged and the branch auto-deleted.

🗣 Why didn't you set up a monitor for the merge?
🤖 Conflated the narrower CI-checks monitor with the broader
   PR-state watcher; saved the lesson as a memory.

🗣 Don't write memories — write to the relevant skill instead.
🤖 Removed the memory; added the lesson to the watcher skill.
```

The course correction at line 7 is the turn that earns the recap —
without it, the reader sees a tidy outcome but not the fork.
