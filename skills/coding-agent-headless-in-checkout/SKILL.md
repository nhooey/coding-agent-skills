---
name: coding-agent-headless-in-checkout
description: Run a prompt as a headless Claude Code session inside one git checkout, so it loads that checkout's CLAUDE.md, skills, settings, plugins and Nix dev shell as a session started there by hand would, and fan it out across many checkouts by running the bundled single-checkout script once per checkout, from xargs, a shell loop or parallel Bash calls. Each run works in a git worktree by default, starts a new session or continues the checkout's newest one as a fork, warning when that session may still be running, and reports how it ended as one JSON line and an exit status. Use when the user wants a job done in another repository's own context, or the same job done in several ("run this in all my repos", "do X across these projects", "use up my weekly limit on my recent repos"), instead of subagents, which all start in the parent session's directory with its skills.
---

# Headless sessions in other checkouts, and fanning them out

_`scripts/run_headless.py` runs one `claude -p` inside one checkout and reports how it ended; running a prompt across many checkouts is the caller's job, one call of the script per checkout._

## Why shells, not subagents

A subagent, or a Workflow agent, starts in the parent session's working directory and gets the parent's `CLAUDE.md` and skills. It can't become a session of another repository. A headless `claude -p` started with a checkout as its working directory loads everything a manual session there would: the checkout's `CLAUDE.md`, `.claude/skills`, `.claude/settings.json`, hooks, `.mcp.json` servers and plugins. Never pass `--bare`, which skips all of them.

A subagent that only shells out to `claude -p` works too, but spends tokens supervising a process that needs none. Run the script from a Bash call instead: in the background from a session, which hears when it finishes, or from a terminal.

## Running it in one checkout

```bash
run_headless.py --dry-run --job <name> --prompt '<prompt>' <checkout>   # the plan, nothing started
run_headless.py --job <name> --prompt-file prompt.md <checkout>
```

`scripts/run_headless.py --help` lists every option. The ones that matter most:

| Option                       | Default                 | What it does                                                                                                                |
| ---------------------------- | ----------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `--job`                      | a timestamp             | names the worktree branch `headless/<job>`, the session and the log folder                                                  |
| `--label`                    | the checkout's name     | names the log files and progress lines; set it when two checkouts share one                                                 |
| `--where worktree\|checkout` | `worktree`              | where the session works                                                                                                     |
| `--session new\|continue`    | `new`                   | start fresh, or fork the checkout's newest session                                                                          |
| `--model`, `--effort`        | the user's own settings | passed to `claude`                                                                                                          |
| `--permission-mode`          | `auto`                  | passed to `claude`, always with `--permission-prompts none` so nothing waits                                                |
| `--max-turns`, `--timeout`   | none                    | caps; set them on a first or experimental run                                                                               |
| `--claude-arg`               | none                    | one more `claude` argument, repeatable                                                                                      |
| `--no-admission`             | off                     | start at once, whatever the memory pressure                                                                                 |
| `--admission-timeout`        | none                    | minutes to wait for memory pressure to ease before giving up as `skipped`                                                   |
| `--dry-run`                  | off                     | print the working directory, the session it resumes, the command, the priority prefix and the memory pressure level it read |

A run takes minutes to an hour, so a session running it follows `coding-agent-usage-line-report-eta`.

## Priority and admission control

- **Priority:** on macOS each session starts under `taskpolicy -c utility`, so the scheduler favours interactive work and everything the session starts inherits the class. Elsewhere it starts at normal priority. `--no-admission` keeps the utility class.
- **Memory pressure:** before starting, the script reads `kern.memorystatus_vm_pressure_level`: 1 (normal) starts the run; 2 (warning) or 4 (critical) holds it, rechecking every few seconds and saying so on a progress line, `waiting <label> <time>: memory pressure level <n>`. A run already going is never stopped. A level that can't be read, or isn't 1, 2 or 4, counts as 1, with a note in the outcome. Off macOS there is nothing to read, so the run starts.
- **Giving up:** `--admission-timeout <minutes>` ends the wait with status `skipped` and exit status 3, so a fan-out moves on; the checkout's work is untouched and no worktree is made. Without it the run waits as long as it takes; with `--no-admission` it doesn't wait at all, for a run that must go whatever the pressure.
- **What it bounds:** Nix's `max-jobs` and `cores` apply to each client of the daemon, so holding a new run is what keeps builds across a fan-out near the machine's CPUs. Keep a fan-out's `-P` small anyway.
- **Checking it:** `taskpolicy -G <pid>` on a started session shows the utility class.

