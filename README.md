# coding-agent-skills

A marketplace of coding-agent skills, packaged as a Nix flake.

Each skill is a self-contained directory under [`skills/`](skills/) with a
`SKILL.md` (frontmatter + instructions) that an agent loads on demand. The flake
builds every skill into an installable package and exposes apps that reconcile
an agent's skill directory to exactly the set this flake declares. Skills are
built by [`agent-skill-flake`](https://github.com/nhooey/agent-skill-flake),
which turns skill directories into flakes and aggregates them.

These skills shape _how a coding agent works_ — workflow habits, prompt
ergonomics, and where lessons get stored — rather than what it builds.

## Skills

| Skill                                                                                                                    | What it does                                                                                                                                                   |
| ------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`coding-agent-questions-as-first-class-prompts`](skills/coding-agent-questions-as-first-class-prompts/SKILL.md)         | Routes any question for the user through the agent's structured-question primitive (e.g. `AskUserQuestion`) instead of free-text prose that waits for a reply. |
| [`coding-agent-route-feedback-to-skills-over-memory`](skills/coding-agent-route-feedback-to-skills-over-memory/SKILL.md) | When the user teaches the agent how to work, routes the lesson into the right existing skill with draft wording, falling back to memory only if no skill fits. |
| [`coding-agent-session-recap`](skills/coding-agent-session-recap/SKILL.md)                                               | Renders a session summary as alternating 🗣 user / 🤖 assistant one-liners, one sentence per turn, no tool-call noise.                                         |

## Install

Each skill is an output package, plus an aggregate `default` that bundles them all.

```bash
# Preview what installing every skill would change, without writing anything
nix run github:nhooey/coding-agent-skills#preview

# Install all skills into the agent's skill directory
nix run github:nhooey/coding-agent-skills#install

# Converge the skill directory to exactly this flake's declared set
nix run github:nhooey/coding-agent-skills#reconcile

# Remove the skills this flake installed
nix run github:nhooey/coding-agent-skills#uninstall
```

Other apps: `reap` (remove garbage-collected/broken entries this flake owns) and
`purge` (remove every entry this flake's lineage owns, live or broken).

Package outputs:

- `agent-skills-nhooey-coding-agent-all` — the aggregate of every skill (also `default`)
- `agent-skill-nhooey-coding-agent-questions-as-first-class-prompts`
- `agent-skill-nhooey-coding-agent-route-feedback-to-skills-over-memory`
- `agent-skill-nhooey-coding-agent-session-recap`

## Development

```bash
nix develop      # enter the dev shell; run `menu` to list commands
nix fmt          # nixfmt over *.nix, prettier over *.md / *.yaml
nix flake check  # runs the treefmt check (fails on any unformatted file)
```

The dev shell provides `check`, `fmt`, and `update-flake` commands plus
`reap-skills` / `update-skills-devshell`. Its own toolchain skills (the git/GitHub
pack and skillspkgs' `authoring` combination) live in the runtime
[`skills-devshell/`](skills-devshell/) sub-flake and are invoked at run time, so
the root flake stays a leaf with zero skill inputs in its lock.

## Layout

```
skills/                  one directory per skill (SKILL.md + per-skill flake.nix)
skills-devshell/         runtime sub-flake supplying the dev shell's own skills
source.nix               the upstream owner, shared by the root and every skill flake
flake.nix                builds skills via agent-skill-flake; wires the dev shell + treefmt
garnix.yaml              Garnix CI scope (Linux packages + the default dev shell)
```

## Authoring a skill

Add a directory under `skills/<name>/` containing a `SKILL.md` and a `flake.nix`
that calls `agent-skill-flake.lib.mkSkillFlake` with `source = import
../../source.nix`. The root flake's `mkAllSkillsFlake` picks up every directory
under `skills/` automatically, so no central registry edit is needed. Run
`nix fmt` and `nix flake check` before committing.

## CI

[Garnix](https://garnix.io) builds the Linux packages and the default dev shell
on every push (see [`garnix.yaml`](garnix.yaml)).
