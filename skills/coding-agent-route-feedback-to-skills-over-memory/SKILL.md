---
name: coding-agent-route-feedback-to-skills-over-memory
description: Use this skill whenever the user teaches the agent how to work — corrections ("stop doing X", "don't add Y"), standing rules ("always Z", "from now on", "going forward"), confirmations of a non-obvious choice ("yeah that was right, keep doing that"), tool/command gotchas ("that flag is broken, use this workaround"), or save-this-behavior requests ("remember to run X before Y"). Any time the user is shaping HOW you operate — workflow habits, commit/PR practices, debugging heuristics, tool usage, always-or-never rules — invoke BEFORE writing a memory. It routes the lesson into the right existing skill with draft wording, falling back to memory only if no skill fits. Do NOT trigger on user identity ("I'm a backend engineer"), time-bound project state ("we ship Thursday"), external pointers (Linear, dashboards), or one-shot task instructions ("save build output to /tmp/foo") — those stay memory material.
---

# Route behavioral feedback into skills before memory

The auto-memory reflex is to save a memory the moment the user gives
feedback. That reflex is usually wrong for behavioral lessons. Most
"how to work" corrections live better in a **skill** than in a per-user
memory file:

- **Skills are shared.** Anyone with the marketplace installed inherits
  the lesson; a memory only helps the one user it was saved under.
- **Skills are domain-organized.** A commit-hygiene rule lives in the
  commit-hygiene skill, where future-you will look for it. A memory file
  sits next to unrelated memories and is found only by description-based
  recall.
- **Skills are versioned in git.** Edits go through PRs, get reviewed,
  and carry their own history. Memories mutate silently.
- **Skills survive context resets.** A memory only fires if the agent
  thinks to read memory; a skill in the available-skills list is
  surfaced to every session automatically.

Your reflex should be: _"can this lesson go in a skill?" → if yes,
propose the edit → only fall back to memory if no skill fits._

## When this applies

Trigger on any moment the user is teaching the agent _how to work_ —
whether or not the auto-memory system happens to be loaded. Concrete
signals:

- **Corrections** to the agent's approach: _"don't write memories,
  write to the skill instead,"_ _"stop summarizing every response,"_
  _"use `gh` not `curl` for that."_
- **Confirmations** of a non-obvious choice the agent made: _"yes, one
  bundled PR was right here,"_ _"keep doing it that way,"_ — quiet
  approvals are easy to miss and deserve the same routing.
- **Workflow rules** that generalize beyond this session: _"always
  `force-with-lease`,"_ _"never amend after pushing,"_ _"that `gh` flag
  is broken in v2."_
- **Explicit save requests** about behavior: _"remember that we use
  squash merges here."_

Don't trigger on these — they are genuine memory material:

- **User identity facts** — role, expertise, name, personal
  preferences-about-them. These are about _this user_; they don't
  generalize and don't belong in a sharable skill.
- **Time-bound project state** — who is working on what, deadlines,
  incident history, current sprint goals. These are local and decay
  fast.
- **External references** — Linear project names, dashboard URLs, Slack
  channel handles. These are pointers, not behaviors.

The line worth holding: a skill captures _how to do work_; a memory
captures _who the user is, what they're working on, or where to look_.

## The check: which skill, if any?

Before writing anything, scan the available skills (the
`available-skills` system reminder, plus any marketplaces the user has
installed) for a topical home.

- **Direct match.** A skill already covers this topic; the lesson is a
  refinement, a new gotcha, or a missing edge case. Example: user
  pushes back on commit subject length → already covered by
  `git-hygiene-commit-message-format`; the lesson extends that skill.
- **Adjacent match.** No skill names the lesson directly, but one is
  the natural home. Example: a rule about PR title rewording → land it
  in `github-hygiene-pr-mirrors-commit` even though its current text
  doesn't yet say this.
- **No match.** The lesson is novel and doesn't fit any existing skill.
  Fall back to memory — but flag the entry as a future-skill candidate
  so a later session can promote it once a few related lessons
  accumulate. One lesson does not earn a new skill; skills earn their
  existence by clustering related rules.

When two skills both fit, prefer the more specific one. A lesson that
fits both a broad and a narrow skill belongs in the narrow one; the
broad skill catches it via cross-reference if needed.

## The verbal proposal

Don't silently edit. State the proposal in plain text and let the user
redirect before any file changes:

```
That sounds like a refinement to `<skill-name>` rather than a memory.
I'd add it under "<section heading>" as:

    <draft text, 1–3 sentences, in the skill's existing voice>

Want me to capture it that way?
```

