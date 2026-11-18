# coding-agent-skills

A marketplace of coding-agent skills, packaged as a Nix flake.

Each skill is a self-contained directory under [`skills/`](skills/) with a
`SKILL.md` (frontmatter + instructions) that an agent loads on demand. The flake
builds every skill into an installable package and exposes apps that reconcile
an agent's skill directory to exactly the set this flake declares. Skills are
built by [`agent-skill-flake`](https://github.com/nhooey/agent-skill-flake),
which turns skill directories into flakes and aggregates them.

These skills shape _how a coding agent works_ — workflow habits, prompt
ergonomics, and where lessons get stored — rather than what it builds. Skills
for the shape of an agent's output in isolation, such as a session recap, live
in agent-output-skills.

## Skills

| Skill                                                                                                                    | What it does                                                                                                                                                                                                                                                  |
| ------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`coding-agent-browser-selection`](skills/coding-agent-browser-selection/SKILL.md)                                       | Before any Claude in Chrome work, finds which browser app and window the session drives, with a bundled macOS script, and switches until it matches the user's preferences.                                                                                   |
| [`coding-agent-headless-in-checkout`](skills/coding-agent-headless-in-checkout/SKILL.md)                                 | Runs a prompt as a headless Claude Code session inside one git checkout, with its own skills and Nix environment, in a worktree, in a new session or a fork of the checkout's last one, and reports how it ended; a caller fans it out across many checkouts. |
| [`coding-agent-plans-as-graph`](skills/coding-agent-plans-as-graph/SKILL.md)                                             | Keeps plans as a graph of Markdown nodes in `agents/plans/open/` and `closed/`, with states, typed links and a generated overview of what's in progress, ready, blocked and proposed.                                                                         |
| [`coding-agent-kanban-turn-responses`](skills/coding-agent-kanban-turn-responses/SKILL.md)                               | Shapes every response as kanban lists: one-line emoji progress updates between tool calls, and a final response of Done/Pending/Waiting/Answers/Review/Todo/Decide lists closing on what earlier turns left open.                                             |
| [`coding-agent-questions-as-first-class-prompts`](skills/coding-agent-questions-as-first-class-prompts/SKILL.md)         | Routes any question for the user through the agent's structured-question primitive (e.g. `AskUserQuestion`) instead of free-text prose that waits for a reply.                                                                                                |
| [`coding-agent-route-feedback-to-skills-over-memory`](skills/coding-agent-route-feedback-to-skills-over-memory/SKILL.md) | When the user teaches the agent how to work, routes the lesson into the right existing skill with draft wording, falling back to memory only if no skill fits.                                                                                                |
| [`coding-agent-scratchpad-scripts`](skills/coding-agent-scratchpad-scripts/SKILL.md)                                     | Keeps edits in the Edit and Write tools, one-off checks inline and only named data in the scratchpad; anything run twice goes to `shell-hygiene-commands-as-cli-tools`.                                                                                       |
| [`coding-agent-session-build-limits`](skills/coding-agent-session-build-limits/SKILL.md)                                 | A SessionStart hook that gives every Claude Code session a fixed share of the machine for make, cargo, Rust tests, pytest-xdist and the JVM, leaving variables the user already set alone.                                                                    |
| [`coding-agent-skill-references`](skills/coding-agent-skill-references/SKILL.md)                                         | How a skill names other skills (bare names, a closing Related skills section) and reads its preferences files; its Python scripts use the stdlib, its tests sit in `tests/<skill>/`, run through Nix.                                                         |
| [`coding-agent-use-existing-libraries-and-tools`](skills/coding-agent-use-existing-libraries-and-tools/SKILL.md)         | Before writing new logic, uses the built-ins of the tool already in use, a nixpkgs application or a library through Nix, and writes custom code only when none fits.                                                                                          |
| [`coding-agent-vpn-blocked-domains`](skills/coding-agent-vpn-blocked-domains/SKILL.md)                                   | When a domain blocks a request, checks whether it went through the VPN and suggests excluding the domain from it, or connecting it if it was off.                                                                                                             |

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
- `agent-skill-nhooey-coding-agent-browser-selection`
- `agent-skill-nhooey-coding-agent-headless-in-checkout`
- `agent-skill-nhooey-coding-agent-plans-as-graph`
- `agent-skill-nhooey-coding-agent-kanban-turn-responses`
- `agent-skill-nhooey-coding-agent-questions-as-first-class-prompts`
- `agent-skill-nhooey-coding-agent-route-feedback-to-skills-over-memory`
- `agent-skill-nhooey-coding-agent-scratchpad-scripts`
- `agent-skill-nhooey-coding-agent-session-build-limits`
- `agent-skill-nhooey-coding-agent-skill-references`
- `agent-skill-nhooey-coding-agent-use-existing-libraries-and-tools`
- `agent-skill-nhooey-coding-agent-vpn-blocked-domains`
- `hooks-plugin` — the hooks plugin, below

