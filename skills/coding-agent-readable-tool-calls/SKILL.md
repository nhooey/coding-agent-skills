---
name: coding-agent-readable-tool-calls
description: Make every tool call an agent makes easy to read for the person watching it in the terminal. Paths relative to the project, with a `cd` once at the start of a Bash call or a long path held in a short variable, and never the scratchpad's absolute path twice; a description on each call saying what it does and why in plain words, never the command's text; one quiet command per call, its output trimmed with the tool's own options (`--max-count`, `--format`, `--jq`, Read's `limit`) rather than `| head | cut`, `2>&1` only when the error output matters, and no shell loop where the tool takes a batch. A pipeline or command needed a second time becomes a named tool per `shell-hygiene-commands-as-cli-tools`. Use before every Bash, Read, Edit, Write or Agent call, as a main agent or a subagent, and when briefing a subagent.
---

# Readable tool calls

_The person watching a session reads each tool call as it scrolls past. A call they can read at a glance shows them what the agent is doing; one buried in long paths and pipes shows them nothing, so they stop checking._

## The rules

1. **Short paths.** Name files relative to the project.
   - **One `cd` per call:** when a Bash call works somewhere else, start it with one `cd` there and use short paths after it. Where it needs a second long path, put that path in a short variable at the start (`skills=~/git/github/owner/repo/skills`) and use the variable.
   - **The scratchpad:** never write the scratchpad's absolute path more than once in a call. Name the file inside it, after a `cd` or through a variable.
   - **`cd` doesn't stay outside the project:** in Claude Code, a Bash call's `cd` carries to the next call only in the main session and only when it ends inside the working directories; elsewhere, and in every subagent, the next call starts back in the start folder. So each call that works outside the project opens with its own `cd`, once.
   - **The file tools take absolute paths:** Read, Edit and Write need one, and the terminal shows it relative to the session's folder, so a scratchpad file shows as a chain of `../../..`. Keep a file the session reads or edits more than once in the project when it belongs there, read a scratchpad file from a Bash call that starts with `cd` into the scratchpad, and read each file once, with `offset` and `limit` for the part you need, rather than in several calls.
2. **Descriptions say what and why.** Every tool call that takes a description, such as a Bash call's `description` or a subagent's `description`, says in plain words what the call does and what for: "Count the failing tests in the last CI run", not "gh run view --log | grep FAIL | wc -l". Never repeat the command's text, its flags or its paths; the reader can see those already, and needs the description for what they can't see.
3. **Quiet commands.**
   - **One command per call** where the work allows it. A chain of `&&` is for steps that depend on each other, not for batching unrelated checks; independent checks go in parallel calls.
   - **Trim with the tool's own options,** not a pipe: `git log --max-count=10 --format='%h %s'`, `grep --max-count=5`, `gh pr view --json title --jq .title`, `jq` over JSON, Read's `offset` and `limit`. Not `| head -60`, `| cut -c1-200` or `| tail`. A pipe stays only where no option does the job.
   - **`2>&1` only when the error output matters** to the answer. By default the tool shows both streams anyway.
   - **No shell loop over what the tool takes as a batch:** `git show a b c`, `sed --quiet '1,5p' one.md two.md`, `gh api --paginate`, several Read calls in parallel, rather than a `for` loop.
4. **A command needed again becomes a tool.** A pipeline you need more than once, or any command you run a second time, becomes a named tool in the project under `shell-hygiene-commands-as-cli-tools`, and the call names that tool.

## Before and after

A scratchpad file read in a pipeline:

```bash
# Before
cat /private/tmp/claude-501/-Users-me-git-proj/7c7bd17a-6e08-4396-873d-79f37759e539/scratchpad/ci-run-4412-log.txt 2>&1 | grep FAIL | cut -c1-200 | head -40
# description: "cat ci-run-4412-log.txt | grep FAIL"

# After
cd /private/tmp/claude-501/-Users-me-git-proj/7c7bd17a-6e08-4396-873d-79f37759e539/scratchpad && grep --max-count=40 FAIL ci-run-4412-log.txt
# description: "List the failing tests in the saved CI log, to pick which to fix first"
```

A check across another repository:

```bash
# Before
for f in ~/git/github/owner/skills/skills/*/SKILL.md; do head -3 ~/git/github/owner/skills/skills/$(basename $(dirname $f))/SKILL.md | tail -1 | cut -c1-120; done

# After
cd ~/git/github/owner/skills && git grep --line-number '^description:' -- 'skills/*/SKILL.md'
# description: "List each skill's description, to find which one covers this rule"
```

## Briefing a subagent

A subagent's calls scroll past the same person. Pass rules 1 and 3 on in its brief, or rely on the hook below where it runs.

## The hook

In Claude Code, the `coding-agent-skills-hooks` plugin's SubagentStart hook, `scratchpad-guard.sh` from `coding-agent-scratchpad-scripts`, gives every subagent rules 1 and 3 in two lines, after that skill's own rules. Its `Scratchpad guard: off` setting silences these lines too.

## Related skills

When one of these applies and it's in your skill listing, load it
without asking. If it isn't in your listing, tell the user which skill is
missing and ask whether to install it from the same collection this skill
came from; don't apply it from memory.

- `coding-agent-scratchpad-scripts`: what goes in the scratchpad and what each file there is named; its hook carries rules 1 and 3 to subagents.
- `shell-hygiene-commands-as-cli-tools`: rule 4 in full: when a command becomes a tool in the project, and the tool's shape.
- `shell-hygiene-long-options`: write each command's options in their long form, so the call reads without a man page.