Keep the proposal concrete:

- Quote the actual section heading; don't say "I'd add a section about X."
- Draft the actual sentences. "I'd add a note about X" is too vague
  for the user to evaluate — they need to see the wording.
- Match the surrounding skill's voice — terse imperative, no hedging,
  no first-person.

If the lesson reasonably fits in two places, name both and ask which
the user prefers. Don't pick blindly.

## After the user accepts the wording: how to persist

The wording is one decision; _where the edit lands_ is a separate one.
Ask the user which persistence path they want — but **only offer paths
that actually exist for this skill.** The available paths depend on
whether you know the skill's on-disk repo location:

1. **Upstream PR** — always available. Branch off the skill's upstream
   repo, apply the edit, push, open a PR. Use this when the on-disk
   location is unknown, when the user prefers review-then-merge, or
   when the skill belongs to a marketplace the user doesn't directly
   control.
2. **Edit the on-disk repo directly** — only offer when the on-disk
   location is known. Edit `SKILL.md` in place; the user commits
   later. Faster than a PR, no review round-trip, fine for skills the
   user owns.
3. **Markdown proposal in the on-disk repo** — only offer when the
   on-disk location is known. Write a `proposals/<topic>.md` (or
   similar) capturing the suggested change without modifying the skill
   yet. Useful when the user wants to think it over or batch several
   proposals before applying them.

### Signals that tell you the on-disk location

Check, in order:

- The current working directory is inside (or below) the marketplace's
  repo — e.g., the agent is operating from
  `/Users/<user>/git/.../<marketplace>/...` and the skill file lives
  under that path.
- A memory entry points at the marketplace location (e.g., a `reference`
  memory naming the checkout path).
- The user has just mentioned the path in this session.
- An environment hint (e.g., the IDE's open workspace root) matches a
  marketplace path.

If none of these resolve, treat the on-disk location as unknown and
offer only the upstream-PR option. Don't guess a path; an unfounded
on-disk offer is worse than not offering it.

### Asking the question

When the on-disk location _is_ known, ask all three:

```
How do you want this to land?
  1. Open a PR upstream (against <upstream-repo-url>)
  2. Edit the on-disk repo at <path>
  3. Drop a proposal markdown file at <path>/proposals/<topic>.md
```

When it isn't, ask only one — and say why:

```
I don't have the skill's on-disk repo location handy, so the only
path I can take is a PR against <upstream-repo-url>. Want me to open
one?
```

Saying _why_ the on-disk options are missing gives the user the chance
to provide the path if they want.

## Mid-save pivot

If you catch yourself partway through writing a memory (drafted the
body, haven't written the file yet), stop and pivot to the skill
proposal. Don't write the memory "just in case" — two-stage saves
("write memory, maybe move it") strand the same lesson in two places
and the duplication causes drift.

If you already wrote a memory earlier in _this same session_ for a
lesson that turns out to fit a skill, offer to remove the memory once
the skill edit is approved. Don't leave the rule in both places.

## Edge cases

- **User says "save as a memory anyway."** Respect the override. Write
  the memory and don't re-propose the skill edit for that lesson.
  Add a short note in the memory body explaining _why_ the user
  preferred memory ("user wanted this scoped to themselves") so later
  sessions don't try to re-route the same item.
- **User wants both.** Land the skill edit as the primary record, then
  save a thin memory that _points to_ the skill via a `[[skill-name]]`
  link rather than restating the rule. The memory is an index entry,
  not a duplicate.
- **Right skill is read-only / upstream-only.** If the natural home is
  a skill the user doesn't control (a vendor skill, public
  marketplace), the on-disk edit and on-disk markdown-proposal options
  aren't available even if the location is known. Offer the upstream
  PR; fall back to memory if the user doesn't want to PR upstream.
- **Lesson contradicts an existing skill.** If the user's feedback
  conflicts with what a skill currently says (rather than extending
  it), surface the conflict before editing: _"the `<skill>` skill
  currently says X; your feedback says Y. Update the skill, or treat
  this as a one-off exception?"_ Don't silently overwrite skill
  guidance based on a single correction.
- **No skill fits, but one _should_ exist.** If the lesson is broadly
  applicable but no skill covers the topic, write the memory with a
  `candidate-for-future-skill: <topic>` line in the body. Don't spin
  up a new skill on the spot for one lesson; wait for the cluster.

## Cross-references

- `coding-agent-session-recap` — when recapping a session, a course
  correction that resulted in a skill edit (rather than a memory write)
  deserves its own 🗣 line; the routing decision is part of the lesson
  the recap should preserve.
