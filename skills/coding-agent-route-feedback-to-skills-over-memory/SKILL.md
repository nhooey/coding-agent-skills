---
name: coding-agent-route-feedback-to-skills-over-memory
description: Route a lesson about how the agent works into the right existing skill, or that skill's preferences file, before writing a memory. Propose the skill and section with draft wording, ask where the edit lands (an upstream pull request, an edit to the skill's repository on disk, or a proposal file there), and fall back to a memory, flagged as a candidate for a future skill, only when no skill fits. Use whenever the user corrects the agent ("stop doing X", "don't add Y"), sets a standing rule ("always Z", "from now on", "going forward"), confirms a non-obvious choice ("yes, that was right, keep doing it"), reports a tool gotcha ("that flag is broken, use this instead") or asks it to remember a way of working, and before writing any memory about how to work. Not for who the user is ("I'm a backend engineer"), time-bound project state ("we ship Thursday"), pointers to outside resources (a Linear project, a dashboard) or one-off task instructions ("save build output to /tmp/foo"), which stay memory material.
---

# Route feedback to skills before memory

_A lesson about how to work belongs in the skill on its topic, where every session and every user of the skill finds it; a memory is the fallback when no skill fits._

## Why a skill over a memory

- **Shared:** everyone who installs the skill gets the lesson; a memory helps one user.
- **Found where it belongs:** a commit rule sits in the commit skill, not among unrelated memories found only by recall.
- **Reviewed:** a skill edit goes through git, with its history in the commit message; a memory changes unseen.
- **Always in front of the agent:** a skill is in every session's listing; a memory fires only when recalled.

## When this applies

Whenever the user teaches the agent how to work, whether or not auto-memory is loaded:

- **Corrections:** "stop summarizing every response", "use `gh`, not `curl`, for that".
- **Confirmations** of a non-obvious choice: "yes, one bundled pull request was right here". Quiet approvals are easy to miss and route the same way.
- **Standing rules:** "always `--force-with-lease`", "never amend after pushing", "that `gh` flag is broken in v2".
- **Requests to remember a way of working:** "remember that we use squash merges here".

These stay memory material, since they are about the user or the moment rather than how to work:

- **Who the user is:** role, expertise, name. A personal choice about how one skill's output or workflow should look is different: it goes in that skill's preferences file ([Anyone, or a personal choice](#anyone-or-a-personal-choice)).
- **Time-bound project state:** who is on what, deadlines, incidents, sprint goals.
- **Pointers:** a Linear project, a dashboard URL, a Slack channel.

## Which skill, if any

Scan the skill listing, and the collections the user has installed, for the lesson's home:

- **Direct match:** a skill covers the topic, and the lesson refines it or adds a gotcha or an edge case. Pushback on commit subject length extends `git-hygiene-commit-message-format`.
- **Adjacent match:** no skill names the lesson, but one is its natural home. A rule about pull request titles goes in `github-hygiene-pull-request-mirrors-commit`, though its text doesn't say it yet.
- **No match:** fall back to a memory, with a `candidate-for-future-skill: <topic>` line in its body, so a later session can promote it once related lessons gather. One lesson doesn't earn a new skill.

When two skills fit, prefer the narrower one.

## Anyone, or a personal choice

Once you know the skill, decide which of its two homes the lesson goes in:

- **Right for anyone using the skill:** edit the skill. A gotcha, a missing edge case, a rule every user would want: "that `gh` flag is broken in v2", "a Decide option names what it acts on".
- **A personal choice:** the skill's preferences file. A wording, a glyph, an order or a default another user might reasonably not pick: "sort the lists Done, Waiting, Todo", "use squash merges here".

| Preferences file | Path                                                   | Holds                    | Written by                                                     |
| ---------------- | ------------------------------------------------------ | ------------------------ | -------------------------------------------------------------- |
| User             | `~/.agents/skills/<skill-name>.preferences.md`         | a choice for everywhere  | the user's Home Manager config; propose the change to it       |
| Project          | `<project>/.agents/skills/<skill-name>.preferences.md` | a choice for one project | an edit in the project, committed with the change it goes with |

A project's file overrides the user's, and the user's overrides the skill's defaults; `coding-agent-skill-references` has the full layout. When unsure which kind a lesson is, name both homes in the proposal and let the user pick.

## The proposal

Never edit silently. Show the proposal first, then ask through the structured-question tool, as `coding-agent-questions-as-first-class-prompts` says, whether to capture it that way:

```text
That's a refinement to `<skill-name>` rather than a memory. I'd add it
under "<section heading>" (or to its preferences file, for a personal
choice) as:

    <draft text, 1–3 sentences, in the skill's voice>
```

- **Quote the real section heading,** not "a section about X".
- **Draft the real sentences:** "I'd add a note about X" gives the user nothing to judge.
- **Match the skill's voice:** terse and imperative, no hedging, no first person.
- **State the rule as it now stands:** leave out who asked, when, their words and the incident behind it. That history goes in the commit message that lands the edit, as `git-hygiene-no-history-in-tracked-files` says.
- **Two good homes:** name both and ask which.

## Where the edit lands

Once the user accepts the wording, ask where it lands, offering only the paths that exist for this skill. A personal choice skips this: it goes in the preferences file.

1. **Upstream pull request:** always available. Branch off the skill's upstream repository, apply the edit, push and open a pull request. The only path when the skill's repository on disk is unknown, or when the user doesn't control the skill.
2. **Edit the repository on disk:** only when its location is known. Edit the `SKILL.md` in place, for the user to commit.
3. **A proposal file in the repository on disk:** only when its location is known. Write the suggested change to `proposals/<topic>.md`, leaving the skill alone, for a user who wants to think it over or batch several.

The location is known when, checking in order:

- the working directory is inside the collection's repository, with the skill under it;
- a memory names the checkout's path;
- the user named the path this session;
- an environment hint, such as the IDE's workspace root, matches the collection's path.

Otherwise it is unknown: offer only the pull request, and say that the on-disk paths are missing because the location isn't known, so the user can give it. Never guess a path.

## Edge cases

- **Halfway through writing a memory:** stop and propose the skill edit instead. Don't write the memory "just in case"; the same lesson in two places drifts.
- **A memory written earlier this session** for a lesson that fits a skill: once the skill edit is approved, offer to remove the memory.
- **"Save it as a memory anyway":** write the memory, with a line saying the user wanted it as a memory, so later sessions don't re-route it, and don't propose the skill edit again.
- **The user wants both:** the skill edit is the record, and the memory only points at it with a `[[skill-name]]` link, never restating the rule.
- **A skill the user doesn't control,** such as a vendor's or a public collection's: the on-disk paths don't apply even with the location known. Offer the upstream pull request, then a memory if the user declines.
- **The lesson contradicts the skill** rather than extending it: name the conflict before editing, "`<skill>` says X; you've said Y. Update the skill, or treat this as a one-off?", and let the user decide.

## Related skills

When one of these applies and it's in your skill listing, load it
without asking. If it isn't in your listing, tell the user which skill is
missing and ask whether to install it from the same collection this skill
came from; don't apply it from memory.

- `coding-agent-skill-references`: how a skill names other skills, and where its user and project preferences files live.
- `coding-agent-questions-as-first-class-prompts`: the proposal and the question of where the edit lands go through the structured-question tool.
- `agent-output-session-recap`: when recapping a session, a course correction that led to a skill edit rather than a memory gets its own 🗣 line.
- `git-hygiene-commit-message-format`: commit message rules, the example of a direct match.
- `git-hygiene-no-history-in-tracked-files`: a tracked file states the current rule, and its history goes in the commit message.
- `github-hygiene-pull-request-mirrors-commit`: pull request titles and bodies mirror the commit, the example of an adjacent match.
