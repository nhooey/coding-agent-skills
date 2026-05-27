# Plan: `coding-agent-plan-mode-conventions` skill

## Context

Plan-mode behavior in this user's setup currently has three friction points:

1. **Plan files land in the global `~/.claude/plans/` directory**, not co-located with the project they describe. That
   makes plans hard to find later, hard to share with teammates, and impossible to gitignore per-project.
2. **When the user asks a question during plan mode**, the agent often folds the answer into a plan revision or treats
   the question as a request to keep iterating, instead of just answering and then offering plan modification as a
   discrete next step.
3. **Plan markdown wraps at ~80 characters** (the same convention used in SKILL.md bodies in this repo), but plans
   frequently contain code paths, function signatures, and step-by-step prose that read better with more room.

This plan adds a single skill to the marketplace that establishes conventions for all three. The skill is agent-neutral
in tone (matching the existing `coding-agent-*` skills), even though plan mode itself is a Claude Code feature today —
other coding agents may grow equivalent flows, and the conventions transfer.

Note on *this* plan file: the in-flight Plan Mode session originally wrote it to `~/.claude/plans/` because that is the
current plan-file location; per the user's correction, it now lives at this project-local
`.claude/plans/add-plan-mode-conventions-skill.md` path — exactly the convention the skill prescribes. This file follows
the 120-character wrap rule the skill prescribes.

## Skill design

**Name:** `coding-agent-plan-mode-conventions`

**Location:** `/Users/nhooey/git/github/nhooey/coding-agent-skills/skills/coding-agent-plan-mode-conventions/`

**Files (two, matching every other skill in this repo):**

- `SKILL.md` — frontmatter + body
- `flake.nix` — minimal wrapper using `flake-skills.lib.mkSkillFlake`, mirroring
  `skills/coding-agent-session-recap/flake.nix`

**No root `flake.nix` edit needed.** The repo's root flake uses `flake-skills.lib.mkAllSkillsFlake` with
`skillsDir = ./skills`, which directory-scans. Dropping a new skill directory in is enough.

## SKILL.md content (four rules)

### Rule 1 — write plan files into the project's `.claude/plans/`

- When the agent needs to write a plan file (Plan Mode, or any other planning workflow), write it under
  `<project-root>/.claude/plans/` rather than any global location.
- "Project root" = the nearest enclosing git repository working tree. If the current working directory is not inside a
  git repo, fall back to the current working directory.
- Create `.claude/` and `.claude/plans/` if they don't exist. Use `mkdir -p` semantics — idempotent, no error if either
  already exists.