## Hooks plugin

A skill whose rule a script can decide in every session ships its hook in
`coding-agent-skills-hooks`, this repository's one hooks-only Claude Code
plugin. A plugin hook runs in every session and subagent, whether or not the
skill is loaded; the skill itself still installs through the packages above.

- **What's in it:**
  - the SessionStart hook `session-build-limits.sh`, from
    [`coding-agent-session-build-limits`](skills/coding-agent-session-build-limits/SKILL.md)
  - the PreToolUse (`Bash|Write|Edit`) and SubagentStart hook
    `scratchpad-guard.sh`, with its helper `scratchpad_guard.py`, from
    [`coding-agent-scratchpad-scripts`](skills/coding-agent-scratchpad-scripts/SKILL.md)
  - the PostToolUse (`Write|Edit`) hook `plans-check-hook.sh`, with its
    helpers `plans_check_hook.py` and `plans.py`, from
    [`coding-agent-plans-as-graph`](skills/coding-agent-plans-as-graph/SKILL.md)
  - the PreToolUse (`Write|Edit`) hook `memory-write-reminder.sh`, with its
    helper `memory_write_reminder.py`, from
    [`coding-agent-route-feedback-to-skills-over-memory`](skills/coding-agent-route-feedback-to-skills-over-memory/SKILL.md)
  - the PreToolUse (`mcp__claude-in-chrome__.*`) and PostToolUse (`Bash`,
    `select_browser`, `switch_browser`) hook `browser-check-hook.sh`, with its
    helper `browser_check_hook.py`, from
    [`coding-agent-browser-selection`](skills/coding-agent-browser-selection/SKILL.md)
- **Layout:** [`plugin/`](plugin/) holds `.claude-plugin/plugin.json` and
  `hooks/hooks.json`. It isn't the repository root, so the plugin doesn't load
  `skills/` a second time under a namespaced name.
- **The package:** `nix build .#hooks-plugin` copies `plugin/` and adds each
  hook script from its skill's `scripts/` to the plugin's `scripts/`. It is
  built by [`nix/hooks-plugin.nix`](nix/hooks-plugin.nix), the same derivation
  as agent-plugins-nixpkgs' `mkClaudePlugin`, built here because
  agent-plugins-nixpkgs takes this flake as an input.
- **Adding a hook:** keep the script in `skills/<skill>/scripts/`, where the
  skill documents it, and its tests in `tests/<skill>/`, where
  `skills-dev test <skill>` and `nix flake check` run them; list the script in
  `hookScripts` in [`flake.nix`](flake.nix); and add it to `hooks/hooks.json`
  as `bash "${CLAUDE_PLUGIN_ROOT}/scripts/<name>"`, since a store file has no
  executable bit to rely on. Keep it under about 50 ms, exiting at once when it
  has nothing to do.
