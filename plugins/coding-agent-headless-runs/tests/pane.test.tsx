import { expect, mock, test } from "claude-code/testing";
import type { On } from "claude-code";

const PLUGIN = "coding-agent-headless-runs";
const ROOT = "/state/coding-agent-headless";
const T0 = Date.parse("2026-11-16T01:00:00Z");
const MIN = 60_000;

const PANE = {
  plugin: PLUGIN,
  component: "Pane",
  requestId: "headless-runs",
  props: {
    title: "Headless runs",
    isFocused: false,
    bodyColumns: 100,
    placement: "dock",
    scroll: { offset: 0, bodyRows: 20 },
    view: {},
  },
} as const;

const RUNS = {
  command: "runs",
  args: "",
  origin: { kind: "composer" },
  presentation: { isFullscreen: true, columns: 100 },
} as const;

/** A status file's JSON as run_headless.py writes it. */
const status = (fields: Record<string, unknown>) =>
  JSON.stringify({
    job: "wave-1",
    label: "alpha",
    workdir: "/git/alpha.worktrees/headless-wave-1",
    branch: "headless/wave-1",
    log: `${ROOT}/wave-1/alpha.stream.jsonl`,
    session_id: "sess-1",
    state: "running",
    started: "2026-11-16T01:00:00+00:00",
    updated: "2026-11-16T01:04:59+00:00",
    ended: null,
    turns: 3,
    tool_calls: 9,
    last_tool: "Bash",
    eta: { figure: "10m", seconds: 600, count: 1, at: "2026-11-16T01:00:00Z" },
    parent: { session_id: "me", pid: 1, cwd: "/git/plan" },
    ...fields,
  });

const entry = (name: string, kind: "file" | "dir") => ({
  name,
  kind,
  size: 1,
  mtimeMs: T0,
  isLink: false,
});

/**
 * The engine beneath the plugin: a state folder holding `files`, the panes it
 * has open, and what it was asked to copy and open.
 */
const engine = (on: On, files: Record<string, string>) => {
  const state = {
    panes: [] as string[],
    opened: 0,
    copied: [] as string[],
  };
  const clock = mock.clock(on, { now: T0 + 5 * MIN });
  mock.env(on, { HOME: "/home/neil", XDG_STATE_HOME: "/state" });
  on("session.id", () => ({ value: "me" }));
  on("session.start", (_, e) => ({ cwd: e.cwd }));
  on("command.register", (_, e) => ({ value: { command: e.name } }));
  on("fs.list", (_, e) => {
    const inside = Object.keys(files)
      .filter((path) => path.startsWith(`${e.path}/`))
      .map((path) => path.slice(e.path.length + 1).split("/"));

    if (inside.length === 0) {
      throw new Error(`ENOENT: ${e.path}`);
    }

    const names = [...new Set(inside.map((parts) => parts[0] ?? ""))];

    return {
      value: names.map((name) =>
        entry(
          name,
          inside.some((p) => p[0] === name && p.length > 1) ? "dir" : "file",
        ),
      ),
    };
  });
  on("fs.read", (_, e) => ({ value: files[e.path] ?? "" }));
  on("ui.panes", () => ({
    value: state.panes.map((id) => ({
      id,
      title: id,
      isShown: true,
      isFocused: false,
      isPlaced: true,
    })),
  }));
  on("ui.open", (_, e) => {
    state.opened += 1;
    state.panes = [...new Set([...state.panes, e.id])];

    return { value: { isPlaced: true } };
  });
  on("ui.close", (_, e) => {
    state.panes = state.panes.filter((id) => id !== e.id);

    return { value: undefined };
  });
  on("ui.copy", (_, e) => {
    state.copied.push(e.text);

    return { value: { isCopied: true } };
  });
  on("ui.toast", () => ({ value: undefined }));

  return { state, clock };
};

const start = { cwd: "/git/plan", surface: "terminal", isInteractive: true };

for (const surface of ["terminal", "desktop"] as const) {
  test(`the pane groups the runs by job and a row copies its resume command, on ${surface}`, async ($, on) => {
    const { state } = engine(on, {
      [`${ROOT}/wave-1/alpha.status.json`]: status({}),
      [`${ROOT}/wave-1/beta.status.json`]: status({
        label: "beta",
        state: "failed",
        session_id: null,
        log: `${ROOT}/wave-1/beta.stream.jsonl`,
        ended: "2026-11-16T01:03:00+00:00",
      }),
      [`${ROOT}/wave-1/beta.stream.jsonl`]: "",
    });
    await $.session.start({ ...start, surface } as never);
    const ui = await $.ui.mount({ ...PANE, surface });

    expect((await ui.find({ type: "Text", text: /wave-1/ }))?.text).toBe(
      "wave-1 · 🏃 1 · ❌ 1",
    );

    await ui.press({ key: "wave-1/alpha@" + T0 });
    expect(state.copied).toEqual([
      "cd '/git/alpha.worktrees/headless-wave-1' && claude --resume sess-1",
    ]);

    await ui.press({ key: "wave-1/beta@" + T0 });
    expect(state.copied[1]).toBe(`${ROOT}/wave-1/beta.stream.jsonl`);
    await ui.unmount();
  });
}

test("the pane opens by itself once for a running job of this session's", async ($, on) => {
  const { state, clock } = engine(on, {
    [`${ROOT}/wave-1/alpha.status.json`]: status({}),
  });
  await $.session.start(start as never);
  await clock.settle();
  expect(state.opened).toBe(1);

  // Closed by the person, it stays closed while the same run goes on.
  state.panes = [];
  await clock.advance(10_000);
  expect(state.opened).toBe(1);
});

test("a run another session started leaves the pane closed", async ($, on) => {
  const { state, clock } = engine(on, {
    [`${ROOT}/wave-1/alpha.status.json`]: status({
      parent: { session_id: "someone-else" },
    }),
  });
  await $.session.start(start as never);
  await clock.advance(10_000);
  expect(state.opened).toBe(0);
});

test("/runs opens and closes the pane", async ($, on) => {
  const { state } = engine(on, {
    [`${ROOT}/wave-1/alpha.status.json`]: status({ state: "ok" }),
  });
  await $.session.start(start as never);
  expect(state.panes).toEqual([]);

  await $.command.run(RUNS);
  expect(state.panes).toEqual(["headless-runs"]);

  await $.command.run(RUNS);
  expect(state.panes).toEqual([]);
});

test("the pane says when there are no runs", async ($, on) => {
  engine(on, {});
  await $.session.start(start as never);
  const ui = await $.ui.mount({ ...PANE, surface: "terminal" });

  expect((await ui.find({ type: "Text" }))?.text).toBe(
    `No headless runs yet: ${ROOT} is not there.`,
  );
  await ui.unmount();
});

test("the ETA counts down between reads", async ($, on) => {
  const { clock } = engine(on, {
    [`${ROOT}/wave-1/alpha.status.json`]: status({}),
  });
  await $.session.start(start as never);
  const ui = await $.ui.mount({ ...PANE, surface: "terminal" });
  const row = async () =>
    (await ui.find({ type: "Button", key: "wave-1/alpha@" + T0 }))?.text;

  expect(await row()).toContain("ETA 5m00s");
  await clock.advance(3_000);
  expect(await row()).toContain("ETA 4m57s");
  await ui.unmount();
});
