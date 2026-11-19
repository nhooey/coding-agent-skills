# coding-agent-skills

A marketplace of coding-agent skills, packaged as a Nix flake. Each skill is a
directory under `skills/` with a `SKILL.md` and a `flake.nix`; the root flake
builds them all through agent-skill-flake. `plugins/` holds Claude Code mods,
and `agents/plans/` the project's plans.

## Build and test

```bash
nix develop      # the dev shell; installs the project's skills into .agents/skills/
nix fmt          # nixfmt over *.nix, prettier over *.md and *.yaml
nix flake check  # formatting, the hooks plugin's build and every test
```

In the dev shell, `skills-dev` runs the rest. `skills-dev test` runs every test
outside the sandbox, the same set as the `python-tests` and `shell-tests`
checks: pytest over the Python tests under `tests/` and `scripts/`, and bash
over each shell test under `tests/`. `skills-dev test python` or
`skills-dev test shell` runs one language's, and `skills-dev test <skill> ...`
the named skills' tests under `tests/`. `skills-dev mods check` validates,
type-checks and tests the mods under `plugins/`; `skills-dev mods --help` lists
the mod commands.

## Tests

A skill's folder holds only what it installs: its `SKILL.md`, its pages and its
`scripts/`. The tests of `skills/<skill>/scripts/` are in `tests/<skill>/`, each
language's run by its own tool. A Python test imports a script by its module
name, since `tests/conftest.py` puts the skill's `scripts/` on `sys.path`, and
finds the files beside it through that module's `__file__`. The skills' Python
scripts use only the standard library; the tests may use the libraries the dev
shell's Python has. agent-skill-flake's `skill-layout` check enforces both
rules, and that no two skills' scripts share a module name.

Run `nix fmt` and `nix flake check` before committing: no CI runs them on push,
so a formatting slip or a failing test is otherwise caught by nothing.
Run `skills-dev mods check` too when a change touches `plugins/`, since
`nix flake check` doesn't cover the mods.

`skill-checks.toml` holds the settings that agent-skill-flake's `skill-layout`
and `skill-description` checks read. The skills it lists under `trigger-first`
open their descriptions on `Load ` and keep them within 500 characters. It
also turns on `tests-name-skills`, so every folder directly under `tests/`
names a skill.