## Fanning out across checkouts

The script does one checkout; the caller runs it once per checkout. Give every run the same `--job`, so their worktrees, branches and logs share a name. From one Bash call, with the checkouts one per line in a file:

```bash
xargs -P 4 -I{} run_headless.py --job <name> --prompt-file prompt.md {} < checkouts.txt
jq -s . "${XDG_STATE_HOME:-$HOME/.local/state}/coding-agent-headless/<name>"/*.outcome.json
```

`-P` sets how many run at once. Try the prompt on one checkout, with a low `--max-turns`, before a large batch. A shell loop or separate Bash calls work as well; xargs is the shortest way to cap how many run at a time and to stop on a usage limit (see [Limits and billing](#limits-and-billing)).

### Choosing the checkouts

The user names them, or asks for "the ones I've worked on lately". To list the checkouts under a folder, such as `~/git`, newest commit by the user first:

```bash
find ~/git -maxdepth 4 -name .git -type d -prune | sed 's|/.git$||' | while read -r d; do
  t=$(git -C "$d" log -1 --format=%ct --author="$(git config user.email)" 2>/dev/null) && [ -n "$t" ] && echo "$t $d"
done | sort -rn | head -20 | cut -d' ' -f2-
```

Show the list and the prompt to the user before a real run: every run acts on its own, with nobody to approve its steps. Two checkouts with the same folder name need a `--label` each, or their logs overwrite each other.

## Worktrees and sessions

- **Worktree (default):** the run gets `<checkout>.worktrees/headless-<job>`, beside the checkout, on a new branch `headless/<job>` from the checkout's `HEAD`. The checkout's working tree is never touched, so a run can't collide with uncommitted work or an open session. Uncommitted changes in the checkout are not in the worktree. A rerun with the same `--job` reuses the worktree.
- **Uncommitted work:** a worktree has only what's committed, so a session continued in one can remember edits that stayed behind in the checkout. For a checkout with uncommitted changes, `--dirty` decides what a continuing worktree run does: `tell` (the default) continues, and opens the prompt with a note naming the uncommitted paths and saying their changes aren't there; `new` starts a new session instead; `skip` doesn't run until the work is committed or stashed. Tell the user which checkouts are dirty before the run, from the dry run's notes.
- **Checkout:** the run works in the checkout itself. Use it only when the checkout is clean and no one else is working there.
- **New or continued:** a new session is the default, and right for a wave, whose prompt carries all the context the run needs. Continue only to follow up on what that checkout's own session was doing.
- **Continuing:** Claude Code keeps a directory's sessions in `~/.claude/projects/<the path, every non-alphanumeric character turned into ->/`. The script takes the newest `.jsonl` there and forks it: `--continue --fork-session` in the checkout, or `--resume <the .jsonl> --fork-session` in a worktree, whose new directory has no sessions of its own. The fork leaves the original session as it was, for a window that may still have it open. A checkout with no session gets a new one. Every session the script starts is named `headless <job>`.
- **A session that may still be running:** when the newest transcript was written in the last `--live-within` minutes, 10 by default, the script warns on stderr and in the outcome's notes. The fork is a copy as of that moment: it won't see what the live session does next, and in `--where checkout` the two can edit the same files.

## The Nix environment

Each run gets the checkout's environment the way a manual session does:

- **Through a plugin:** a checkout whose dev shell reaches Claude Code through a plugin, one that loads it into every Bash command, needs nothing more, since `claude -p` loads plugins.
- **Through direnv:** a checkout with an `.envrc` runs under `direnv exec <dir>`. direnv trusts an `.envrc` by its path, so a new worktree's copy starts blocked; the script allows it only when it is byte for byte the checkout's own, which the user already allowed.

## Reading the results

Progress goes to stderr, each line opening on the run's label: one when the session starts, one every `--progress-every` seconds, 60 by default, with its time, its tool calls so far and the tool it called last, and one when it ends. When the agent runs a fan-out in the background, it reads that output only when the user asks how it's going.

The outcome goes to stdout as one JSON line, and to `<label>.outcome.json` in the log folder, `$XDG_STATE_HOME/coding-agent-headless/<job>/` by default: its `status` (`ok`, `failed`, `limit` or `skipped`), exit `code`, `session_id`, `resumed_from`, `turns`, the start of the final `result`, its `log` and its `notes`. The session's full stream-json output and stderr are beside it. The exit status says the same: 0 ok, 1 failed or timed out, 2 bad arguments, 3 skipped, 255 a usage limit.

### The live status file

While a run goes, the script keeps `<label>.status.json` beside the outcome, rewritten every `--status-every` seconds, 10 by default, and once more when the run ends. Each write goes to a temporary file that is then renamed over it, so a reader never sees half a record. The `coding-agent-headless-runs` mod in this repository draws these files in a pane. One JSON object:

| Field                              | Holds                                                                                                                                                                                                                                           |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `job`, `label`                     | the run's `--job` and `--label`                                                                                                                                                                                                                 |
| `checkout`, `workdir`, `branch`    | the checkout, where the session works, and that directory's branch: `headless/<job>` in a worktree                                                                                                                                              |
| `log`                              | the stream-json log's path                                                                                                                                                                                                                      |
| `session_id`, `transcript`         | the session's id and its transcript's path, once the session has said its id; `null` before                                                                                                                                                     |
| `state`                            | `waiting` (held by admission control), `running`, then `ok`, `failed`, `limit` or `skipped`                                                                                                                                                     |
| `started`, `updated`, `ended`      | ISO 8601 date-times in UTC: when the runner began, the last write, and the end (`null` until then)                                                                                                                                              |
| `turns`, `tool_calls`, `last_tool` | from the stream log so far; `turns` is the result's own count once the run ends                                                                                                                                                                 |
| `eta`                              | the last `coding-agent-usage-line-report-eta` line the session wrote: `figure` (`4m`), `seconds`, `count` (how many it has written) and `at`, when; `null` before the first one                                                                 |
| `pid`                              | the runner's process id                                                                                                                                                                                                                         |
| `parent`                           | the session that started the runner: `session_id` and `pid` from the `CLAUDE_CODE_SESSION_ID` and `CLAUDE_PID` Claude Code exports to Bash (outside Claude Code, no id and the parent process's pid), and `cwd`, the runner's working directory |

The ETA's `at` is the transcript entry's timestamp; where the transcript can't be read, it is the first write that saw the line, so it is late by at most `--status-every`. A `running` record whose `updated` has stopped moving belongs to a runner that was killed.

Report each checkout's outcome to the user by its name, with the branch of any worktree that holds changes. A run's own work, such as a pull request it opened, is in its result text and log.

## Limits and billing

- **Subscription, not the API:** `claude -p` bills `ANTHROPIC_API_KEY` whenever it is set, so the script refuses to start while it is, unless given `--allow-api-key`. `claude auth status` shows the login in use.
- **Usage limits:** a headless run can't wait for a limit to reset. A run that fails on a usage limit exits 255, and xargs, GNU or BSD, starts no more commands after one exits 255, so an xargs fan-out stops there by itself. A caller that loops instead checks for 255 and stops. Rerun the checkouts with no outcome file after the reset, with the same `--job` to reuse their worktrees.
- **Trust:** a headless session runs a checkout's hooks and `.mcp.json` servers without a trust dialog, and auto mode approves actions without a person. Run only in checkouts the user owns, named one by one.

## Cleaning up

A finished job leaves its worktrees and `headless/<job>` branches. Remove each by its path and branch name once its changes are merged or dropped, as `shell-hygiene-delete-named-paths` and `git-workflow-tidy-branches` say: `git -C <checkout> worktree remove <checkout>.worktrees/headless-<job>`, then `git -C <checkout> branch -d headless/<job>`.

## Your preferences

!`cat "${CLAUDE_SKILL_DIR}/../coding-agent-headless-in-checkout.preferences.md" "${CLAUDE_PROJECT_DIR}/.agents/skills/coding-agent-headless-in-checkout.preferences.md" 2>/dev/null || true`

If your agent doesn't run the line above, read these files yourself if they
exist: `coding-agent-headless-in-checkout.preferences.md` next to this skill's folder, then
`.agents/skills/coding-agent-headless-in-checkout.preferences.md` in the project. A project's
file overrides the user's, and the user's overrides this skill's defaults.

## Related skills

When one of these applies and it's in your skill listing, load it
without asking. If it isn't in your listing, tell the user which skill is
missing and ask whether to install it from the same collection this skill
came from; don't apply it from memory.

- `coding-agent-usage-line-report-eta`: report a running ETA while a run or a fan-out goes, since either takes minutes to an hour.
- `shell-hygiene-delete-named-paths`: remove each finished worktree by its own path, never by glob.
- `git-workflow-tidy-branches`: delete the `headless/<job>` branches once their work is merged or dropped.
