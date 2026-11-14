---
name: coding-agent-fan-out-headless
description: Run one prompt across many git checkouts at once, as one headless Claude Code session per checkout, each started inside its checkout so it loads that checkout's CLAUDE.md, skills, settings, plugins and Nix dev shell as a session started there by hand would. Each run works in a git worktree by default, continues the checkout's newest session as a fork or starts a new one, and the bundled runner waits for every run and writes a summary. Use when the user wants the same job done in several repositories ("run this in all my repos", "do X across these projects", "use up my weekly limit on my recent repos"), instead of subagents, which all start in the parent session's directory with its skills.
---

# Fan one prompt out across checkouts

_One `claude -p` per checkout, started inside it, in parallel; the bundled `scripts/fan_out.py` sets each one up, waits for them all and reports._

## Why shells, not subagents

A subagent, or a Workflow agent, starts in the parent session's working directory and gets the parent's `CLAUDE.md` and skills. It can't become a session of another repository. A headless `claude -p` started with a checkout as its working directory loads everything a manual session there would: the checkout's `CLAUDE.md`, `.claude/skills`, `.claude/settings.json`, hooks, `.mcp.json` servers and plugins. Never pass `--bare`, which skips all of them.

A subagent that only shells out to `claude -p` works too, but spends tokens supervising a process that needs none. Run the runner from one Bash call instead: in the background from a session, which hears when it finishes, or from a terminal.

## Running it

```bash
fan_out.py --dry-run --job <name> --prompt '<prompt>' <checkout>...   # the plan, nothing started
fan_out.py --job <name> --prompt-file prompt.md --parallel 4 <checkout>...
```

`scripts/fan_out.py --help` lists every option. The ones that matter most:

| Option                       | Default                 | What it does                                                                 |
| ---------------------------- | ----------------------- | ---------------------------------------------------------------------------- |
| `--job`                      | a timestamp             | names the worktree branch `fan-out/<job>`, the sessions and the log folder   |
| `--where worktree\|checkout` | `worktree`              | where each run works                                                         |
| `--session continue\|new`    | `continue`              | fork the checkout's newest session, or start fresh                           |
| `--parallel`                 | 4                       | runs at a time                                                               |
| `--model`, `--effort`        | the user's own settings | passed to `claude`                                                           |
| `--permission-mode`          | `auto`                  | passed to `claude`, always with `--permission-prompts none` so nothing waits |
| `--max-turns`, `--timeout`   | none                    | caps per run; set them on a first or experimental run                        |
| `--claude-arg`               | none                    | one more `claude` argument, repeatable                                       |
| `--dry-run`                  | off                     | print each run's working directory, the session it resumes and its command   |

Start with `--dry-run`, and with a low `--max-turns` on one checkout before a large batch. A run takes minutes to an hour, so a session running it follows `coding-agent-usage-line-report-eta`.

## Choosing the checkouts

The user names them, or asks for "the ones I've worked on lately". To list the checkouts under a folder, such as `~/git`, newest commit by the user first:

```bash
find ~/git -maxdepth 4 -name .git -type d -prune | sed 's|/.git$||' | while read -r d; do
  t=$(git -C "$d" log -1 --format=%ct --author="$(git config user.email)" 2>/dev/null) && [ -n "$t" ] && echo "$t $d"
done | sort -rn | head -20 | cut -d' ' -f2-
```

Show the list and the prompt to the user before a real run: every run acts on its own, with nobody to approve its steps.

## Worktrees and sessions

