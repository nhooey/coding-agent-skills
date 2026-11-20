---
name: coding-agent-headless-in-checkout
description: Load when a job should run inside another repository's own context, or the same job across several, as in "run this in all my repos", "do X across these projects" or "use up my weekly limit on my recent repos". Runs a headless Claude Code session per checkout, since subagents all start in this session's directory with its skills.
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

| Option                       | Default                 | What it does                                                                                                                                                                                                                                                  |
| ---------------------------- | ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--job`                      | a timestamp             | names the worktree branch `headless/<job>`, the session and the log folder                                                                                                                                                                                    |
| `--label`                    | the checkout's name     | names the log files and progress lines; set it when two checkouts share one                                                                                                                                                                                   |
| `--where worktree\|checkout` | `worktree`              | where the session works                                                                                                                                                                                                                                       |
| `--session new\|continue`    | `new`                   | start fresh, or fork the checkout's newest session                                                                                                                                                                                                            |
| `--model`, `--effort`        | the user's own settings | passed to `claude`                                                                                                                                                                                                                                            |
| `--permission-mode`          | `auto`                  | passed to `claude`, always with `--permission-prompts none` so nothing waits                                                                                                                                                                                  |
| `--max-turns`, `--timeout`   | none                    | caps; set them on a first or experimental run                                                                                                                                                                                                                 |
| `--claude-arg`               | none                    | one more `claude` argument, repeatable                                                                                                                                                                                                                        |
| `--no-admission`             | off                     | start at once, whatever the memory pressure and free space                                                                                                                                                                                                    |
| `--admission-timeout`        | none                    | minutes to wait for memory pressure to ease or disk space to free before giving up as `skipped`                                                                                                                                                               |
| `--keep-worktree`            | off                     | leave the run's worktree as it ends, and sweep no landed worktrees before it                                                                                                                                                                                  |
| `--dry-run`                  | off                     | print the working directory, the session it resumes, the command, the priority prefix, the memory pressure level it read, the build floor (`build_floor_gb`), each volume under it (`disk_short`) and the path of `git-worktree-manager` (`worktree_manager`) |

A run takes minutes to an hour, so a session running it follows `coding-agent-usage-line-report-eta`.

## Priority and admission control

- **Priority:** on macOS each session starts under `taskpolicy -c utility`, so the scheduler favours interactive work and everything the session starts inherits the class. Elsewhere it starts at normal priority. `--no-admission` keeps the utility class.
- **Memory pressure:** before starting, the script reads `kern.memorystatus_vm_pressure_level`: 1 (normal) starts the run; 2 (warning) or 4 (critical) holds it, rechecking every few seconds and saying so on a progress line, `waiting <label> <time>: memory pressure level <n>`. A run already going is never stopped. A level that can't be read, or isn't 1, 2 or 4, counts as 1, with a note in the outcome. Off macOS there is nothing to read, so the run starts.
- **Disk space:** the script also reads the free space on the checkout's volume and on `/nix` with `shutil.disk_usage`, and holds the run the same way while either is below the build floor, the one agents' builds stop at, which it asks `git-worktree-manager` for: the `floors.build_gb` of `git-worktree-manager disk --format json` in the checkout.
  It measures the free space itself, since it measures again every few seconds while it waits.
  Without the program, or when its reply holds no floor, the floor is `WORKTREE_MANAGER_FLOOR_BUILD_GB` from the environment, else 70 GB, with a note in the outcome when the program gave none.
  A floor that isn't a finite number of GB above 0 counts as none.
  A volume that can't be read, such as `/nix` on a machine without Nix, holds nothing.
  The progress line names the volume, its free space and the floor.
- **Giving up:** `--admission-timeout <minutes>` ends the wait with status `skipped` and exit status 3, so a fan-out moves on; the checkout's work is untouched, no worktree is made and nothing is swept.
  Without it the run waits as long as it takes; with `--no-admission` it doesn't wait at all, for a run that must go whatever the pressure or free space.
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

- **Worktree (default):** the run gets `<checkout>.worktrees/headless-<job>`, beside the checkout, on a new branch `headless/<job>` from the checkout's `HEAD`.
  The checkout's working tree is never touched, so a run can't collide with uncommitted work or an open session.
  Uncommitted changes in the checkout are not in the worktree.
  The worktree is locked while its session works, so no sweep removes it, as [Cleaning up](#cleaning-up) says.
  A rerun with the same `--job` reuses the worktree.
- **Uncommitted work:** a worktree has only what's committed, so a session continued in one can remember edits that stayed behind in the checkout. For a checkout with uncommitted changes, `--dirty` decides what a continuing worktree run does: `tell` (the default) continues, and opens the prompt with a note naming the uncommitted paths and saying their changes aren't there; `new` starts a new session instead; `skip` doesn't run until the work is committed or stashed. Tell the user which checkouts are dirty before the run, from the dry run's notes.
- **Checkout:** the run works in the checkout itself. Use it only when the checkout is clean and no one else is working there.
- **New or continued:** a new session is the default, and right for a wave, whose prompt carries all the context the run needs. Continue only to follow up on what that checkout's own session was doing.
- **Continuing:** Claude Code keeps a directory's sessions in `~/.claude/projects/<the path, every non-alphanumeric character turned into ->/`. The script takes the newest `.jsonl` there and forks it: `--continue --fork-session` in the checkout, or `--resume <the .jsonl> --fork-session` in a worktree, whose new directory has no sessions of its own. The fork leaves the original session as it was, for a window that may still have it open. A checkout with no session gets a new one. Every session the script starts is named `headless <job>`.
- **A session that may still be running:** when the newest transcript was written in the last `--live-within` minutes, 10 by default, the script warns on stderr and in the outcome's notes. The fork is a copy as of that moment: it won't see what the live session does next, and in `--where checkout` the two can edit the same files.

## The Nix environment

Each run gets the checkout's environment the way a manual session does:

- **Through a plugin:** a checkout whose dev shell reaches Claude Code through a plugin, one that loads it into every Bash command, needs nothing more, since `claude -p` loads plugins.
- **Through direnv:** a checkout with an `.envrc` runs under `direnv exec <dir>`.
  direnv trusts an `.envrc` by its path, so a new worktree's copy starts blocked, and `direnv exec` refuses a blocked `.envrc` outright.
  In a worktree the script therefore calls `git-worktree-manager provision --format json <worktree>` first, which allows the copy when it is byte for byte the checkout's own, and runs under `direnv exec` only when the reply's `direnv` step is `done`.
  Without `git-worktree-manager`, or when that step is skipped or failed, the session starts without `direnv exec`, and a note in the outcome says so.

## Reading the results

Progress goes to stderr, each line opening on the run's label: one when the session starts, one every `--progress-every` seconds, 60 by default, with its time, its tool calls so far and the tool it called last, and one when it ends. When the agent runs a fan-out in the background, it reads that output only when the user asks how it's going.

The outcome goes to stdout as one JSON line, and to `<label>.outcome.json` in the log folder, `$XDG_STATE_HOME/coding-agent-headless/<job>/` by default: its `status` (`ok`, `failed`, `limit` or `skipped`), exit `code`, `session_id`, `resumed_from`, `turns`, the start of the final `result`, its `log`, its `notes` and its `cleanup`, what became of the worktree (`null` for a run in the checkout), which the progress line that ends the run repeats in brackets.
The session's full stream-json output and stderr are beside it.
The exit status says the same: 0 ok, 1 failed or timed out, 2 bad arguments, 3 skipped, 255 a usage limit.

### The live status file

While a run goes, the script keeps `<label>.status.json` beside the outcome, rewritten every `--status-every` seconds, 10 by default, and once more when the run ends. Each write goes to a temporary file that is then renamed over it, so a reader never sees half a record. The `coding-agent-headless-runs` mod in this repository draws these files in a pane. One JSON object:

| Field                              | Holds                                                                                                                                                                                                                                           |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `job`, `label`                     | the run's `--job` and `--label`                                                                                                                                                                                                                 |
| `checkout`, `workdir`, `branch`    | the checkout, where the session works, and that directory's branch: `headless/<job>` in a worktree                                                                                                                                              |
| `log`                              | the stream-json log's path                                                                                                                                                                                                                      |
| `session_id`, `transcript`         | the session's id and its transcript's path, once the session has said its id; `null` before                                                                                                                                                     |
| `state`                            | `waiting` (held by admission control), `running`, then `ok`, `failed`, `limit` or `skipped`; a killed runner leaves `waiting` or `running`, which the pane shows as `killed`                                                                    |
| `started`, `updated`, `ended`      | ISO 8601 date-times in UTC: when the runner began, the last write, and the end (`null` until then)                                                                                                                                              |
| `turns`, `tool_calls`, `last_tool` | from the stream log so far; `turns` is the result's own count once the run ends                                                                                                                                                                 |
| `eta`                              | the last `coding-agent-usage-line-report-eta` line the session wrote: `figure` (`4m`), `seconds`, `count` (how many it has written) and `at`, when; `null` before the first one                                                                 |
| `pid`, `status_every`              | the runner's process id, and its `--status-every` in seconds                                                                                                                                                                                    |
| `parent`                           | the session that started the runner: `session_id` and `pid` from the `CLAUDE_CODE_SESSION_ID` and `CLAUDE_PID` Claude Code exports to Bash (outside Claude Code, no id and the parent process's pid), and `cwd`, the runner's working directory |

The ETA's `at` is the transcript entry's timestamp; where the transcript can't be read, it is the first write that saw the line, so it is late by at most `--status-every`.

A runner that is killed writes no end, so its record stays `waiting` or `running`. Such a record belongs to a killed runner when no process has its `pid`, or when its `updated` is older than 10 minutes and 3 × `status_every`, whatever its `pid`, since the system may have given the pid to a later process; a record with `status_every` 0 isn't rewritten while its session runs, so only its `pid` says. The pane shows such a run as `killed`, ended at its last write. A rerun under the same job and label replaces the record on its first write.

Report each checkout's outcome to the user by its name, with the branch of any worktree that holds changes. A run's own work, such as a pull request it opened, is in its result text and log.

### A job's figures

How many of a job's runs ended `ok`, `failed`, `limit` or `skipped` comes from the job's outcome files, counted by the jq program `scripts/job_summary.jq` beside the runner:

```bash
folder="${XDG_STATE_HOME:-$HOME/.local/state}/coding-agent-headless/<job>"
find "$folder" -maxdepth 1 -name '*.outcome.json' -exec cat {} + |
  jq --slurp --raw-input --arg job <job> --arg folder "$folder" --from-file scripts/job_summary.jq