- Also recommend adding `.claude/plans/` to the project's `.gitignore` if not already present. The skill should:
  - On first plan write in a repo where `.claude/plans/` is not gitignored, surface a one-line note ("Plan files default
    to gitignored — want me to add `.claude/plans/` to `.gitignore`?") and let the user opt in.
  - Not silently edit `.gitignore`. The user has to say yes.

### Rule 2 — answer-then-offer when the user asks a question in plan mode

- When the user asks a question (factual, clarifying, "what would happen if…", "why did you pick X") during plan mode,
  the agent must:
  1. **Answer the question directly first.** Don't immediately convert the question into a plan revision.
  2. **Then explicitly offer plan modification as a first-class structured prompt** — in Claude Code, this is an
     `AskUserQuestion` call with discrete options, not a free-form "want me to update the plan?" sentence at the end of
     prose. Other agents should use their equivalent structured-question mechanism.
- The structured offer should present, at minimum, these options:
  - **Modify the plan** to reflect the answer
  - **Leave the plan as-is** — answer was informational only
  - **Discuss further** before deciding
- Rationale: free-form trailing questions get skimmed and missed; a structured prompt forces an intentional choice and
  keeps the plan file's state aligned with the user's intent.
- Do **not** trigger this pattern for direct requests to edit the plan ("change the plan to use Postgres") — those are
  instructions, not questions, and should just be applied.

### Rule 3 — wrap plan markdown at 120 characters, not 80

- Plan files written under `.claude/plans/` use a 120-character soft wrap, not the 80-char wrap used in SKILL.md bodies
  in this marketplace.
- Code fences and URLs are exempt as usual.
- This applies only to plan markdown. SKILL.md and other documentation in this repo keep their existing conventions.

### Rule 4 — move implemented plans into `.claude/plans/implemented/`

- Once the work a plan describes has been implemented and merged, move the plan file from `.claude/plans/<name>.md` to
  `.claude/plans/implemented/<name>.md`. The top-level `.claude/plans/` is for active/upcoming work only.
- Use `git mv` if the plan is tracked, plain `mv` otherwise. Do not edit the plan's contents as part of the move — the
  file is preserved verbatim as the design artifact, just relocated.
- Create `.claude/plans/implemented/` on demand with `mkdir -p` semantics. The directory is not pre-created by Rule 1.
- "Implemented" = the code or skill the plan describes has landed on the default branch (merged, not just PR-open). For
  a multi-PR plan, move only after the final PR merges.
- Trigger points where the agent should propose the move: immediately after merging the PR that completes the plan, or
  when the user asks "what's still in-flight?" and the agent notices a plan whose described work is already shipped.
  Surface a one-line proposal ("This plan looks implemented — move to `.claude/plans/implemented/`?"); do not move
  silently.

## SKILL.md voice & structure

Match the existing skills (`coding-agent-route-feedback-to-skills-over-memory`, `coding-agent-session-recap`):

- YAML frontmatter with `name` and a single-paragraph `description` that fires on plan-mode triggers.
- Body wrapped at ~72 characters (the SKILL.md convention — distinct from the 120-char rule the skill *describes* for
  plan files).
- Section structure: short intro → "When this skill applies" → one subsection per rule → "Edge cases" → "Cross-
  references" (link `coding-agent-route-feedback-to-skills-over-memory` since both touch agent-user interaction).
- Imperative voice, no first-person, no hedging.

## flake.nix content

Copy `skills/coding-agent-session-recap/flake.nix` verbatim, changing:

- `description` — to `"coding-agent-plan-mode-conventions: Coding-agent skill — write plan files to the project's
  .claude/plans/ directory, wrap at 120 chars, answer-then-offer when the user asks a question mid-plan, and move
  implemented plans into .claude/plans/implemented/"`
- `skillName` — to `"coding-agent-plan-mode-conventions"`

`src = ./.` and the input declarations are unchanged.

## Files to create

- `skills/coding-agent-plan-mode-conventions/SKILL.md`
- `skills/coding-agent-plan-mode-conventions/flake.nix`

No other files modified. The root `flake.nix` picks the new skill up via directory scan.

## Verification

1. **Flake builds.** From the repo root, run `nix flake check` (or `nix build .#skills.coding-agent-plan-mode-conventions`
   if the marketplace exposes per-skill outputs). The new skill should evaluate without error.
2. **Skill is discoverable.** Confirm the skill name appears in any skill-listing output the marketplace produces (e.g.,
   `nix flake show`).
3. **Manual behavioral check.** In a fresh Claude Code session inside a git repo:
   - Enter plan mode and confirm the agent writes the plan file to `<repo>/.claude/plans/` and creates the directory if
     missing.
   - Ask a clarifying question mid-plan-mode and confirm the agent answers, then issues a structured
     `AskUserQuestion`-style prompt with the modify/leave/discuss options.
   - Inspect a generated plan file and confirm prose wraps near 120 chars rather than 80.
   - Confirm the agent surfaces the gitignore suggestion exactly once per repo and does not silently edit `.gitignore`.
   - After merging a PR that completes a plan, confirm the agent proposes moving the plan file to
     `.claude/plans/implemented/` rather than moving silently or leaving it in place.
4. **Voice and format spot-check.** Diff the new SKILL.md against `coding-agent-route-feedback-to-skills-over-memory`
   and confirm comparable structure, voice, and line-length (~72 chars).