- **Worktree (default):** each run gets `<checkout>.worktrees/fan-out-<job>`, beside the checkout, on a new branch `fan-out/<job>` from the checkout's `HEAD`. The checkout's working tree is never touched, so many runs can't collide with uncommitted work or an open session. Uncommitted changes in the checkout are not in the worktree. A rerun with the same `--job` reuses the worktree.
- **Uncommitted work:** a worktree has only what's committed, so a session continued in one can remember edits that stayed behind in the checkout. For a checkout with uncommitted changes, `--dirty` decides what a continuing worktree run does: `tell` (the default) continues, and opens the prompt with a note naming the uncommitted paths and saying their changes aren't there; `new` starts a new session instead; `skip` leaves the checkout out until its work is committed or stashed. Tell the user which checkouts are dirty before the run, from the dry-run's notes.
- **Checkout:** the run works in the checkout itself. Use it only when the checkout is clean and no one else is working there.
- **Continuing:** Claude Code keeps a directory's sessions in `~/.claude/projects/<the path, every non-alphanumeric character turned into ->/`. The runner takes the newest `.jsonl` there and forks it: `--continue --fork-session` in the checkout, or `--resume <the .jsonl> --fork-session` in a worktree, whose new directory has no sessions of its own. The fork leaves the original session as it was, for a window that may still have it open. A checkout with no session gets a new one, named `fan-out <job>`.

## The Nix environment

Each run gets the checkout's environment the way a manual session does:

- **Through a plugin:** a checkout whose dev shell reaches Claude Code through a plugin, one that loads it into every Bash command, needs nothing more, since `claude -p` loads plugins.
- **Through direnv:** a checkout with an `.envrc` runs under `direnv exec <dir>`. direnv trusts an `.envrc` by its path, so a new worktree's copy starts blocked; the runner allows it only when it is byte for byte the checkout's own, which the user already allowed.

## Reading the results

The runner prints one line per run as it finishes, then writes `summary.json` in the log folder, `$XDG_STATE_HOME/coding-agent-fan-out/<job>/` by default: per checkout its `status` (`ok`, `failed`, `limit` or `skipped`), exit `code`, `session_id`, `resumed_from`, `turns`, the start of the final `result`, its `log` and its `notes`. Each run's full stream-json output and stderr are beside it. The runner exits 0 only when every run is `ok`.

Report each checkout's outcome to the user by its name, with the branch of any worktree that holds changes. A run's own work, such as a pull request it opened, is in its result text and log.

## Limits and billing

- **Subscription, not the API:** `claude -p` bills `ANTHROPIC_API_KEY` whenever it is set, so the runner refuses to start while it is, unless given `--allow-api-key`. `claude auth status` shows the login in use.
- **Usage limits:** a headless run can't wait for a limit to reset. The first run that fails on a usage limit stops the runner from starting more, and the rest are reported as `skipped`. Rerun those checkouts after the reset, with the same `--job` to reuse their worktrees.
- **Trust:** a headless session runs a checkout's hooks and `.mcp.json` servers without a trust dialog, and auto mode approves actions without a person. Run only in checkouts the user owns, named one by one.

## Cleaning up

A finished job leaves its worktrees and `fan-out/<job>` branches. Remove each by its path and branch name once its changes are merged or dropped, as `shell-hygiene-delete-named-paths` and `git-workflow-tidy-branches` say: `git -C <checkout> worktree remove <checkout>.worktrees/fan-out-<job>`, then `git -C <checkout> branch -d fan-out/<job>`.

## Your preferences

!`cat "${CLAUDE_SKILL_DIR}/../coding-agent-fan-out-headless.preferences.md" "${CLAUDE_PROJECT_DIR}/.agents/skills/coding-agent-fan-out-headless.preferences.md" 2>/dev/null || true`

If your agent doesn't run the line above, read these files yourself if they
exist: `coding-agent-fan-out-headless.preferences.md` next to this skill's folder, then
`.agents/skills/coding-agent-fan-out-headless.preferences.md` in the project. A project's
file overrides the user's, and the user's overrides this skill's defaults.

## Related skills

When one of these applies and it's in your skill listing, load it
without asking. If it isn't in your listing, tell the user which skill is
missing and ask whether to install it from the same collection this skill
came from; don't apply it from memory.

- `coding-agent-usage-line-report-eta`: report a running ETA while the runs go, since a batch takes minutes to an hour.
- `shell-hygiene-delete-named-paths`: remove each finished worktree by its own path, never by glob.
- `git-workflow-tidy-branches`: delete the `fan-out/<job>` branches once their work is merged or dropped.
