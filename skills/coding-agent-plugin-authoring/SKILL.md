---
name: coding-agent-plugin-authoring
description: Lay out, build, test and ship a Claude Code plugin in an nhooey repository. The plugin sits in its own `plugin/` folder and is packaged with agent-plugins-nixpkgs' `claudePlugin` flake module, which builds it as `packages.plugin` and adds a `plugin-build` command. `nix flake check` builds it and runs `claude plugin validate` on the build; the dev shell runs `claude plugin test` on the engine-driven tests; a `--plugin-dir result-plugin` session tries a change; and a lock bump in agent-plugins-nixpkgs ships it. Covers the flake input that keeps the two lock files from nesting, what the build includes, runtime libraries vendored as committed bundles, the hook-mode helper the build adds, and user plugins over managed ones for a plugin under development. Complements the bundled `plugin-authoring` skill, which covers the hooks API. Use when creating a plugin repository, adding a plugin to one, changing what a plugin's build holds, testing a plugin change in a session, or releasing one.
---

# Plugin authoring

_A plugin lives in its repository's `plugin/` folder, is built by the `claudePlugin` flake module, checked by `claude plugin validate` and `claude plugin test`, tried with `--plugin-dir`, and shipped by a lock bump in agent-plugins-nixpkgs._

This skill is the packaging around a plugin.
What goes in it, the hooks API, mods, panes, tools and `hooks.json`, is in Claude Code's bundled `plugin-authoring` skill; load it for that.

## Layout

- **The plugin's folder:** `plugin/`, never the repository root, so the build copies only the plugin, and a repository that also holds skills under `skills/` doesn't load them a second time under the plugin's namespace.
- **The manifest:** `plugin/.claude-plugin/plugin.json`, with a `name` and a `version`; the build's name and version come from it.
- **What runs:** `hooks/`, `src/`, `types/`, `defaults/` and `vendor/`, the folders the build includes.
  Tests, tools, `package.json` and `node_modules` sit beside them in `plugin/` and stay out of the build.
- **Runtime libraries:** the engine loads only the plugin's own files, so each library a hook imports is bundled by the flake into one ES module file in `plugin/vendor/`, with its licence beside it.
  The bundles are committed, for a marketplace install, and a flake check fails where they differ from the flake's, naming the command that lays them again.
- **A hooks-only plugin:** `hooks.json` runs each script as `bash "${CLAUDE_PLUGIN_ROOT}/scripts/<name>"`, since a store file has no executable bit to rely on.
  The scripts live in the skills that document and test them, and the build copies them into `scripts/`.
- **The hook-mode helper:** the build adds `lib/hook-mode.sh`, so a plugin never has a file at that path.
  A hook that can deny or block reads its mode through it, `hook_mode <name>` from bash, and starts at `remind`.

## The build

Import agent-plugins-nixpkgs' `flakeModules.claudePlugin` and turn it on in `perSystem`:

```nix
inputs.agent-plugins-nixpkgs = {
  url = "github:nhooey/agent-plugins-nixpkgs";
  inputs = {
    nixpkgs.follows = "nixpkgs";
    flake-parts.follows = "flake-parts";
    # agent-plugins-nixpkgs takes this repository as an input; following
    # nothing keeps each lock file from nesting the other at every update.
    <this-repository>.follows = "";
  };
};

imports = [ inputs.agent-plugins-nixpkgs.flakeModules.claudePlugin ];

perSystem = { config, ... }: {
  agent-plugins.claudePlugin = {
    enable = true;
    src = ./plugin;
    include = [ ".claude-plugin/plugin.json" "defaults" "hooks" "src" "types" "vendor" ];
  };
  packages.default = config.packages.plugin;
};
```

| Option        | Default                                                           | Use                                                      |
| ------------- | ----------------------------------------------------------------- | -------------------------------------------------------- |
| `src`         | none                                                              | the plugin's folder, as a path                           |
| `include`     | `.claude-plugin/plugin.json`, `defaults`, `hooks`, `src`, `types` | the paths copied; one that doesn't exist is skipped      |
| `postPatch`   | empty                                                             | shell run in the copy, such as copying in vendor bundles |
| `packageName` | `plugin`                                                          | the package's name                                       |

