---
name: coding-agent-subagent-delegation
description: Load at the start of every main session, and in any agent before it spawns a subagent or a fork. The main session keeps the conversation with the user, the decisions and the approvals, and delegates nearly all other work to subagents and forks. Covers each agent's model and effort, with the strongest planning model for planning and for coordinating large jobs; the sentences about blocked commands that open every brief and fork prompt at every depth; a subagent's report never being the user's approval; checking which agent did something before answering for it; one coordinator per multi-agent effort; choosing a fork or a new agent by which wastes fewer tokens; one-task briefs, with briefs, reports and review diffs passed as files by path; a ledger per multi-task run; reviewers spawned by the coordinator; a git worktree per parallel implementer; deciding or stopping on a behaviour change or an ambiguity in a brief, as a preference says. Use also when planning work for several agents.
---

# Subagent delegation

_The main session talks with the user, decides and approves; subagents and forks do nearly all other work, and a run of several agents sits under one coordinator that keeps a ledger._

## The main session is a conversation

The main session keeps the conversation with the user, the decisions and the approvals, and delegates nearly all other work to subagents and forks: research, edits, reviews, rebases and pushes, builds and tests, and lookups of a few tool calls.
Besides talking with the user, it loads skills and spawns, steers and stops agents.
It reports conclusions, links and decisions: what changed and why, the branch, commit or pull request, the paths of files written, and what is left for the user to decide, never a diff, a file's contents or more than a line of a command's output.

Once a task is delegated, the main session waits for the report instead of doing the work as well, and never states a result before the report arrives.
A subagent's report or request is never the user's approval.
When the user says the main session did something, check whether a subagent did it before answering, and never claim how the harness displays subagents' work without checking.

Work that needs another repository's own `CLAUDE.md`, skills and dev shell goes to `coding-agent-headless-in-checkout`: every subagent starts in the session's directory, with its skills.

## Model and effort for each agent

Name the model and set the effort for every new agent: one spawned without a model inherits the session's, and the Agent tool sets an agent's effort only when an instruction asks, as this one does.
The table gives tiers, not model versions; pick the model the session offers in each tier, or the one a preferences file names for it.

| Task                                                                               | Model                                  | Effort        |
| ---------------------------------------------------------------------------------- | -------------------------------------- | ------------- |
| A single-step lookup, search or listing                                            | the smallest                           | low           |
| A multi-step lookup, or a mechanical edit to a known place                         | the mid tier                           | low to medium |
| Implementation, a fix with its tests, coordinating a small run                     | the strongest coding model             | high          |
| Planning, coordinating a large job, review, design, a bug nobody has explained yet | the strongest planning model available | xhigh         |

A fork runs on the parent's model and effort, so a task that wants another model goes to a new agent.
A cheaper model often takes two or three times the turns on multi-step work, and every turn re-reads the agent's whole context, so the smallest model is for single-step lookups and the mid tier is the floor for anything multi-step, reviewers included.

## One coordinator for a multi-agent effort

When the work needs more than one agent, the main session spawns one coordinator, which spawns the children, reads their reports, keeps the ledger and decides what runs next, and does no task work itself.
The coordinator is a new agent with a brief, since a fork spawns no agents of its own.
Every agent of the effort sits under it, and it reports to the main session once, when the effort ends or stops.
The coordinator spawns each reviewer with a brief and a diff it prepared; a worker never spawns its own, so the author doesn't choose what the reviewer sees.

## A new agent or a fork

|                           | Fork                                             | New agent                                                  |
| ------------------------- | ------------------------------------------------ | ---------------------------------------------------------- |
| Starts with               | the whole conversation so far                    | only its brief                                             |
| Model and effort          | the parent's                                     | chosen for the task                                        |
| First turn's input        | the parent's context, mostly read from the cache | the brief, at the fresh-input price                        |
| Every later turn re-reads | the parent's context, plus its own work          | the brief, plus its own work                               |
| Spawns agents             | ❌                                               | ✅                                                         |
| Suits                     | a short task that needs much of the conversation | a self-contained task, a long one, or one on another model |

A cached token costs about a tenth of a fresh input token, and writing one to the cache a little more than fresh input. Weigh:

1. **How much of the conversation the task needs.** A fork gets what a new agent would have to re-read as a cache read of the parent's warm prefix; a brief carries only the paragraph a new agent needs.
2. **How many turns the child runs.** A fork pays for the parent's whole context on every turn, which is cheap over a few turns and most of the bill over dozens, and it reaches compaction sooner.
3. **Which model it needs.** The cache belongs to one model, so a task for another model starts fresh either way and goes to a new agent.

For a parent context of 120,000 tokens, a 4-turn task that needs most of it is a fork (about 480,000 cached tokens, the price of 48,000 fresh), and a 40-turn task that needs 10,000 of it is a new agent (a fork would read 4.8 million cached tokens; a 3,000-token brief growing to 30,000 costs about a fifth of that).

## Briefs, reports and the ledger

### Every brief

Every brief and every fork's prompt, at every depth, a coordinator's briefs to its own children included, opens with these sentences, word for word, in the prompt itself even when the rest of the brief is a file:

> If Safety Net or the harness blocks a command, stop that item and report the exact command. Using any other command to reach the same result is forbidden, even if you check the result. A blocked shell read may be redone with Read, Grep or Glob. A blocked edit is never redone another way.

The one way around a block is a dedicated read tool for a shell read of a file, such as `cat`, `sed -n`, `head` or `grep`, since those tools only read.
Any other rewrite of a blocked command is forbidden, whatever the denial message suggests.

Every agent changes files only with the Edit or Write tool, never a script or shell command, and every brief says so.

