---
name: coding-agent-keep-computer-awake
description: Keep the computer awake / prevent the Mac from sleeping while a coding agent processes a user prompt — start a tagged `claffeinate` instance so the laptop cannot sleep, idle, or dim its display. macOS implementation; a sibling Linux skill (planned) will cover `systemd-inhibit`. Skip silently on non-Darwin hosts. Trigger at the start of *every* user-prompt turn (not just long-running ones); the call is idempotent and ~free after the first time. Also handle reaping when the user closes the tab.
---

# Keep the computer awake during coding-agent prompts (macOS)

When a coding agent is mid-prompt — running tests, waiting on a sub-agent,
building a flake, monitoring CI — macOS will happily sleep, idle, or dim
the display out from under us. Wake-on-network rarely saves long-running
jobs cleanly, and the user usually has no signal that the laptop drifted
off until they come back to a stalled session.

The fix is a thin wrapper around macOS's built-in `caffeinate(1)` that tags
each instance with the agent session (terminal tab / IDE pane) that owns
it, so multi-tab workflows don't kill each other's instances:
[`github:nhooey/claffeinate`](https://github.com/nhooey/claffeinate).

The pattern: **at the start of every prompt-handling turn on macOS, run
`claffeinate start --timeout 3600` so caffeinate is asserted for the next
hour. The call is idempotent — a second `start` in the same tab returns
"already running" without spawning a duplicate — so calling it on every
turn is cheap.**

## When this skill applies

Trigger at the very start of handling **every** user prompt, before any
substantive tool use. Specifically:

- macOS only. Probe with `[ "$(uname -s)" = "Darwin" ]`. Skip silently on
  non-Darwin hosts — those don't have `caffeinate(1)`. A Linux equivalent
  using `systemd-inhibit` is planned as a sibling skill; until that exists,
  Linux/WSL laptops are not covered by this marketplace.
- Skip when the user has explicitly said "let it sleep" or "don't caffeinate"
  for the rest of the session.
- Don't re-trigger mid-prompt. Once per turn at the start is enough;
  idempotency means a second call is a no-op, but the round-trip through
  `nix run` still costs a few hundred ms of cold-start, so don't spam it.

The trigger is **not** "only on long-running prompts" — by the time the
assistant knows a prompt will be long, the laptop may already be drifting
toward sleep. Always start the assertion up-front.

## Wiring up the assertion

Run via the published Nix flake so there's nothing to install:

```sh
if [ "$(uname -s)" = "Darwin" ]; then
  nix run github:nhooey/claffeinate -- start --timeout 3600 \
    >/dev/null 2>&1 || true
fi
```

Notes:

- **Output is suppressed.** `claffeinate start` either prints the new PID or
  `already running: PID=<pid>`; neither is useful to surface to the user on
  every turn. `|| true` makes a non-Darwin or transient failure a no-op.
- **`--timeout 3600` is the safety backstop.** caffeinate exits on its own
  after 1 hour even if the agent session is still running. Long enough that
  realistic prompt durations almost never hit it; short enough that a
  silently-orphaned instance doesn't keep the laptop awake all night.
  Re-running `start` on the _next_ prompt restarts the timer (a fresh
  `start` after the previous instance has exited).
- **First-call cost.** The first `nix run` on a fresh machine downloads
  claffeinate and `jq`. Subsequent calls hit the Nix store and run in
  ~100 ms. If the user complains about per-prompt latency, recommend
  `nix profile install github:nhooey/claffeinate` so `claffeinate` is on
  PATH directly and the wrapper script's startup is the only cost.
- **Default assertion is `--display`.** No flag → `caffeinate -d`, which
  also implicitly prevents idle and disk sleep. That's the right default
  for "an agent is working at this terminal." Don't pass `--system` unless
  the user is doing something that explicitly needs CPU-active sleep
  prevention (rare).

### Refreshing the timer mid-session

`claffeinate start` is idempotent: while the existing instance is alive, a
new `start` call **does not reset its `--timeout`**. The 1-hour clock keeps
counting from the original start. For typical conversational use this is
fine — turns are usually well under an hour, and once one instance expires
the next prompt's `start` boots a fresh 1-hour window.

If the assistant is doing something it knows will exceed an hour (a long
agent run, a multi-hour build, a `Monitor` loop on a slow CI), refresh the
timer up-front:

```sh
nix run github:nhooey/claffeinate -- kill-mine >/dev/null 2>&1 || true
nix run github:nhooey/claffeinate -- start --timeout 14400 \
  >/dev/null 2>&1 || true
```

Pick the timeout to match the expected upper bound of the work, not "as
large as possible" — the timeout exists precisely so a forgotten or crashed
session doesn't pin the laptop awake forever.

## Cleanup: orphan reaping

claffeinate's tagging scheme (`caffeinate--claffeinate--tab-<TERM_SID>-<SSE_PORT>--dir-<basename>`)
makes it possible to detect instances whose agent session has died. The
recommended hook lives in the user's shell startup file rather than in this
skill — but mention it if the user asks "how do I clean these up?":

```sh
# ~/.zshrc / ~/.bashrc / ~/.config/fish/config.fish
command -v claffeinate >/dev/null && claffeinate kill-orphans >/dev/null 2>&1 &
```

Within a session, `claffeinate kill-mine` removes the current tab's
instance — useful if the user wants to allow sleep right now.

## Gotchas worth remembering

- **macOS only.** `caffeinate(1)` is a Darwin built-in; the flake's
  `systems` list is restricted to `aarch64-darwin` and `x86_64-darwin` for
  this reason. There is no Linux/WSL fallback in claffeinate — guard with
  `uname -s` and skip.
- **Idempotency hides timer-not-resetting.** A second `start` in the same
  tab cheerfully returns "already running" without changing anything. If
  the assistant _needs_ a fresh window, `kill-mine; start` is the only
  correct refresh — see the section above.
- **`TERM_SESSION_ID=unknown` instances get reaped aggressively.** SSH
  sessions without iTerm/JediTerm don't set `TERM_SESSION_ID`, so
  claffeinate uses the literal `unknown`. `kill-orphans` will treat any
  such instance as dead because no `claude` process can advertise that
  combination. Accepted behavior; just be aware.
- **IDE-integrated mode owns the SSE port (Claude Code example).** When
  Claude Code runs inside WebStorm / VS Code / JetBrains,
  `CLAUDE_CODE_SSE_PORT` is held by the IDE, not by `claude`. claffeinate
  handles this correctly via `pgrep -x claude` plus `ps -E` env-match —
  don't try to "improve" liveness detection with `lsof` on the port; it
  will mistake the IDE for Claude. Other coding agents that ship an IDE
  bridge will have equivalent symptoms — substitute the agent's process
  name and bridge-port env var when applying this lesson.
- **Don't double-caffeinate.** If the user is already running `caffeinate`
  by hand, claffeinate will start a _second_ assertion (different tag).
  Both are fine independently, but the user may be surprised to see two
  processes in `pgrep caffeinate`. If they ask, `claffeinate list` shows
  only the tagged ones.

## Reference: where this advice comes from

This skill targets the `claffeinate` interface as of commit
[`c436b2b`](https://github.com/nhooey/claffeinate/tree/c436b2b851d5a68afe98a01cd935846b8efc2904).
If `claffeinate`'s CLI surface changes upstream, update this skill against
these specific anchors (the URLs are pinned to the commit so they remain
stable even after `master` moves):

- **CLI surface (`start --timeout`, idempotency, exit codes):**
  [`SPECIFICATION.md` "CLI surface"](https://github.com/nhooey/claffeinate/blob/c436b2b851d5a68afe98a01cd935846b8efc2904/SPECIFICATION.md#cli-surface)
  and
  [`SPECIFICATION.md` "Behavior detail → cmd_start"](https://github.com/nhooey/claffeinate/blob/c436b2b851d5a68afe98a01cd935846b8efc2904/SPECIFICATION.md#cmd_start).
  These are the source of truth for "long options are canonical", the
  default-`--display` behavior, and the "already running" idempotency
  contract this skill relies on.
- **`start` subcommand implementation:**
  [`bin/claffeinate.sh` lines 206–292](https://github.com/nhooey/claffeinate/blob/c436b2b851d5a68afe98a01cd935846b8efc2904/bin/claffeinate.sh#L206-L292).
  This is where flag parsing, the idempotency check (existing pidfile +
  `kill -0`), and the `--timeout` translation to `caffeinate -t SECS` live.
- **User-facing usage docs:**
  [`README.md` "Subcommands"](https://github.com/nhooey/claffeinate/blob/c436b2b851d5a68afe98a01cd935846b8efc2904/README.md#subcommands)
  and
  [`README.md` "Reap orphans on shell startup"](https://github.com/nhooey/claffeinate/blob/c436b2b851d5a68afe98a01cd935846b8efc2904/README.md#reap-orphans-on-shell-startup).
- **Flake / install surface (`nix run`, `nix profile install`):**
  [`README.md` "Via the Nix flake"](https://github.com/nhooey/claffeinate/blob/c436b2b851d5a68afe98a01cd935846b8efc2904/README.md#via-the-nix-flake)
  and
  [`flake.nix` `packages.default`](https://github.com/nhooey/claffeinate/blob/c436b2b851d5a68afe98a01cd935846b8efc2904/flake.nix#L38-L58).
  The Darwin-only platform restriction this skill mirrors is at
  [`flake.nix` lines 25–28](https://github.com/nhooey/claffeinate/blob/c436b2b851d5a68afe98a01cd935846b8efc2904/flake.nix#L25-L28).

To re-pin these references, fetch the latest `master` SHA from
`github.com/nhooey/claffeinate`, replace every occurrence of
`c436b2b851d5a68afe98a01cd935846b8efc2904` (and the short `c436b2b`) above
with the new SHA, and verify each linked anchor still resolves to the
material this skill cites — line numbers in `bin/claffeinate.sh` in
particular tend to drift between revisions.

## Cross-references

- [`github:nhooey/claffeinate`](https://github.com/nhooey/claffeinate) —
  the upstream tool this skill drives.
- `coding-agent-garnix-ci` skill — the structural template this skill
  follows: trigger after a specific assistant action, run a small bounded
  background helper, swallow output unless something actionable happens.
