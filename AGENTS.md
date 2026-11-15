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
check-mods       # in the dev shell: validate, type-check and test the mods under plugins/
```

Run `nix fmt` and `nix flake check` before committing.
