---
name: coding-agent-route-feedback-to-skills-over-memory
description: Load when the user corrects the agent, sets a standing rule ("always", "from now on"), confirms a non-obvious choice, reports a tool gotcha or a recurring problem, or asks it to remember a way of working, and before writing any memory about how to work. Routes the lesson to the one layer that owns it (a setting, flake, hook, program, skill or `AGENTS.md`). Not for who the user is, project state or one-off instructions.
---

# Route feedback to the layer that owns it

_A lesson about how to work belongs in the one layer that owns it: guidance where an agent reads it, a guarantee where a machine enforces it. A skill holds judgement; a fact, a ban or a setting that must hold without the agent's cooperation goes in configuration, a hook or a tool; memory is the last layer._

## Why not a memory

- **Shared:** everyone who installs the skill, uses the tool or builds the repository gets the lesson; a memory helps one user.
- **Found where it belongs:** a commit rule sits in the commit skill, a cache path in the dev shell, not among unrelated memories found only by recall.
- **Reviewed:** a skill edit or a plan node goes through git, with its history in the commit message; a memory changes unseen.
- **Held without recall:** a hook, a check or a dev shell setting holds whether or not the agent remembers it, and a skill is in every session's listing; a memory fires only when recalled.

## When this applies

Whenever the user teaches the agent how to work, whether or not auto-memory is loaded:

- **Corrections:** "stop summarizing every response", "use `gh`, not `curl`, for that".
- **Confirmations** of a non-obvious choice: "yes, one bundled pull request was right here". Quiet approvals are easy to miss and route the same way.
- **Standing rules:** "always `--force-with-lease`", "never amend after pushing", "that `gh` flag is broken in v2".
- **Requests to remember a way of working:** "remember that we use squash merges here".
- **Reports of a recurring problem:** "builds in worktrees start from scratch", "the disk filled up again".

Route a lesson the same way before writing any memory about how to work, whatever prompted it.

**The hook:** in Claude Code, the `coding-agent-skills-hooks` plugin's `scripts/memory-write-reminder.sh` lets a session's first Write or Edit under `~/.claude/projects/*/memory/` go ahead and reminds it to load this skill; a memory written through Bash isn't seen.

These stay memory material, since they are about the user or the moment rather than how to work:

- **Who the user is:** role, expertise, name. A personal choice about how one skill's output or workflow should look is different: it goes in that skill's preferences file ([Anyone, or a personal choice](#anyone-or-a-personal-choice)).
- **Time-bound project state:** who is on what, deadlines, incidents, sprint goals.
- **Pointers:** a Linear project, a dashboard URL, a Slack channel.
- **One-off task instructions:** "save build output to /tmp/foo".

## The routing table

Ask the questions in order and take the first row whose question the lesson answers yes. Rows sharing a step split one question by what the lesson is.

| Step | Layer                              | What decides it                                                                                                                                                                                       | What the session does                                                                                                      |
| ---- | ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| 1    | User-level preferences file        | A fact about this machine or this user that a skill reads as a setting: `/usr/bin/trash` for ad-hoc deletes on macOS, a terminal width, a push mode.                                                  | Draft the entry for that skill's user-level preferences file, landed through the machine configuration.                    |
| 1    | Machine configuration              | Any other fact about this machine or this user: a Nix setting such as `min-free` or `max-jobs`, an installed tool, git config, managed settings, a scheduled job, the global instructions.            | Propose a plan node in the machine configuration repository.                                                               |
| 2    | GitHub settings (github-config)    | A setting GitHub holds: branch deletion on merge, rulesets, merge methods, a token that acts across repositories.                                                                                     | Propose a plan node in the GitHub settings repository.                                                                     |
| 3    | The repository's flake             | Must hold for every build of one repository, by anyone, and no second repository would copy it: a check, a dev shell command, the toolchain.                                                          | Propose a plan node in that repository.                                                                                    |
| 4    | Shared dev shell module            | The same in every repository's dev shell: skills reconciled, a standard command, where a language's build cache goes, such as Cargo's target directory, so a new worktree doesn't build from scratch. | Propose a plan node in the module's repository.                                                                            |
| 5    | Command-line program               | An action more than one caller performs (a runner, a hook, a person), runnable without Nix: `worktrees finish`.                                                                                       | Propose a plan node in the repository that owns the subject, or a new repository's node where none does.                   |
| 6    | Plugin hook or Safety Net rulebook | An agent must be held to it, and a path, a command pattern or a script decides it; it calls the step 5 program where there is one, and starts at `remind`.                                            | Propose a plan node in the repository whose plugin carries the hook or rulebook.                                           |
| 7    | Plugin hook on a Claude Code event | It happens at a moment only Claude Code sees: session start, subagent start, worktree creation.                                                                                                       | Propose a plan node in the repository whose plugin carries the hook.                                                       |
| 8    | Mod                                | Something the user looks at: a pane, a band, the status line.                                                                                                                                         | Propose a plan node in the mod's repository.                                                                               |
| 9    | Skill, or its project preferences  | It needs judgement: when to do something, how to use a tool, a style, a heuristic, a gotcha.                                                                                                          | Draft the skill edit ([Which skill, if any](#which-skill-if-any)), or the project preferences entry for a personal choice. |
| 10   | `AGENTS.md`                        | A fact about one project that an agent needs before reading anything: what the repository is, its commands by name.                                                                                   | Draft the edit, committed in the project.                                                                                  |
| 10   | Memory                             | Otherwise: a fact about one project on this machine that nothing else can hold.                                                                                                                       | Write the memory.                                                                                                          |

- **A lesson about one repository can still be every repository's:** a repository's flake never owns logic a second repository would copy, so a lesson raised in one repository that every repository's dev shell would need answers no at step 3 and yes at step 4.
- **A hook needs a decider:** step 6 holds only where a path, a command pattern or a script can tell a breach from a pass. A lesson that needs judgement to apply goes on to step 9, even when the user says "make it a hard rule".
- **Machine facts stay out of skills:** a macOS path, a core count or a vault name answers yes at step 1, never at step 9, so a skill stays portable.
- **A skill or `AGENTS.md` never restates** what a lower layer holds; it names the layer: the command, the check, the hook.

## Two layers at once

A lesson often has a why and a mechanism: arming a pull request watcher after each push needs a rule about when, and a hook after `git push` makes it hold. Route each part through the table, then propose both together:

- **The mechanism** gets its plan node, by the row it answers yes to.
- **The why** gets its skill edit, and that edit names the mechanism's node, by its title and the repository it is proposed in, never repeating its logic. Once the node is implemented, the skill names the hook, command or check that implemented it instead.

## A proposed plan node

For every layer other than a skill, a preferences file, `AGENTS.md` and memory, the session proposes a plan node rather than a line of text, since a hook, a tool or a dev shell setting is a change with tests. Write it as `coding-agent-plans-as-graph` says:

- **Where:** `agents/plans/open/<id>.md` in the owning repository, or in the open folder of the plan it belongs to there.
- **Frontmatter:** `state: proposed`, since only the user approves a node; `kind: implementation`; `part-of` the end state it serves where that repository's plans have one; `touches` naming the repository.
- **Title:** what will be true once it is done, such as "Every worktree's dev shell shares the Cargo target directory".
- **Body:** the rule as it stands, which step of the routing table placed it and why, the change, and a Check section a later session can run.

## Which skill, if any

For a lesson at step 9, scan the skill listing, and the collections the user has installed, for its home:

- **Direct match:** a skill covers the topic, and the lesson refines it or adds a gotcha or an edge case. Pushback on commit subject length extends `git-hygiene-commit-message-format`.
- **Adjacent match:** no skill names the lesson, but one is its natural home. A rule about pull request titles goes in `github-hygiene-pull-request-mirrors-commit`, though its text doesn't say it yet.
- **No match:** fall back to a memory, with a `candidate-for-future-skill: <topic>` line in its body, so a later session can promote it once related lessons gather. One lesson doesn't earn a new skill.

When two skills fit, prefer the narrower one.

## Anyone, or a personal choice

Once you know the skill, decide which of its two homes the lesson goes in:

- **Right for anyone using the skill:** edit the skill. A gotcha, a missing edge case, a rule every user would want: "that `gh` flag is broken in v2", "a Decide option names what it acts on".
- **A personal choice:** the skill's preferences file. A wording, a glyph, an order or a default another user might reasonably not pick: "sort the lists Done, Waiting, Todo", "use squash merges here".

| Preferences file | Path                                                   | Holds                    | Written by                                                                         |
| ---------------- | ------------------------------------------------------ | ------------------------ | ---------------------------------------------------------------------------------- |
| User             | `~/.agents/skills/<skill-name>.preferences.md`         | a choice for everywhere  | the machine configuration, such as Home Manager; propose the change to it (step 1) |
| Project          | `<project>/.agents/skills/<skill-name>.preferences.md` | a choice for one project | an edit in the project, committed with the change it goes with                     |

A project's file overrides the user's, and the user's overrides the skill's defaults; `coding-agent-skill-references` has the full layout. When unsure which kind a lesson is, name both homes in the proposal and let the user pick.

## The proposal

Never edit or write silently. Show the proposal first, then ask through the structured-question tool, as `coding-agent-questions-as-first-class-prompts` says, whether to capture it that way:

```text
That belongs in <layer> (step <n>: <its question>), not memory.
For `<skill-name>`, under "<section heading>":

    <draft text, 1–3 sentences, in the skill's voice>

For <repository>, a proposed plan node agents/plans/open/<id>.md:

    <title, and the body's rule, change and check in a few lines>
```

- **Name the layer and the step** that placed it, so the user can disagree with the routing, not just the wording.
- **Quote the real section heading,** not "a section about X".
- **Draft the real sentences:** "I'd add a note about X" gives the user nothing to judge.
- **Match the target's voice:** terse and imperative, no hedging, no first person.
- **State the rule as it now stands:** leave out who asked, when, their words and the incident behind it. That history goes in the commit message that lands the edit, as `git-hygiene-no-history-in-tracked-files` says.
- **Two good homes:** name both and ask which.

## Where the edit lands

Once the user accepts the wording, ask where it lands, offering only the paths that exist for the target's repository: the skill's, the project's for `AGENTS.md`, or the owning repository for a plan node. A personal choice skips this: it goes in the preferences file.

1. **Upstream pull request:** always available. Branch off the repository upstream, apply the edit or add the node, push and open a pull request. The only path when the repository on disk is unknown, or when the user doesn't control it.
2. **Edit the repository on disk:** only when its location is known. Edit the `SKILL.md` or `AGENTS.md` in place, or write the node and run the plan script's `check` and `overview` there, for the user to commit.
3. **A proposal file in the repository on disk:** only when its location is known. Write the suggested change to `proposals/<topic>.md`, leaving the target alone, for a user who wants to think it over or batch several. A plan node needs no proposal file, since `state: proposed` already is one.

The location is known when, checking in order:

- the working directory is inside the repository;
- a memory or this skill's preferences name the checkout's path;
- the user named the path this session;
- an environment hint, such as the IDE's workspace root, matches the repository's path.

Otherwise it is unknown: offer only the pull request, and say that the on-disk paths are missing because the location isn't known, so the user can give it. Never guess a path.

## Edge cases

- **Halfway through writing a memory:** stop and route the lesson instead. Don't write the memory "just in case"; the same lesson in two places drifts.
- **A memory written earlier this session** for a lesson another layer owns: once that edit or node is approved, offer to remove the memory.
- **"Save it as a memory anyway":** write the memory, with a line saying the user wanted it as a memory, so later sessions don't re-route it, and don't propose the other layer again.
- **The user wants both:** the skill edit or plan node is the record, and the memory only points at it with a `[[name]]` link, never restating the rule.
- **A layer the user doesn't control,** such as a vendor's skill or plugin, or a public collection: the on-disk paths don't apply even with the location known. Offer the upstream pull request, then a memory if the user declines.
- **The lesson contradicts its target** rather than extending it: name the conflict before editing, "`<skill>` says X; you've said Y. Update it, or treat this as a one-off?", and let the user decide.
- **Unsure between two steps:** name both layers, with the question each answers, and ask.

## Your preferences

!`cat "$(dirname "${CLAUDE_SKILL_DIR}")/coding-agent-route-feedback-to-skills-over-memory.preferences.md" "${CLAUDE_PROJECT_DIR}/.agents/skills/coding-agent-route-feedback-to-skills-over-memory.preferences.md" 2>/dev/null || true`

If your agent doesn't run the line above, read these files yourself if they exist: `coding-agent-route-feedback-to-skills-over-memory.preferences.md` next to this skill's folder, then `.agents/skills/coding-agent-route-feedback-to-skills-over-memory.preferences.md` in the project.
A project's file overrides the user's, and the user's overrides this skill's defaults.

The keys this skill reads, with its own defaults:

```markdown
- Machine configuration repository: ask the user
- GitHub settings repository: ask the user
- Skill repositories by subject: ask the user
```

## Related skills

When one of these applies and it's in your skill listing, load it without asking.
If it isn't in your listing, tell the user which skill is missing and ask whether to install it from the same collection this skill came from; don't apply it from memory.

- `coding-agent-plans-as-graph`: how a proposed plan node is written, and the `check` and `overview` run after adding one.
- `coding-agent-skill-references`: how a skill names other skills, and where its user and project preferences files live.
- `coding-agent-questions-as-first-class-prompts`: the proposal and the question of where the edit lands go through the structured-question tool.
- `agent-output-session-recap`: when recapping a session, a course correction that led to a skill edit or plan node rather than a memory gets its own 🗣 line.
- `git-hygiene-commit-message-format`: commit message rules, the example of a direct match.
- `git-hygiene-no-history-in-tracked-files`: a tracked file states the current rule, and its history goes in the commit message.
- `github-hygiene-pull-request-mirrors-commit`: pull request titles and bodies mirror the commit, the example of an adjacent match.
