# coding-agent-skills

A marketplace of coding-agent skills, packaged as a Nix flake. Each skill is a
directory under `skills/` with a `SKILL.md` and a `flake.nix`; the root flake
builds them all through agent-skill-flake. `plugins/` holds Claude Code mods,
and `agents/plans/` the project's plans.

## Build and test

```bash
nix develop      # the dev shell; installs the project's skills into .agents/skills/
nix fmt          # nixfmt over *.nix, prettier over *.md and *.yaml
nix flake check  # formatting and the skills' script tests
```

In the dev shell, `skills-dev` runs the rest; `skills-dev --help` lists its
commands. `skills-dev test` runs the skills' script tests outside the sandbox,
and `skills-dev mods check` validates, type-checks and tests the mods under
`plugins/`.

Run `nix fmt` and `nix flake check` before committing: no CI runs them on push,
so a formatting slip or a failing script test is otherwise caught by nothing.
Run `skills-dev mods check` too when a change touches `plugins/`, since
`nix flake check` doesn't cover the mods.
