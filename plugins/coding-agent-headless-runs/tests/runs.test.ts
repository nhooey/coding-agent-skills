import { describe, expect, test } from "claude-code/testing";

import {
  alivePids,
  copyText,
  duration,
  etaText,
  groupHeader,
  groups,
  isKilled,
  livePids,
  newOwnLive,
  parseStatus,
  rowText,
  runKey,
  shown,
  silenceLimit,
  withKilled,
} from "../hooks/runs";
import type { RunStatus } from "../types";

const T0 = Date.parse("2026-11-16T01:00:00Z");
const MIN = 60_000;

/** A status file's JSON as run_headless.py writes it. */
const file = (fields: Record<string, unknown> = {}) => ({
  job: "wave-1",
  label: "alpha",
  checkout: "/git/alpha",
  workdir: "/git/alpha.worktrees/headless-wave-1",
  branch: "headless/wave-1",
  log: "/state/wave-1/alpha.stream.jsonl",
  session_id: "sess-1",
  transcript: "/p/sess-1.jsonl",
  state: "running",
  started: "2026-11-16T01:00:00+00:00",
  updated: "2026-11-16T01:10:00+00:00",
  ended: null,
  turns: 12,
  tool_calls: 40,
  last_tool: "Bash",
  eta: {
    figure: "20m",
    seconds: 1200,
    count: 2,
    at: "2026-11-16T01:05:00+00:00",
  },
  pid: 10,
  parent: { session_id: "me", pid: 9, cwd: "/git/plan" },
  ...fields,
});

const run = (fields: Record<string, unknown> = {}): RunStatus => {
  const parsed = parseStatus(file(fields));

  if (parsed === undefined) {
    throw new Error("not a status record");
  }

  return parsed;
};

describe("parseStatus", () => {
  test("reads the runner's fields", () => {
    expect(run()).toEqual({
      job: "wave-1",
      label: "alpha",
      workdir: "/git/alpha.worktrees/headless-wave-1",
      branch: "headless/wave-1",
      log: "/state/wave-1/alpha.stream.jsonl",
      sessionId: "sess-1",
      state: "running",
      started: T0,
      updated: T0 + 10 * MIN,
      ended: null,
      turns: 12,
      toolCalls: 40,
      lastTool: "Bash",
      eta: { figure: "20m", seconds: 1200, at: "2026-11-16T01:05:00+00:00" },
      pid: 10,
      statusEvery: null,
      parentSessionId: "me",
    });
  });

  test("refuses what is not a status record", () => {
    expect(parseStatus(null)).toBeUndefined();
    expect(parseStatus(file({ state: "done" }))).toBeUndefined();
    expect(parseStatus(file({ started: "never" }))).toBeUndefined();
  });

  test("takes missing optional fields as unknown", () => {
    const r = run({ session_id: null, eta: null, parent: null, turns: null });
    expect([r.sessionId, r.eta, r.parentSessionId, r.turns]).toEqual([
      null,
      null,
      null,
      null,
    ]);
  });
});

describe("the rows", () => {
  test("durations read compactly", () => {
    expect([duration(12_000), duration(245_000), duration(3_725_000)]).toEqual([
      "12s",
      "4m05s",
      "1h02m",
    ]);
  });

  test("the ETA counts down from its report, then says how far past it", () => {
    expect(etaText(run(), T0 + 10 * MIN)).toBe("ETA 15m00s");
    expect(etaText(run(), T0 + 28 * MIN)).toBe("3m00s past ETA 20m");
    expect(etaText(run({ state: "ok" }), T0 + 10 * MIN)).toBeUndefined();
    expect(etaText(run({ eta: null }), T0)).toBeUndefined();
  });

  test("a row holds the state, label, elapsed time, ETA, turns and tools", () => {
    expect(rowText(run(), T0 + 10 * MIN)).toBe(
      "🏃 alpha · 10m00s · ETA 15m00s · 12 turns · 40 tools · last Bash",
    );
    expect(
      rowText(
        run({ state: "limit", ended: "2026-11-16T01:30:00+00:00" }),
        T0 + 90 * MIN,
      ),
    ).toBe("❌ alpha · 30m00s · 12 turns · 40 tools · last Bash");
  });

  test("a live run whose runner stopped writing says so", () => {
    expect(rowText(run(), T0 + 20 * MIN)).toContain("no update for 10m00s");
  });

  test("a row copies the resume command, else the log's path", () => {
    expect(copyText(run())).toBe(
      "cd '/git/alpha.worktrees/headless-wave-1' && claude --resume sess-1",
    );
    expect(copyText(run({ session_id: null }))).toBe(
      "/state/wave-1/alpha.stream.jsonl",
    );
    expect(copyText(run({ workdir: "/a/it's" }))).toContain(`'/a/it'\\''s'`);
  });
});