- **A setting for blocking hooks:** a hook that can deny or block reads a
  setting that turns it down to a reminder or off, since a plugin enabled in
  managed settings can't be disabled in a session. The setting lives in the
  skill's preferences file, as
  [`coding-agent-skill-references`](skills/coding-agent-skill-references/SKILL.md)
  describes: `.agents/skills/<skill>.preferences.md` in the project
  (`$CLAUDE_PROJECT_DIR`), overriding `~/.agents/skills/<skill>.preferences.md`.
  The skill documents the setting's line.
  `session-build-limits.sh` only adds to the environment and
  `memory-write-reminder.sh` only adds context, so they have none;
  `scratchpad-guard.sh` reads `Scratchpad guard: deny | remind | off`, and is
  at `remind` unless set.
- **Checks:** `nix flake check` runs each hook script's tests and
  `checks.hooks-plugin`, which builds the plugin and runs
  [`check_hooks_plugin.py`](scripts/check_hooks_plugin.py): every hook is a
  command hook running one of the plugin's scripts through `bash`, every
  script is run by a hook or named by one as its helper and parses, and the
  manifest has a name and version.
  `claude plugin validate` on the built plugin checks it as Claude Code reads
  it.
- **Installing it:** agent-plugins-nixpkgs passes `hooks-plugin` through, and a
  nix-darwin configuration adds it to `services.agent-plugins.plugins`, which
  enables it in managed settings. To try it in one session, pass the store path
  to `claude --plugin-dir`.

## Development

```bash
nix develop      # enter the dev shell; run `menu` to list commands
nix fmt          # nixfmt over *.nix, prettier over *.md / *.yaml
nix flake check  # the treefmt check, the hooks plugin's build check and every test
```

The dev shell provides `check`, `fmt`, and `update-flake` commands plus
`reap-skills` / `update-skills-devshell`, and this repository's own tool,
`skills-dev`: `skills-dev test` runs every test outside the sandbox, the same
set as `nix flake check`'s `python-tests` and `shell-tests` checks: pytest over
the Python tests under [`tests/`](tests/) and [`scripts/`](scripts/), and bash
over the shell tests. `skills-dev test python` or `skills-dev test shell` runs
one language's, and `skills-dev test <skill> ...` the named skills' tests under
`tests/`. `skills-dev mods check` validates, type-checks and
tests the Claude Code mods under [`plugins/`](plugins/), and `skills-dev mods
try` starts Claude Code with one mod loaded. `mods check` runs outside
`nix flake check` because it needs `claude` itself and the API types its
running build writes. The dev shell's own toolchain skills (the git, shell and
Python packs, a few coding-agent skills, and skillspkgs' `authoring`
combination) live in the runtime [`skills-devshell/`](skills-devshell/)
sub-flake and are invoked at run time, so the root flake stays a leaf with zero
skill inputs in its lock.

## Layout

```
skills/                  one directory per skill (SKILL.md + per-skill flake.nix)
tests/                   each skill's tests in tests/<skill>/, and the layout test
skills-devshell/         runtime sub-flake supplying the dev shell's own skills
scripts/                 `skills-dev mods`, the hooks plugin's checker, and their tests
plugins/                 Claude Code mods, checked by `skills-dev mods check`
plugin/                  the hooks plugin's manifest and hooks.json; scripts come from skills/
nix/                     the hooks plugin's builder
agents/plans/            the project's plans, as a graph of Markdown nodes
source.nix               the upstream owner, shared by the root and every skill flake
flake.nix                builds skills via agent-skill-flake; wires the dev shell + treefmt
```

## Authoring a skill

Add a directory under `skills/<name>/` containing a `SKILL.md` and a `flake.nix`
that calls `agent-skill-flake.lib.mkSkillFlake` with `source = import
../../source.nix`. The root flake's `mkAllSkillsFlake` picks up every directory
under `skills/` automatically, so no central registry edit is needed. Run
`nix fmt` and `nix flake check` before committing.
