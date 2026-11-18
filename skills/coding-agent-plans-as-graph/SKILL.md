---
name: coding-agent-plans-as-graph
description: Keep a project's plans as a graph of Markdown nodes in `agents/plans/`, one node per file, open ones in `open/` and finished ones in `closed/`, a plan of several nodes in a folder of its own, with a generated README showing what's in progress, ready, blocked and proposed. Each node has a state (proposed, approved, in-progress; implemented, rejected, abandoned, superseded), a kind (end state, implementation, schedule) and typed links (`part-of`, `needs`, `after`, `superseded-by`), and its body can be as long as it needs. Plans say what will be true, separately from how to get there and from when and by which agents, with costs in tokens, dollars and weekly-limit percent. The research and audits a plan rests on are dated reports in `agents/reports/`, each current or superseded. The bundled `plans.py` checks the graph, lists ready nodes and writes the overview. Use when writing, updating or reviewing a plan, starting work from one, closing a node, scheduling agents across plan nodes, or tidying plans left in `.claude/plans/` or elsewhere.
---

# Plans as a graph of Markdown nodes

_A plan is a folder of small Markdown files, each a node with a state and typed links, readable at a glance through a generated overview._

## Layout

```text
agents/plans/
  README.md                the overview, written by plans.py; never edited by hand
  open/<id>.md             proposed, approved or in-progress
  closed/<id>.md           implemented, rejected, abandoned or superseded
  <plan>/open/<id>.md      the same, for the nodes of one plan
  <plan>/closed/<id>.md
```

