---
name: coding-agent-scratchpad-scripts
description: Load before writing any file to a scratchpad or temporary directory, before scripting a file edit, and before briefing a subagent that runs commands. Keeps throwaway scripts out of the scratchpad; anything run twice goes to `shell-hygiene-commands-as-cli-tools`.
---

# Scratchpad scripts

_A script an agent writes to its scratchpad is read once, by nobody, and run once or never. The rule keeps edits in the edit tools, one-off checks inline, and only data, named for what it holds, in the scratchpad._

## The rule

1. **An edit to a file uses the Edit or Write tool.** Never a generated script that rewrites it: no `ed1.py`, `fix_test2.py` or `sed` script written to a file to change another file. The edit tools show the change as a diff, keep the file's state in step, and leave nothing behind.

   The [hook](#the-hook) reminds you of this rule when a Bash command's inline program (`python3 -` heredoc, `-c`, `-e`) opens a file for writing, or a heredoc goes into a file outside the temporary roots: the command runs and one line of context follows, up to three times a session; at `deny` the session's first such command is denied, and one that generates data is rerun unchanged.

2. **A one-off check runs inline in the Bash call,** with no file written. A heredoc into `python3 -` or `node -` is fine:

   ```bash
   python3 - <<'PYEOF'
   import json
   print(len(json.load(open("out/report.json"))["rows"]))
   PYEOF
   ```

   Pick a heredoc delimiter that can't occur in the body, such as `PYEOF`, not `EOF`.

3. **Anything run twice, or that a committed claim or file rests on, follows `shell-hygiene-commands-as-cli-tools`.**

4. **Never `source` a generated file,** in your own commands or in a subagent's. A sourced file runs unseen in the current shell, and hooks such as CC Safety Net refuse it ("shell execution source cannot be verified safely"), which interrupts the user. Write the commands into the Bash call, or make a tool of them under rule 3. Give every subagent this rule in its brief.
5. **The scratchpad holds data, and a file kept there gets a name saying what it holds:** captured output, a data sample, a draft. `pr-78-body.md`, `ci-run-4412-log.txt` and `rulesets-before-garnix-removal/`, not `out.txt`, `a.json` or `s3.ts`. Never a numbered series: a new version replaces the file, or gets a name saying how it differs.

## Why the scripts pile up

Each Bash call starts a fresh shell, so a helper the agent wants again gets written to a file instead of kept in the shell. Small edits get done as throwaway Python instead of with the edit tool. And subagents each start their own series, since none can see what the others wrote. Most such scripts run once or never, and the ones run again usually redo a job the project already has a command for.

## Why and how to apply

**Why:** a scratchpad script with a cryptic name can't be found, trusted or reused, so the next agent writes another. An edit made with the edit tool can be reviewed, and a data file named for what it holds can be found.

**How to apply:** before writing a file anywhere but the project's own source, ask what it is. An edit goes through the Edit or Write tool. A check you'll run once goes inline. Anything you'll run again goes under rule 3. Data you keep gets a name saying what it holds. When briefing a subagent, pass these rules on, the `source` rule included.
The rules hold for a main agent and a subagent alike.

## The hook

`scripts/scratchpad-guard.sh`, in the `coding-agent-skills-hooks` plugin, holds rules 1, 2 and 4 in every session and subagent:

- **PreToolUse on `Bash|Write|Edit`:** catches writing, editing, running or making executable a program file (`.py`, `.sh`, `.js`, `.ts` and the like) under a temporary root (`/tmp`, `/var/folders`, `$TMPDIR`) with no project marker (`.git`, `flake.nix`, `package.json`, an `.html` page, …) between, and `source` of any file there. Its message names the three ways out above.
- **SubagentStart:** gives each subagent rules 1, 2 and 4 in four lines, then rules 1 and 3 of `coding-agent-readable-tool-calls` (short paths, quiet commands) in two more.
- **The setting:** a line `Scratchpad guard: remind` in this skill's preferences file. `remind`, the default, lets the call run and adds the message; `deny` denies it; `off` silences both hooks.

## Your preferences

!`cat "$(dirname "${CLAUDE_SKILL_DIR}")/coding-agent-scratchpad-scripts.preferences.md" "${CLAUDE_PROJECT_DIR}/.agents/skills/coding-agent-scratchpad-scripts.preferences.md" 2>/dev/null || true`

If your agent doesn't run the line above, read these files yourself if they
exist: `coding-agent-scratchpad-scripts.preferences.md` next to this skill's folder, then
`.agents/skills/coding-agent-scratchpad-scripts.preferences.md` in the project. A project's
file overrides the user's, and the user's overrides this skill's defaults.

The keys this skill reads, with its own defaults:

```markdown
- Scratchpad guard: remind
```

`Scratchpad guard` is `deny`, `remind` or `off`; the hook reads it on every call, so a change needs no rebuild.

## Related skills

When one of these applies and it's in your skill listing, load it
without asking. If it isn't in your listing, tell the user which skill is
missing and ask whether to install it from the same collection this skill
came from; don't apply it from memory.

- `coding-agent-readable-tool-calls`: short paths, plain descriptions and quiet commands in each tool call; this skill's hook passes two of its rules to subagents.
- `coding-agent-route-feedback-to-skills-over-memory`: a correction about where scripts or scratch files belong lands in this skill, not in memory.
- `shell-hygiene-commands-as-cli-tools`: rule 3 in full: when a command becomes a tool in the project, and the tool's shape.