- **What it gives:** `packages.plugin`, and, with numtide devshell's flake module imported, a `plugin-build` command that builds it into `result-plugin`.
- **Without the module:** a flake that only needs the builder, such as a skills repository with a hooks-only plugin, takes agent-plugins-nixpkgs as a `flake = false` input and calls `lib.mkClaudePlugin pkgs { src; include; postPatch; }` from `import "${inputs.agent-plugins-nixpkgs}/lib" { inherit (nixpkgs) lib; }`, which needs no `follows` at all.
- **New files:** the flake reads the git tree, so a new file reaches the build only once `git add` has staged it.

## Checks

| Check                    | Runs in            | What it does                                                                                |
| ------------------------ | ------------------ | ------------------------------------------------------------------------------------------- |
| the plugin's build       | `nix flake check`  | `checks.plugin`, the package itself                                                         |
| `claude plugin validate` | `nix flake check`  | validates the built plugin as Claude Code reads it                                          |
| the core's tests         | `nix flake check`  | type-checks and unit tests of the code that imports nothing from the engine                 |
| vendor bundles           | `nix flake check`  | the committed bundles against the flake's                                                   |
| `claude plugin test`     | the dev shell only | the engine-driven tests, which need the engine's runtime and API types, which a build lacks |

- **Validate in a build:** run nixpkgs' `claude-code` in a `runCommand` on `config.packages.plugin`, with `HOME` set to a folder under `$TMPDIR` and `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`, `DISABLE_AUTOUPDATER` and `DISABLE_TELEMETRY` set to `1`.
  It is unfree, so the flake's `pkgs` allows `claude-code` alone by name with `allowUnfreePredicate`.
- **`claude plugin test <folder>`** runs every `*.test.ts` and `*.test.tsx` under the folder, so it can't be pointed at `plugin/` when that also holds the core's Node tests.
  A dev shell command, `plugin-test`, copies the manifest, the folders that run and the engine tests into a temporary folder, then runs `claude plugin validate` and `claude plugin test` on it.
- **Before a pull request** that touches the hooks or the engine tests, run `plugin-test` and the hooks' type-check against the engine's API, since `nix flake check` runs neither.

## Trying a change in a session

1. **Install it as a user plugin.** The nix-darwin configuration lists a plugin under development in `services.agent-plugins.userPlugins`, never `managedPlugins`, and the user's own settings enable it as `<plugin>@nix-pinned`.
   A managed entry locks the plugin's name, so `--plugin-dir` can't load a working copy over it.
2. **Build it:** `plugin-build`, which links the build to `result-plugin`.
3. **Start the session** from the repository: `claude --plugin-dir result-plugin --continue`.
   The local build overrides the pinned install for that session only.
4. **After each change:** `plugin-build` again, then `/reload-plugins` in that session.

## Shipping it

agent-plugins-nixpkgs takes each first-party plugin repository as a flake input and passes its `packages.<system>.plugin` through as a package of its own, named for the plugin.
A repository whose flake exports no package with the passthru `mkMarketplace` reads is taken as a `flake = false` `*-src` input instead, and built there with `mkClaudePlugin`.

- **A release:** merge the change in the plugin's repository, then bump its input in agent-plugins-nixpkgs with `agent-plugins update <input>` in its dev shell, in a pull request there.
  Then bump agent-plugins-nixpkgs in the nix-darwin configuration and switch; Claude Code loads the new build at the next session start.
- **A new plugin:** in agent-plugins-nixpkgs, add the input, with its `agent-plugins-nixpkgs.follows = ""`, the pass-through in `pkgs/`, a row in the README's first-party table and a case in its `first-party-plugins` check; then list the package in the nix-darwin configuration's `userPlugins`.

## Related skills

When one of these applies and it's in your skill listing, load it
without asking. If it isn't in your listing, tell the user which skill is
missing and ask whether to install it from the same collection this skill
came from; don't apply it from memory.

- `plugin-authoring`: what goes in a plugin: hooks, mods, panes, tools and `hooks.json`.
- `nix-flakes`: the conventions the plugin repository's `flake.nix` follows.
