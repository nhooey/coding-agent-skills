---
title: A workaround skill for bundled scripts the Monitor tool couldn't run on macOS
state: rejected
kind: implementation
---

# A workaround skill for bundled scripts the Monitor tool couldn't run on macOS

A proposed `coding-agent-skills-bundled-script-invocation-in-buggy-claude` skill, telling skills
how to run their bundled scripts from the Monitor tool, which didn't load the shell snapshot and so
ran with a near-empty `PATH` on macOS (anthropics/claude-code#63050). Claude Code fixed the bug, so
the workaround isn't needed. Making scripts fail loudly when a tool is missing, the lesson it
taught, is skill-authoring-skills' `bundled-scripts-fail-loudly` plan.
