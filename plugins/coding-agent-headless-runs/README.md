# coding-agent-headless-runs

A Claude Code mod that shows the headless sessions the [`coding-agent-headless-in-checkout` skill](../../skills/coding-agent-headless-in-checkout/SKILL.md) runs, in a pane beside the chat. Each run's `run_headless.py` keeps a live status file, and the pane reads them every few seconds, so you can watch a wave across many repositories without reading its logs.

## Install

At the prompt of a terminal session:

```text
/plugin install coding-agent-headless-runs --marketplace nhooey/coding-agent-skills
```

Answer `y` to add the marketplace, then choose a scope. From a shell:

```bash
claude plugin install coding-agent-headless-runs --marketplace nhooey/coding-agent-skills
```

## What it draws

```text
wave-3 · 🏃 2 · ✅ 3 · ❌ 1
  🏃 app · 12m03s · ETA 4m10s · 23 turns · 87 tools · last Bash
  🏃 site · 3m40s · 1m05s past ETA 2m · 6 turns · 14 tools · last Edit
  ❌ api · 30m00s · 41 turns · 120 tools · last Bash
tidy · ✅ 1
  ✅ notes · 2m11s · 4 turns · 9 tools · last Write
```

- **Groups:** runs of one job sit under the job's name, with a count per state. Jobs with a run going come first, then the most recently written.
- **Rows:** running and waiting runs come first, then those that finished in the last 6 hours, latest first. Each row has:
  - the state: 🏃 running, ⏳ waiting on memory pressure, ✅ ok, ❌ failed or hit a usage limit, 💤 skipped;
  - the label, the checkout's name unless the run set `--label`;
  - the time it has run, or ran;
  - the ETA counting down from the session's last `coding-agent-usage-line-report-eta` line, or how far past it the run has gone;
  - turns, tool calls and the last tool.
- **A stalled runner:** a running row whose status file hasn't changed for 2 minutes says `no update for <time>`, since its runner was most likely killed.
- **A row is a button:** clicking it copies `cd '<workdir>' && claude --resume <session id>`, to open the run's session by hand; before the session has an id, it copies the stream log's path.

## Opening it

- **By itself:** when a run started from this session is running or waiting, the pane opens. It knows the run is this session's from the `parent.session_id` in the status file, which `run_headless.py` takes from the `CLAUDE_CODE_SESSION_ID` Claude Code exports to Bash. It opens once per run: closed by hand, it stays closed until another run of this session's starts. A terminal narrower than 144 columns places a pane nobody asked for only once you open it.
- **`/runs`:** opens the pane, or closes it when it is open.

## Where the runs come from

The mod reads `<state>/coding-agent-headless/*/*.status.json`, where `<state>` is `$XDG_STATE_HOME`, or `~/.local/state` when that is unset: the runner's default log folder. A run given its own `--log-dir` elsewhere doesn't show. Files last written more than 6 hours ago are skipped. The skill's [The live status file](../../skills/coding-agent-headless-in-checkout/SKILL.md#the-live-status-file) section lists the fields.

## Developing

From the repository's dev shell:

```bash
check-mods coding-agent-headless-runs
```

It runs `claude plugin validate`, `tsc -p` and `claude plugin test` on the mod, through [`../check-mods.sh`](../check-mods.sh); with no name it checks every mod in the repository. To try the mod without installing it:

```bash
claude --plugin-dir plugins/coding-agent-headless-runs
```

| File                                       | Holds                                                                         |
| ------------------------------------------ | ----------------------------------------------------------------------------- |
| [`hooks/register.tsx`](hooks/register.tsx) | the hooks: the pane, `/runs`, the read every 3 seconds, opening by itself     |
| [`hooks/runs.ts`](hooks/runs.ts)           | the pure core: reading a status record, choosing and grouping rows, the words |
| [`types/index.d.ts`](types/index.d.ts)     | the run shape and the `$.state` contract                                      |
| [`tests/`](tests/)                         | the core's tests, and the pane and `/runs` driven through the engine          |
