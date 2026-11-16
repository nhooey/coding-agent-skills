---
name: coding-agent-session-build-limits
description: Give every Claude Code session, interactive or headless, a fixed share of the machine for make, Cargo, Rust tests, pytest-xdist, the JVM and Gradle, Go, npm's native builds, uv, CMake, .NET and Swift, with a SessionStart hook, shipped in the coding-agent-skills-hooks plugin, that appends export lines to the file named in CLAUDE_ENV_FILE and leaves any variable the user already set alone. Use when setting up a machine so several sessions building at once don't oversubscribe its cores, when a session's builds or tests spawn more workers than the machine can spare, or when installing, changing or debugging that hook.
---

# Session build limits

_`scripts/session-build-limits.sh` is a SessionStart hook: it sets the variables build and test tools read, so one session uses at most a share of the cores._

## What it sets

The share is 3 unless the `Share` key of [Your preferences](#your-preferences) sets another. Three sessions building at once fill 8 performance cores; a fourth spills onto the efficiency cores. With the default share:

| Variable                        | Value                              | Limits                                    |
| ------------------------------- | ---------------------------------- | ----------------------------------------- |
| `MAKEFLAGS`                     | `-j3`                              | make, and what it starts                  |
| `CARGO_MAKEFLAGS`               | `-j3`                              | build scripts cargo runs                  |
| `CARGO_BUILD_JOBS`              | `3`                                | Cargo's own compile jobs                  |
| `RUST_TEST_THREADS`             | `3`                                | Rust test binaries                        |
| `PYTEST_XDIST_AUTO_NUM_WORKERS` | `3`                                | `pytest -n auto`                          |
| `JAVA_TOOL_OPTIONS`             | `-XX:ActiveProcessorCount=3`       | the JVM, so Gradle and Clojure tools      |
| `GOMAXPROCS`                    | `3`                                | Go programs                               |
| `GOFLAGS`                       | gains `-p=3`                       | `go build` and `go test`                  |
| `npm_config_jobs`               | `3`                                | native builds run by npm and node-gyp     |
| `UV_CONCURRENT_BUILDS`          | `3`                                | uv's source builds                        |
| `CMAKE_BUILD_PARALLEL_LEVEL`    | `3`                                | `cmake --build`                           |
| `DOTNET_PROCESSOR_COUNT`        | `3`                                | the .NET runtime, so MSBuild's node count |
| `SWIFT_BUILD_JOBS`              | `3`                                | a repository's Swift commands             |
| `GRADLE_OPTS`                   | gains `-Dorg.gradle.workers.max=3` | Gradle workers                            |

- **How:** it appends `export` lines to the file named in `CLAUDE_ENV_FILE`, which the session's Bash commands then load.
- **Variables already set:** a variable that is already set and not empty is left alone, so a session started with `MAKEFLAGS` set keeps its value.
- **Options appended:** `GOFLAGS` and `GRADLE_OPTS` hold other options, so the limit is appended to what they hold, and skipped when they already hold `-p=` or `-Dorg.gradle.workers.max=`.
- **Swift:** SwiftPM reads no variable for its job count, so a repository's Swift commands pass `--jobs "$SWIFT_BUILD_JOBS"` to `swift build` and `swift test`.
- **No `CLAUDE_ENV_FILE`:** the script does nothing and exits 0.
- **Not Nix:** none of these variables reaches a Nix build, which runs under the daemon with its own `max-jobs` and `cores` for each client. `coding-agent-headless-in-checkout` holds new headless runs while the machine is short of memory, which bounds Nix across agents. A builder that shares the store can't make a machine-wide cap either: the daemon handing a build off keeps its output locks while the builder runs, so a second daemon, or `localhost` in `builders`, waits on them forever ([NixOS/nix#2029](https://github.com/NixOS/nix/issues/2029)).

## Installing it

The hook comes from the `coding-agent-skills-hooks` plugin, this collection's hooks plugin, not from the user's `settings.json`. The skill only documents it.

- **Where it's built:** the flake package `hooks-plugin` copies this skill's `scripts/session-build-limits.sh` into the plugin, whose `hooks/hooks.json` runs it under SessionStart as `bash "${CLAUDE_PLUGIN_ROOT}/scripts/session-build-limits.sh"`.
- **How it's installed:** agent-plugins-nixpkgs passes `hooks-plugin` through, and MyNixOS lists it in `services.agent-plugins.plugins`, whose nix-darwin module enables it in managed settings. A plugin enabled there runs in every session and subagent, and no session or user setting can turn it off.
- **For one session:** `claude --plugin-dir "$(nix build --no-link --print-out-paths github:nhooey/coding-agent-skills#hooks-plugin)"`.
- **A hand-wired copy:** a `hooks.SessionStart` entry in `settings.json` that runs this script as well makes the hook run twice, writing the same export lines twice. That's harmless but redundant; suggest the user remove it, and never edit the user's settings without being asked.
- **Not in:** `--bare` runs, which skip plugins, and agents other than Claude Code.

## Checking it

- A new session's `env` shows the variables in the table.
- `cargo test`, `pytest -n auto`, `go test ./...` and a Gradle build in a session each use at most the share's workers.
- In the coding-agent-skills repository's dev shell, `skills-dev test coding-agent-session-build-limits` runs the script's tests, in `tests/coding-agent-session-build-limits/`, against a temporary `CLAUDE_ENV_FILE`.

## Your preferences

!`cat "$(dirname "${CLAUDE_SKILL_DIR}")/coding-agent-session-build-limits.preferences.md" "${CLAUDE_PROJECT_DIR}/.agents/skills/coding-agent-session-build-limits.preferences.md" 2>/dev/null || true`

If your agent doesn't run the line above, read these files yourself if they exist: `coding-agent-session-build-limits.preferences.md` next to this skill's folder, then `.agents/skills/coding-agent-session-build-limits.preferences.md` in the project.
A project's file overrides the user's, and the user's overrides this skill's defaults.

The key this skill reads, with its own default. The hook reads it from both files itself, at every session start; a value that isn't a positive whole number is ignored. The share is a fact about the machine, so the machine configuration writes it in the user's file:

```markdown
- Share: 3
```

## Related skills

When one of these applies and it's in your skill listing, load it without asking.
If it isn't in your listing, tell the user which skill is missing and ask whether to install it from the same collection this skill came from; don't apply it from memory.

- `coding-agent-headless-in-checkout`: holds new headless runs under memory pressure, which this hook's variables don't cover.
