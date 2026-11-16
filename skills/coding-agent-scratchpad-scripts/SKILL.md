---
name: coding-agent-scratchpad-scripts
description: Keep an agent's scratchpad free of cryptic throwaway scripts. Edit a file with the Edit or Write tool, never a generated script; run a one-off check inline in the Bash call, a heredoc to `python3 -` included, with no file written; make anything run, or expected to run, a second time into a named, documented tool committed in the project, or in a skill's scripts/ when it isn't specific to the project, and the same for code whose output a committed claim or file rests on, even if it ran once; never `source` a generated file; and give a kept scratchpad file a name saying what it holds. Use before writing any file to a scratchpad or temporary directory, before writing a script to change a file, and before briefing a subagent that will run commands, as a main agent or a subagent.
---

# Scratchpad scripts

_A script an agent writes to its scratchpad is read once, by nobody, and run once or never. The rule keeps edits in the edit tools, one-off checks inline, and anything worth running twice in the project as a named tool._

## The rule

1. **An edit to a file uses the Edit or Write tool.** Never a generated script that rewrites it: no `ed1.py`, `fix_test2.py` or `sed` script written to a file to change another file. The edit tools show the change as a diff, keep the file's state in step, and leave nothing behind.
2. **A one-off check runs inline in the Bash call,** with no file written. A heredoc into `python3 -` or `node -` is fine:

   ```bash
   python3 - <<'PYEOF'
   import json
   print(len(json.load(open("out/report.json"))["rows"]))
   PYEOF
   ```

   Pick a heredoc delimiter that can't occur in the body, such as `PYEOF`, not `EOF`.

3. **Anything run, or expected to run, a second time leaves the scratchpad and becomes a tool in the project,** in the shape `shell-hygiene-commands-as-cli-tools` gives: commands and options, `--help`, tests and a dev shell entry, grown into the project's existing tool where there is one. A tool that isn't specific to the project goes in a skill's `scripts/` instead. So does code whose output a committed claim or file rests on, even if it ran once: a probe behind a documented behaviour becomes a test or an eval example, and a script that built a committed file becomes a tool. A check under rule 2 that a claim ends up resting on is kept the same way.

4. **Never `source` a generated file,** in your own commands or in a subagent's. A sourced file runs unseen in the current shell, and hooks such as CC Safety Net refuse it ("shell execution source cannot be verified safely"), which interrupts the user. Write the commands into the Bash call, or make a tool of them under rule 3. Give every subagent this rule in its brief.
5. **A scratchpad file that is kept gets a name saying what it holds:** captured output, a data sample, a draft. `pr-78-body.md`, `ci-run-4412-log.txt` and `rulesets-before-garnix-removal/`, not `out.txt`, `a.json` or `s3.ts`. Never a numbered series: a new version replaces the file, or gets a name saying how it differs.

## Why the scripts pile up

Each Bash call starts a fresh shell, so a helper the agent wants again gets written to a file instead of kept in the shell. Small edits get done as throwaway Python instead of with the edit tool. And subagents each start their own series, since none can see what the others wrote. Most such scripts run once or never, and the ones run again usually redo a job the project already has a command for.

## Why and how to apply

**Why:** a scratchpad script with a cryptic name can't be found, trusted or reused, so the next agent writes another. A tool with a name and a docstring is found and reused by every later session, and an edit made with the edit tool can be reviewed.

**How to apply:** before writing a file anywhere but the project's own source, ask what it is. An edit goes through the Edit or Write tool. A check you'll run once goes inline. Anything you'll run again becomes a named tool in the project, after checking the project doesn't already have one, and so does anything a committed claim or file rests on. Data you keep gets a name saying what it holds. When briefing a subagent, pass these rules on, the `source` rule included.

## Related skills

When one of these applies and it's in your skill listing, load it
without asking. If it isn't in your listing, tell the user which skill is
missing and ask whether to install it from the same collection this skill
came from; don't apply it from memory.

- `coding-agent-route-feedback-to-skills-over-memory`: a correction about where scripts or scratch files belong lands in this skill, not in memory.
- `shell-hygiene-commands-as-cli-tools`: the shape a command run twice takes once it leaves the scratchpad.
