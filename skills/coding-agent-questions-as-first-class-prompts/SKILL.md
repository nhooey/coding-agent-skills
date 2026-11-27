---
name: coding-agent-questions-as-first-class-prompts
description: Ask the user every question through the agent's structured-question tool, such as Claude Code's AskUserQuestion, an IDE's multiple-choice prompt or a CLI option picker, never as a prose question in the reply that waits for a typed answer. Covers clarifications, choices between approaches, yes-or-no confirmations and any decision the context can't settle; a multi-select question that opens on `All` then `None`; splitting a question that has more options than the tool allows; option previews of 3 or 4 lines; and an open question asked as best guesses plus the tool's free-text escape. Use whenever about to write "Should I…?", "Do you want…?", "Which of these…?" or "Let me know whether…", or otherwise pause for the user's input; not for status updates or for decisions the agent can make itself.
---

# Questions as first-class prompts

_A question for the user goes through the agent's structured-question tool, where it is answered by a click, not typed into the reply where it can be missed._

## The rule

When you need the user to answer something, ask it through your runtime's structured-question tool, not as prose in your reply:

| Agent         | The tool                               |
| ------------- | -------------------------------------- |
| Claude Code   | `AskUserQuestion`                      |
| An IDE agent  | its multiple-choice prompt or form     |
| A CLI agent   | its interactive option picker          |
| Anything else | the question primitive in its tool set |

Why the tool and not prose:

- **One click, no typing:** the user picks an option, and the answer maps to a known branch, where "yeah the second one I guess" has to be interpreted.
- **Can't be missed:** a question buried in a long reply gets skipped while the user answers the parts they saw; a prompt stands on its own.
- **On the record:** what was asked and what was chosen are explicit in the transcript.

Where a final response also lists the decision, as in the Decide list of `coding-agent-kanban-turn-responses`, the picker offers the same options in the same order.

## Multi-select: `All`, then `None`

A question that lets the user pick more than one option opens on two shortcuts, in this order, before the specific options:

1. **`All`:** every specific option.
2. **`None`:** no specific option.

```text
Which checks should I run before pushing?  [multi-select]
  ☐ All
  ☐ None
  ☐ Unit tests
  ☐ Lint
  ☐ Type-check
```

A single-select question gets neither.

**Option caps:** `AskUserQuestion` takes at most 4 options a question and adds an "Other" escape itself, so `All` and `None` leave room for 2 specific options. When the options don't fit, split them across several questions, grouping related ones, rather than dropping `All` and `None` or overflowing the cap.

## Option previews

Keep each option's preview to 3 or 4 lines.
Claude Code shows `AskUserQuestion` previews beside the options and hides the lines past what fits, however tall the terminal, and the user can't scroll or expand them.

- **Use the width:** write wide lines, and list several examples on one line joined by `·`, never one to a line.
- **Drop the preview** when what it shows needs more than 4 lines; say it in the option's description or before the question instead.

## Open questions

A question with no fixed set of answers, such as "what should I name this module?" or "what's the target latency?", still goes through the tool: offer 2 or 3 informed guesses as options, and let the tool's free-text or "Other" escape take an answer you didn't foresee. If the tool has no escape, offer the options anyway.

## When not to ask

- **Statements and status:** "Here's what I found" or "Next I'll run the tests" ask nothing.
- **Decisions you can settle yourself** from the code, the request or a sensible default: make the call, say what you chose, and let the user redirect. Ask only what you are blocked on.

## Your preferences

!`cat "$(dirname "${CLAUDE_SKILL_DIR}")/coding-agent-questions-as-first-class-prompts.preferences.md" "${CLAUDE_PROJECT_DIR}/.agents/skills/coding-agent-questions-as-first-class-prompts.preferences.md" 2>/dev/null || true`

If your agent doesn't run the line above, read these files yourself if they
exist: `coding-agent-questions-as-first-class-prompts.preferences.md` next to this skill's folder, then
`.agents/skills/coding-agent-questions-as-first-class-prompts.preferences.md` in the project. A project's
file overrides the user's, and the user's overrides this skill's defaults.

## Related skills

When one of these applies and it's in your skill listing, load it
without asking. If it isn't in your listing, tell the user which skill is
missing and ask whether to install it from the same collection this skill
came from; don't apply it from memory.

- `coding-agent-kanban-turn-responses`: the Decide list a final response prints, whose options the picker repeats.
- `github-workflow-pull-request-changeset-prompt`: this rule applied to the Stage, Commit and Push multi-select after a changeset, split to fit the 4-option cap.
- `coding-agent-route-feedback-to-skills-over-memory`: which skill or path a lesson lands in is a decision to ask through the tool.
- `coding-agent-skill-references`: where this skill's preferences files live and who writes them.