describe("a run whose runner is gone", () => {
  const now = T0 + 11 * MIN;
  const alive = new Set([10]);

  test("ps's reply gives the pids it found, or null when it failed", () => {
    expect(alivePids(0, "   10\n  412\n", "")).toEqual(new Set([10, 412]));
    expect(alivePids(1, "", "")).toEqual(new Set());
    expect(alivePids(1, "", "ps: illegal option")).toBeNull();
    expect(alivePids(2, "", "")).toBeNull();
  });

  test("only live runs' pids are asked about, each once", () => {
    const finished = run({ label: "beta", state: "ok", pid: 11 });
    const twin = run({ label: "gamma", pid: 10 });
    const noPid = run({ label: "delta", pid: null });
    expect(livePids([run(), finished, twin, noPid])).toEqual([10]);
  });

  test("a live run whose pid is gone is killed, ended at its last write", () => {
    const [killed] = withKilled([run()], now, new Set());
    expect(killed?.state).toBe("killed");
    expect(killed?.ended).toBe(T0 + 10 * MIN);
    expect(
      withKilled([run({ state: "waiting" })], now, new Set())[0]?.state,
    ).toBe("killed");
    expect(withKilled([run()], now, alive)[0]?.state).toBe("running");
  });

  test("a live pid that hasn't written for 10 minutes is a later process's", () => {
    expect(isKilled(run(), T0 + 20 * MIN, alive)).toBe(false);
    expect(isKilled(run(), T0 + 20 * MIN + 1, alive)).toBe(true);
    expect(isKilled(run(), T0 + 20 * MIN + 1, null)).toBe(true);
  });

  test("the silence allowed grows with a slow runner, and is endless for one that writes only at the end", () => {
    expect(silenceLimit(run({ status_every: 10 }))).toBe(10 * MIN);
    expect(silenceLimit(run({ status_every: 600 }))).toBe(30 * MIN);
    expect(isKilled(run({ status_every: 0 }), T0 + 600 * MIN, alive)).toBe(
      false,
    );
  });

  test("an unknown pid, or one ps couldn't check, leaves a writing run running", () => {
    expect(isKilled(run({ pid: null }), now, new Set())).toBe(false);
    expect(isKilled(run(), now, null)).toBe(false);
  });

  test("a finished run is never killed", () => {
    expect(isKilled(run({ state: "ok" }), T0 + 600 * MIN, new Set())).toBe(
      false,
    );
  });

  test("a killed run's row says so, and counts with the failed", () => {
    const [killed] = withKilled([run()], now, new Set());
    if (killed === undefined) {
      throw new Error("no run");
    }
    expect(rowText(killed, now)).toBe(
      "❌ alpha · killed · 10m00s · 12 turns · 40 tools · last Bash",
    );
    expect(groupHeader({ job: "wave-1", runs: [killed] })).toBe(
      "wave-1 · ❌ 1",
    );
    expect(newOwnLive([killed], "me", [])).toEqual([]);
  });
});

describe("choosing and grouping", () => {
  const now = T0 + 10 * 60 * MIN;

  test("finished runs leave after the window; live ones stay", () => {
    const old = run({ state: "ok", ended: "2026-11-16T02:00:00+00:00" });
    const recent = run({ state: "ok", ended: "2026-11-16T09:00:00+00:00" });
    const live = run({ started: "2026-11-16T00:00:00+00:00" });
    expect(shown([old, recent, live], now)).toEqual([recent, live]);
  });

  test("groups put live runs first, and count by state", () => {
    const done = run({
      label: "beta",
      state: "failed",
      ended: "2026-11-16T01:20:00+00:00",
      updated: "2026-11-16T01:20:00+00:00",
    });
    const other = run({
      job: "wave-2",
      state: "ok",
      ended: "2026-11-16T01:30:00+00:00",
      updated: "2026-11-16T01:30:00+00:00",
    });
    const live = run({ label: "gamma" });
    const waiting = run({ label: "delta", state: "waiting" });
    const list = groups([other, done, live, waiting]);
    expect(list.map((g) => g.job)).toEqual(["wave-1", "wave-2"]);
    expect(list[0]?.runs.map((r) => r.label)).toEqual([
      "gamma",
      "delta",
      "beta",
    ]);
    expect(list.map(groupHeader)).toEqual([
      "wave-1 · 🏃 1 · ⏳ 1 · ❌ 1",
      "wave-2 · ✅ 1",
    ]);
  });

  test("the pane opens for a live run of this session's once", () => {
    const mine = run();
    const theirs = run({ label: "beta", parent: { session_id: "other" } });
    const finished = run({ label: "gamma", state: "ok" });
    expect(newOwnLive([mine, theirs, finished], "me", [])).toEqual([
      runKey(mine),
    ]);
    expect(newOwnLive([mine], "me", [runKey(mine)])).toEqual([]);
  });
});