```

It prints one JSON object with the job, the folder, the number of runs and the count in each state, every state listed even at zero; add `--raw-output --arg format table` for a table. For a job run with `--log-dir`, set `folder` to that folder. Run it when writing the report, and name it beside the figures it gave. A run still going has no outcome file yet, so it is in none of the counts; an outcome file without a status counts as `unreadable`. A job with no outcome files prints zero counts, and jq exits 0.

## Limits and billing

- **Subscription, not the API:** `claude -p` bills `ANTHROPIC_API_KEY` whenever it is set, so the script refuses to start while it is, unless given `--allow-api-key`. `claude auth status` shows the login in use.
- **Usage limits:** a headless run can't wait for a limit to reset. A run that fails on a usage limit exits 255, and xargs, GNU or BSD, starts no more commands after one exits 255, so an xargs fan-out stops there by itself. A caller that loops instead checks for 255 and stops. Rerun the checkouts with no outcome file, or one whose status is `limit`, after the reset, with the same `--job` to reuse their worktrees.
- **Trust:** a headless session runs a checkout's hooks and `.mcp.json` servers without a trust dialog, and auto mode approves actions without a person. Run only in checkouts the user owns, named one by one.

## Cleaning up

The script makes the run's worktree locked, with `git worktree add --lock --reason "headless <job> pid <pid> since <UTC ISO time>"`, the `<who> since <time>` form `git-worktree-manager` reads, and a sweep leaves a locked worktree, so another run's sweep can't remove it while the session works.
`git-worktree-manager status` shows the lock, with its `who`, `pid`, `since` and whether its process is `alive`.
When the session ends, however it ends, Ctrl-C included, the script unlocks the worktree, before finishing it, and with `--keep-worktree` or without the program too, since the session is over in each case.
It first reads the lock again, from the `locked` file in the worktree's git directory, and unlocks it only while the reason is still this run's own; a lock that is gone or someone else's by then is left, with a note.
A lock that can't be read, as when the checkout went during the session, is left too, with a note giving git's error, and so is a failed unlock.
A runner that is killed leaves its lock, and the worktree stays until a rerun of its job takes the lock over or someone runs `git worktree unlock <worktree>`.
A worktree reused on a rerun of the same `--job` is locked again for the run, unless its lock can't be read, which is a note, and the run then goes on without a lock:

- **An earlier run's lock,** one whose reason starts `headless <job> pid ` and whose process is gone, is taken over with this run's reason, and a note names the old one.
  The process is gone when `git-worktree-manager status` says the lock isn't `alive`, which also tells a pid a later process reused.
  Where `status` gives no answer, without the program, or when its call fails, times out or names no such worktree, the process is gone when no process has the pid.
  When the old lock is released but the new one fails, the note says both.
- **Anyone else's lock,** a live run's of the same job included, is left as it is, with a note naming its reason, and is not unlocked at the end.
  The run goes on in the worktree all the same.

With `git-worktree-manager` on the `PATH`, the script finishes its own worktree when the run ends, and the outcome's `cleanup` says how:

- **No commits** on `headless/<job>`, whether the run succeeded or failed: `git-worktree-manager finish --format json <worktree>` removes the worktree and its branch when the worktree's `HEAD` is merged into `origin/<default>`.
  It also removes them when the branch's content has landed, as after a squash merge, or its name matches a `worktreeManager.disposable` pattern, archiving the branch first.
  Otherwise it keeps both and exits 3 with `not-landed`, as it does for a run that changed nothing in a checkout ahead of origin or on a branch of its own.
  When its reasons include `not-landed` but neither `uncommitted` nor `locked`, the script then runs `git-worktree-manager clean --format json <worktree>`, so the worktree and its branch stay without their build output.
  A locked worktree gets no `clean`, which would keep it too.
  `cleanup` gives `finish`'s reasons, then what `clean` did, its failure or its own exit 3 included.
  The stream log is outside the worktree, so nothing of the run goes with it, and the program keeps a worktree with uncommitted changes.
- **Committed:** `git-worktree-manager clean --format json <worktree>` deletes its build output, and the worktree waits for its branch to land.

Exit status 3 from either means the program kept the worktree, and `cleanup` gives its reasons, such as uncommitted changes, a branch that hasn't landed or a lock; it is no failure.
Any other status is in `cleanup` with what the program's JSON reply says failed, else the last line it said on stderr.
A checkout gone during the session makes `cleanup` say `could not finish <worktree>: <error>`, and the run keeps the status its session gave.

Before making a worktree the script runs `git-worktree-manager sweep` in the checkout, which acts on every worktree and branch of the repository, not only earlier jobs':

- it deletes each landed branch, except one checked out in a worktree that stays;
- it archives and then deletes content-landed branches and those matching `worktreeManager.disposable`, `preview/*` by default;
- it removes worktrees that are landed, clean, idle and unlocked and hold no kept files of their own;
- it prunes worktrees whose folder is gone, and deletes orphaned build output.

It waits for a sweep already running in the repository, then acts.
Each call to the program is cut off after 15 minutes, that wait included; a `sweep`, `finish` or `clean` cut off says `exit 124: timed out after 900s` in its note.
The program deletes only what is merged or archived, and keeps anything with uncommitted changes, so a branch still to review stays.
A sweep that exits 1, for a step that failed, is a note in the outcome, and the run goes on.
`--keep-worktree` turns off the sweep and the finish, for a run someone wants to inspect.

To finish a job's worktree by hand, such as one `--keep-worktree` left, run `git-worktree-manager finish <checkout>.worktrees/headless-<job>`; `git-worktree-manager sweep` in the checkout removes all of its landed ones.
Without the program the script keeps every worktree and says in `cleanup` that nothing was cleaned; remove each then by its path and branch name once its changes are merged or dropped, as `shell-hygiene-delete-named-paths` and `git-workflow-tidy-branches` say.

## Your preferences

!`cat "$(dirname "${CLAUDE_SKILL_DIR}")/coding-agent-headless-in-checkout.preferences.md" "${CLAUDE_PROJECT_DIR}/.agents/skills/coding-agent-headless-in-checkout.preferences.md" 2>/dev/null || true`

If your agent doesn't run the line above, read these files yourself if they exist: `coding-agent-headless-in-checkout.preferences.md` next to this skill's folder, then `.agents/skills/coding-agent-headless-in-checkout.preferences.md` in the project.
A project's file overrides the user's, and the user's overrides this skill's defaults.

## Related skills

When one of these applies and it's in your skill listing, load it without asking.
If it isn't in your listing, tell the user which skill is missing and ask whether to install it from the same collection this skill came from; don't apply it from memory.

- `coding-agent-usage-line-report-eta`: report a running ETA while a run or a fan-out goes, since either takes minutes to an hour.
- `coding-agent-kanban-turn-responses`: where a figure in a status item comes from, and how one that can't be queried is given.
- `shell-hygiene-delete-named-paths`: remove each finished worktree by its own path, never by glob.
- `git-workflow-tidy-branches`: delete the `headless/<job>` branches once their work is merged or dropped.
