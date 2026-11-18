---
name: coding-agent-use-existing-libraries-and-tools
description: Before writing a parser, runner, checker, converter or other new logic, or when a brief asks for custom code, look for what already does the job, and before briefing a subagent to write some. Search the built-ins of the tool already in use, then nixpkgs, then the language's libraries through Nix, and write custom code only when none fits, naming in the commit message what was considered.
---

# Use existing libraries and tools

_Custom code for a solved problem is code someone must read, test and fix._
_Before writing new logic, find the built-in, application or library that already does the job._

## When it applies

Before writing logic of a kind that has been written many times before, such as:

- a parser of a structured format, such as YAML frontmatter, TOML, CSV or a command's output;
- a test runner, or tests of one;
- a diff, a backup, or a check that data is complete or consistent;
- argument parsing, retries, date and time handling, or a converter between formats.

It applies as much when a brief asks for the custom code as when you decide to write it.
When the search finds a fit for code a brief asked for, report the fit to whoever wrote the brief before departing from it.

## Search in this order

Use the first that fits:

1. **The built-ins of the tool already in use,** such as git's subcommands or jq's built-in functions.
   `git rev-list --objects --all --missing=error` and `git fsck` already check that a repository holds every object it needs, so a backup check needs no script of its own.
2. **An application in nixpkgs,** found with `nix search nixpkgs <name>` and added to the flake's dev shell or to the check that runs it.
3. **A library from the language's package index, provided through Nix,** from nixpkgs or the `*2nix` library the project already uses.
4. **Custom code,** only when nothing above fits.

Judge a fit by the inputs the job will meet, not by the length of the call that wraps the tool.

## Then

- **Writing custom code:** the commit message names each thing considered and why it didn't fit, one line each.
- **Code that must use only the standard library,** such as a skill's Python scripts: call an external command-line tool on `PATH`, provided through Nix, rather than bundle a library or reimplement it.
  The code checks the tool is on `PATH` before using it, such as with `shutil.which`, and fails with a message naming the missing tool.
- **Tests:** these may use libraries through Nix, and run under the language's own test tool, such as pytest, bats or `cargo test`.
- **A language the project has already chosen:** keep to it, and search within it rather than bring in a second language for one library.
- **Briefs:** a subagent brief that asks for new logic tells the agent to run this search first and to report what it found at each step.

## Why

A library or application has been run on inputs nobody in this project has thought of, while a hand-written parser handles the cases in front of its author.
Custom code also brings its own tests, and tests of a hand-written runner test the runner, not the code it runs.

## Related skills

When one of these applies and it's in your skill listing, load it
without asking. If it isn't in your listing, tell the user which skill is
missing and ask whether to install it from the same collection this skill
came from; don't apply it from memory.

- `coding-agent-scratchpad-scripts`: custom code that survives the search becomes a named tool in the project, not a scratchpad script.
- `shell-hygiene-commands-as-cli-tools`: the shape custom code takes when it is a command.
- `nix-flakes`: providing an application or library through the flake, and choosing a `*2nix` library.