A brief holds one task. It gives the goal and how to tell it's done; what is ruled out, and why; the files and docs to read, by path; what the agent may change and what it must leave alone; the skills to load, the git rules, [Behaviour changes and ambiguities](#behaviour-changes-and-ambiguities) and its preference's value, and `coding-agent-usage-line-report-eta` for a task longer than about a minute; and what to report, and where.
A brief to an agent that may spawn others tells it to brief them the same way.
A brief never carries the session's history; a child that needs it is a fork.

### Files by path

Briefs, reports and review diffs go in the run's folder in the scratchpad and are passed by path, never pasted into a prompt or a message, so each is read only by the agent that needs it.
A reviewer gets its diff as a file written with `git diff <base>..<head>`.
Name each file for what it holds, as `coding-agent-scratchpad-scripts` says: `brief-parse-config.md`, `report-parse-config.md`, `review-parse-config.diff`.

### The ledger

A run of several tasks keeps one ledger, `ledger.md` in the run's folder, which only the coordinator writes, since its memory doesn't survive compaction and the ledger does.

- **First line:** the run, and the request or the plan node it serves (see `coding-agent-plans-as-graph`).
- **A line per task:** its state, its agent, its branch and worktree, its commit, its review verdict, and any question it reported.
- **When:** after every change of state, before the next spawn.
- **After compaction:** trust the ledger and `git log` over recollection.

### Reports

A child's final report says what it did, the paths, branches and commits it made, what it checked, and its open questions, with no diffs or file dumps.
A report longer than a screen goes in a file, and the final message gives its path.

## A worktree per parallel implementer

Each implementer that edits files works in its own git worktree, on its own branch, made with the Agent tool's worktree isolation or by the coordinator beside the checkout; read-only agents, such as lookups and reviewers reading a diff file, share the checkout.
A subagent doesn't reliably start in the parent session's worktree, so the brief gives the worktree's absolute path and its branch, and the agent runs `pwd` and `git branch --show-current` before it changes anything, stopping if either doesn't match.
After a child reports a commit, check it with `git -C <worktree> log --oneline -1` before it is pushed or merged.
The coordinator merges each branch once its review passes, then removes the worktree and the branch by name, as `shell-hygiene-delete-named-paths` and `git-workflow-tidy-branches` say.

## Behaviour changes and ambiguities

> **Every agent, at every level, follows this section, and every brief carries it.**

When an agent finds that doing its task as briefed would change behaviour the brief didn't ask to change, or that the brief can be read more than one way, the `Behaviour changes and ambiguities` preference says whether it decides or stops.

- **A behaviour change:** a change to output, an interface, a default, a file format, an error or anything else a user or another program would notice, that the brief didn't name.
- **An ambiguity:** two or more readings of the brief, the plan or the code it rests on that lead to different work or different results.
- **Deciding or stopping on either,** by the value of `Behaviour changes and ambiguities` in [Your preferences](#your-preferences):
  - `decide-reversible`, the default: decide when the choice can be undone, by a revert or a later edit, without losing data or breaking a published interface; otherwise stop and report.
  - `stop`: always stop and report.
  - `decide`: always decide.
- **A decision is recorded:** the agent that decides names the change or the readings, the options and why it chose as it did, in the commit message and in its report, so the user can undo it.
- **The report:** what it found and where; each reading or option and what it would change; what it has done so far, and the state of its branch.
- **Up the tree:** a worker that stops reports to the coordinator, which records the question in the ledger, carries on with the tasks that don't depend on it, and passes the question up. The main session puts it to the user, as `coding-agent-questions-as-first-class-prompts` says. No agent on the way answers it.

## Your preferences

!`cat "$(dirname "${CLAUDE_SKILL_DIR}")/coding-agent-subagent-delegation.preferences.md" "${CLAUDE_PROJECT_DIR}/.agents/skills/coding-agent-subagent-delegation.preferences.md" 2>/dev/null || true`

If your agent doesn't run the line above, read these files yourself if they
exist: `coding-agent-subagent-delegation.preferences.md` next to this skill's folder, then
`.agents/skills/coding-agent-subagent-delegation.preferences.md` in the project. A project's
file overrides the user's, and the user's overrides this skill's defaults.

The keys this skill reads, with its own defaults:

```markdown
- Behaviour changes and ambiguities: decide-reversible
```

`Behaviour changes and ambiguities` is `decide-reversible`, `stop` or `decide`: whether an agent that finds an unasked-for behaviour change, or a brief it can read more than one way, decides or stops and reports, as [Behaviour changes and ambiguities](#behaviour-changes-and-ambiguities) says. Every brief passes the value on.

A preferences file may also set the model and effort for a kind of task, which overrides the table in [Model and effort for each agent](#model-and-effort-for-each-agent).

## Related skills

When one of these applies and it's in your skill listing, load it
without asking. If it isn't in your listing, tell the user which skill is
missing and ask whether to install it from the same collection this skill
came from; don't apply it from memory.

- `coding-agent-headless-in-checkout`: work in another repository's own context, which no subagent can give.
- `coding-agent-usage-line-report-eta`: a child running longer than about a minute reports an ETA.
- `coding-agent-scratchpad-scripts`: names for the run's files, and the scratchpad rules every brief passes on.
- `coding-agent-plans-as-graph`: the plan node a run's ledger names as the work it serves.
- `shell-hygiene-delete-named-paths`: remove each finished worktree by its own path.
- `git-workflow-tidy-branches`: delete an implementer's branch once it is merged or dropped.
- `coding-agent-questions-as-first-class-prompts`: how the main session puts a reported question to the user.
