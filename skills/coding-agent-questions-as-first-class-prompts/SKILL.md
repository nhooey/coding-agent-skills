---
name: coding-agent-questions-as-first-class-prompts
description: Whenever you need an answer from the user — a clarification, a choice between approaches, requirements gathering, a yes/no confirmation, or any decision you can't settle from context — pose it through your agent's first-class question facility (the dedicated structured-question / option-prompt primitive your runtime exposes), never as free-text prose in your reply that waits for a typed answer. Map this generic concept to whatever your specific agent calls it (e.g. Claude Code's AskUserQuestion tool, an IDE's multiple-choice prompt, a CLI option picker). For any multi-select question, the first two options must always be `All` then `None`, in that order, before the specific options. Triggers any time you catch yourself about to write "Should I…?", "Do you want…?", "Which of these…?", "Let me know whether…", or otherwise pause for user input. Does not apply to rhetorical framing or status updates that don't actually request an answer.
---

# Ask questions as first-class prompts, never as prose

When you need the user to answer something, route the question through
your agent's **first-class question facility** — the built-in,
structured primitive your runtime exposes for asking the user to pick
from options or supply a value. Do not type the question into your
reply as prose and wait for a free-text answer.

The rule is unconditional: _if you are asking the user a question, it
goes through the facility._ Prose questions are the failure mode this
skill exists to prevent.

## Why first-class beats prose

- **Selectable, not typed.** Structured options render as clickable
  choices — the user taps one instead of composing a sentence. Faster
  for them, and the answer comes back unambiguous.
- **Machine-parseable.** A chosen option maps to a known branch in
  your logic. A free-text reply ("yeah the second one I guess") forces
  you to re-interpret intent and can be misread.
- **Visible, not buried.** A prose question sunk in the middle of a
  long reply is easy to miss; the user answers the parts they saw and
  skips the question. A first-class prompt surfaces as its own
  decision point that demands a response.
- **Auditable.** Each prompt is an explicit fork in the work. Reviewers
  and later sessions can see _what_ was asked and _what_ was chosen,
  not reconstruct it from chat.

## Map the concept to your agent

This skill is agent-agnostic. "First-class question facility" is the
generic name for whatever your runtime provides:

- **Claude Code** — the `AskUserQuestion` tool.
- **IDE-embedded agents** — a multiple-choice prompt or form widget.
- **CLI agents** — an interactive option picker / select prompt.
- **Anything else** — the dedicated question primitive in your tool
  set, distinct from ordinary reply text.

Find the one your runtime offers and use it. The principle is fixed;
only the name changes.

## The multi-select `All` / `None` rule

For any question that lets the user pick **more than one** option, the
first two options are always, in this exact order:

1. **`All`** — select every listed specific option.
2. **`None`** — select no specific option.

Then the specific options follow. `All` and `None` give the user
instant "everything" and "nothing" shortcuts without hunting through
the list and toggling each box.

```
Which checks should I run before pushing?  [multi-select]
  ☐ All
  ☐ None
  ☐ Unit tests
  ☐ Lint
  ☐ Type-check
```

Single-select (pick-exactly-one) questions do **not** get `All` /
`None` — those shortcuts only make sense when multiple selections are
possible.

### When the facility caps the option count

Some facilities limit options per question (Claude Code's
`AskUserQuestion` allows 4, and auto-adds an "Other" escape). `All`
and `None` consume two of those slots, leaving fewer for specifics. If
the real options don't fit, **split into multiple questions** rather
than dropping `All` / `None` or overflowing the cap. Group related
specifics into one multi-select; ask the next group as a follow-up
prompt.

## Open-ended questions still go through the facility

A question that doesn't enumerate cleanly — "what should I name this
module?", "what's the target latency?" — is **not** an excuse to fall
back to prose. Route it through the facility anyway:

- Supply your best-guess options as the choices, and
- Rely on the facility's free-text / "Other" escape for an answer you
  didn't anticipate.

Offering 2–3 informed guesses plus an escape hatch is more useful to
the user than an open prose prompt, and it keeps every question
first-class. If your facility has no free-text escape at all, still
present the structured options — but never substitute a typed prose
question for the prompt.

## When this does NOT apply

- **Rhetorical or framing statements** that don't request an answer:
  "Here's what I found…", "Next I'll run the tests." No prompt needed.
- **Status updates and progress notes.** Reporting is not asking.
- **Decisions you can settle yourself** from the code, the request, or
  a sensible default. Don't manufacture a prompt for a choice with an
  obvious answer — make the call, state it, and let the user redirect.
  This skill governs questions you genuinely need answered, not
  ceremony around decisions you should just make.

The line: if you are pausing for the user to supply information or pick
a direction, it is a question and it goes through the facility. If you
are not actually blocked on their input, don't ask at all.

## Cross-references

- `github-pull-request-changeset-prompt` — a concrete application of
  this rule: the post-changeset Stage/Commit/Push prompt is a
  multi-select that must use the question facility (and shows the
  4-option-cap split in practice).
- `coding-agent-route-feedback-to-skills-over-memory` — when proposing
  where a lesson should land, the "which skill / which persistence
  path" choice is exactly the kind of decision to surface as a
  first-class prompt rather than a prose menu.
