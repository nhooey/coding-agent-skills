---
title: A skill for where plan files go and how plan mode answers questions
state: superseded
kind: implementation
superseded-by: plans-as-graph-skill
---

# A skill for where plan files go and how plan mode answers questions

A proposed `coding-agent-plan-mode-conventions` skill with four rules. None was built as that
skill; each now has another home:

- **Plans in the project, implemented ones moved aside:** `coding-agent-plans-as-graph` puts them
  in `agents/plans/open/` and `closed/`.
- **Answer a question first, then offer to change the plan:** `coding-agent-questions-as-first-class-prompts`
  covers answering, and turning follow-ups into structured prompts.
- **Wrap plan Markdown at 120 columns:** dropped; `nix fmt` sets the formatting.
