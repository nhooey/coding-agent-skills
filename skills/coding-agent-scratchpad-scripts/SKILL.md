---
name: coding-agent-scratchpad-scripts
description: Keeps an agent from filling its scratchpad with cryptic throwaway scripts. An edit to a file goes through the Edit or Write tool, never a generated script; a one-off check runs inline in the Bash call, a heredoc to `python3 -` included, with no file written; anything run, or expected to run, a second time becomes a named, documented tool committed in the project, or in a skill's scripts/ when it isn't specific to the project; a generated file is never `source`d; and a scratchpad file that is kept gets a name saying what it holds. Use it before writing any file to a scratchpad or temporary directory, before writing a script to change a file, and before briefing a subagent that will run commands. Main agents and subagents alike.
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

3. **Anything run, or expected to run, a second time becomes a named, documented tool in the project,** committed like other code: under `tools/`, `scripts/` or wherever the project keeps them, or as a dev-shell command. Its name says what it does (`rerun-until-failure`, `diff-fixtures-against-base`), not `loop.py` or `t.py`, and it opens with a usage docstring: what it does, its arguments, an example. A tool that isn't specific to the project goes in a skill's `scripts/` instead.

   Before writing one, check whether the project already does the job: rerunning the test suite, timing a command, diffing fixtures against a base commit and rendering a component are usually a test-runner flag, a `make` target or a dev-shell command already.

4. **Never `source` a generated file,** in your own commands or in a subagent's. A sourced file runs unseen in the current shell, and hooks such as CC Safety Net refuse it ("shell execution source cannot be verified safely"), which interrupts the user. Write the commands into the Bash call, or make a tool of them under rule 3. Give every subagent this rule in its brief.
5. **A scratchpad file that is kept gets a name saying what it holds:** captured output, a data sample, a draft. `pr-78-body.md`, `ci-run-4412-log.txt` and `rulesets-before-garnix-removal/`, not `out.txt`, `a.json` or `s3.ts`. Never a numbered series: a new version replaces the file, or gets a name saying how it differs.

## Why the scripts pile up

Each Bash call starts a fresh shell, so a helper the agent wants again gets written to a file instead of kept in the shell. Small edits get done as throwaway Python instead of with the edit tool. And subagents each start their own series, since none can see what the others wrote.

In one session's scratchpad, after two days: 232 files, 111 of them scripts. Most had names like `t.py`, `m.ts`, `fx.ts`, `one.py` and `peek.py`, or came in series like `ed1.py` to `ed8.py` and `fix_test1.py` to `fix_test3.py`. About 53 ran once, about 25 ran more than once, and 37 never ran by path. The ones reused mostly redid a job the repo already had a command for.

## Rulings

| Ruling     | The user's words                                                                                                                                                                                                              | What it set                                                                                         |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| 2026-10-20 | "The agent tends to write a lot of cryptic scratchpad scripts for potentially-repeatable actions that it will do."; "make it a skill about scratchpad scripts, or see if there's an existing skill on the internet for that." | the 5 rules; no published skill covering this was found, in Claude skill guides or obra/superpowers |

**Why:** a scratchpad script with a cryptic name can't be found, trusted or reused, so the next agent writes another. A tool with a name and a docstring is found and reused by every later session, and an edit made with the edit tool can be reviewed.

**How to apply:** before writing a file anywhere but the project's own source, ask what it is. An edit goes through the Edit or Write tool. A check you'll run once goes inline. Anything you'll run again becomes a named tool in the project, after checking the project doesn't already have one. Data you keep gets a name saying what it holds. When briefing a subagent, pass these rules on, the `source` rule included.

## Related skills

When one of these applies and it's in your skill listing, load it
without asking. If it isn't in your listing, tell the user which skill is
missing and ask whether to install it from the same collection this skill
came from; don't apply it from memory.

- `coding-agent-route-feedback-to-skills-over-memory`: a correction about where scripts or scratch files belong lands in this skill, not in memory.