- **One node per file**, named by its id: lower-case words and dashes that say what it is, such as `uniform-skill-sets`. The id never changes, because links use it.
- **Open or closed is the folder:** closing a node moves it to the `closed/` beside its `open/` in the same commit that sets its state, with `git mv`, so its history follows it.
- **A plan of several nodes gets its own folder:** nodes that belong to one plan, such as a cross-repository cleanup or a feature's rollout, go in `agents/plans/<plan>/open/` and `closed/`, the folder named like an id. A lone node stays in the top-level `open/` and `closed/`. Ids stay unique across every plan, so a link never says which folder its target is in, and a node can link into another plan.
- **A long list may wrap:** a formatter such as prettier breaks a long `needs:` list onto an indented next line, and `plans.py` reads the indented line as part of the one above.
- **`agents/plans/`** sits beside `AGENTS.md`, readable by any agent and committed like code. Plans in `.claude/plans/`, `docs/plans/` or a `_implemented/` folder are moved here (see [Tidying old plans](#tidying-old-plans)).

## A node

```markdown
---
title: Every skill repository installs the same authoring skills
state: approved
kind: end-state
part-of: uniform-skill-sets
needs: [skillspkgs-authoring-combination]
---

# Every skill repository installs the same authoring skills

What is true when this is done, and how to check it. As long as it needs.
```

The frontmatter is one `key: value` per line, with lists in brackets:

| Key              | Holds                                                                         |
| ---------------- | ----------------------------------------------------------------------------- |
| `title`          | the node's name, as the overview shows it; required                           |
| `state`          | one of the seven states below; required                                       |
| `kind`           | `end-state`, `implementation` or `schedule`; required                         |
| `part-of`        | the one node this one breaks down                                             |
| `needs`          | nodes that must be `implemented` before this one can start                    |
| `after`          | run order between schedule nodes, with no logical need                        |
| `superseded-by`  | the replacement, required when `state: superseded`                            |
| `touches`        | files or modules the work changes, so two runs don't collide in them          |
| `owner`          | who is working on an in-progress node: a person, a branch or a headless job   |
| `implemented-by` | the commit or pull request that finished it                                   |
| `cost`           | a schedule node's estimate: tokens, dollars and the share of the weekly limit |

The body is free Markdown: the reasoning, the design, the checks. Write it as the plan stands; a change of mind is an edit, and why it changed goes in the commit message.

## States

| State         | Folder    | Means                                                   |
| ------------- | --------- | ------------------------------------------------------- |
| `proposed`    | `open/`   | written, not yet agreed                                 |
| `approved`    | `open/`   | agreed; ready once everything it `needs` is implemented |
| `in-progress` | `open/`   | someone is on it, named in `owner`                      |
| `implemented` | `closed/` | done, and its checks pass                               |
| `rejected`    | `closed/` | decided against                                         |
| `abandoned`   | `closed/` | started or approved, then dropped                       |
| `superseded`  | `closed/` | replaced by the node in `superseded-by`                 |

**Blocked isn't a state:** an approved node whose `needs` aren't all implemented is blocked, and the overview works that out. Only the user moves a node from `proposed` to `approved`, or to `rejected`.

## Links

- **`part-of`** breaks a node down: an end state into the implementation nodes that reach it. It's a tree, one parent each.
- **`needs`** gates: the node can't start until each named node is implemented. Keep it to real needs, so most of the graph can run at once.
- **`after`** orders schedule nodes that have no logical need between them, such as two waves that would compete for the same machine or the same files.
- **Dependencies between software modules** aren't written down: they're in the code, and a node's `touches` says where it works.

## Three kinds of node

A plan keeps what, how and when apart, so each can change without rewriting the others:

- **End state:** what will be true, as desired state: postconditions in the present tense that a check could confirm ("every skill repository's dev shell installs the authoring skills"), in the snapshot form `writing-hygiene-declarative-statements` describes. No steps, no tools; steps belong only in implementation nodes.
- **Implementation:** how one part of an end state gets done, `part-of` it: the approach, the files, the checks that prove it.
- **Schedule:** when and by whom. A wave of agents, which implementation nodes it runs, how many at once, and its `cost`: tokens per run times runs, in dollars, and that as a share of the user's weekly limit. Schedule nodes are the only ones with `after`.

## Reports

Research and audits that plans rest on go in `agents/reports/`, beside `agents/plans/`:

- **A report is a dated record,** named `agents/reports/<YYYY-MM-DD>-<slug>.md`, with frontmatter holding `state: current` or `state: superseded`, `superseded-by: <report>` when superseded, and `as-of:` naming the commit or commits it was made against.
- **A plan node links to the report that justifies it,** with a Markdown link in its body.
- **Raw or machine-specific data,** such as timing logs, per-run logs and wave summaries, stays under `$XDG_STATE_HOME`; the report links to it or summarises it.
- **A report is a point-in-time record,** exempt from `git-hygiene-no-history-in-tracked-files` as a decision record is. Its `state` says whether it still holds; a newer finding is a new report that supersedes it, not an edit.

## Working from a plan

- **Find work:** `plans.py ready` lists approved nodes with nothing left to wait on.
- **Claims come from one coordinator:** a node is claimed by the one session that hands out the work, which sets `state: in-progress` and `owner` and pushes that to the default branch before it starts the run. An agent in a worktree or on its own branch never claims a node itself: its commit is invisible to other agents until it merges, so two agents could take the same ready node.
- **No coordinator, no claiming:** where several agents pick work on their own, the files can't make a claim atomic. Use a tracker that can, holding claims by node id, and leave the nodes' `state` to the coordinator or the user.
- **Finish:** set the state, add `implemented-by`, `git mv` it to `closed/`, and regenerate the overview, in the commit that finishes the work or the one straight after.
- **Every change to the graph:** run `plans.py check`, then `plans.py overview`, and commit the overview with the nodes.
- **The hook:** in Claude Code, the `coding-agent-skills-hooks` plugin's `scripts/plans-check-hook.sh` runs `check` after each Write or Edit of a node and adds any finding to the session's context. It doesn't see edits through Bash, such as a `git mv` to `closed/`, and never writes the overview, so the line above still holds.

## The script

`scripts/plans.py`, standard library only, run from the project root:

```bash
python3 scripts/plans.py check      # every problem; exits 1 if any
python3 scripts/plans.py ready      # approved nodes whose needs are all implemented
python3 scripts/plans.py overview   # rewrites agents/plans/README.md, after a clean check
```

`--plans <dir>` points it at another folder. `check` reports a state in the wrong folder, links to missing nodes, cycles in `part-of`, `needs` or `after`, `after` outside a schedule node, unknown keys, missing fields, and nodes left at the plan's root.

## Tidying old plans

For each plan found elsewhere:

1. Read it against the code: what's built, what isn't, what's no longer wanted.
2. Split it into nodes: one end state, its implementation nodes, and a schedule node if it had a build order.
3. Set each node's state from what the code shows, and move finished ones to `closed/`.
4. Leave dates, "done on" notes and who asked out of the nodes; they're in the old file's history and the commit message that moves it.
5. Remove the old file in the same commit, run `check` and `overview`, and list the nodes whose state was a judgement call for the user.

## Your preferences

!`cat "$(dirname "${CLAUDE_SKILL_DIR}")/coding-agent-plans-as-graph.preferences.md" "${CLAUDE_PROJECT_DIR}/.agents/skills/coding-agent-plans-as-graph.preferences.md" 2>/dev/null || true`

If your agent doesn't run the line above, read these files yourself if they
exist: `coding-agent-plans-as-graph.preferences.md` next to this skill's folder, then
`.agents/skills/coding-agent-plans-as-graph.preferences.md` in the project. A project's
file overrides the user's, and the user's overrides this skill's defaults.

The keys this skill reads, with its own defaults:

```markdown
- Plan folder: agents/plans
- Weekly limit: ask the user before costing a schedule
- Dollars per million tokens: from the model's current price list
```

## When to apply

- Writing, updating or reviewing a plan, or turning a request into one.
- Starting work from a plan, or finishing a node.
- Scheduling agents across plan nodes, or estimating what a schedule costs.
- Finding plans in `.claude/plans/`, `docs/plans/` or another folder.

## Related skills

When one of these applies and it's in your skill listing, load it
without asking. If it isn't in your listing, tell the user which skill is
missing and ask whether to install it from the same collection this skill
came from; don't apply it from memory.

- `coding-agent-headless-in-checkout`: runs a schedule node's wave, one headless session per checkout.
- `git-hygiene-no-history-in-tracked-files`: a node states the plan as it stands, with its history in commit messages; reports are exempt.
- `writing-hygiene-declarative-statements`: the snapshot form an end-state node's postconditions are written in.
- `coding-agent-skill-references`: the preferences files this skill reads.
