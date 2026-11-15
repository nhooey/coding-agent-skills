import { expect, test } from "claude-code/testing";
import type { On } from "claude-code";

const PLUGIN = "coding-agent-kanban-answers";
const TOOL = "mcp__coding-agent-kanban-answers__kanban_options";

const ITEMS = [
  {
    turn: "9efb08a1",
    list: "Decide",
    number: 1,
    summary: "Which cache to keep",
    kind: "radio",
    ref: "9efb08a1.Decide.1",
    options: [
      { letter: "A", name: "Disk" },
      { letter: "B", name: "Memory" },
    ],
  },
  {
    turn: "9efb08a1",
    list: "Decide",
    number: 2,
    summary: "Cleanups to start",
    kind: "checkbox",
    ref: "9efb08a1.Decide.2",
    options: [
      { letter: "A", name: "Matchers" },
      { letter: "B", name: "Dead code" },
      { letter: "C", name: "Stale render" },
    ],
  },
  {
    turn: "9efb08a1",
    list: "Decide",
    number: 3,
    summary: "Ship tonight?",
    kind: "binary",
    ref: "9efb08a1.Decide.3",
    options: [
      { letter: "Y", name: "Ship" },
      { letter: "N", name: "Hold" },
    ],
  },
] as const;

const BAND = {
  plugin: PLUGIN,
  component: "AbovePrompt",
  props: {
    hasSurvey: false,
    isCollapsed: false,
    isWorking: false,
    maxRows: 20,
    bodyColumns: 100,
    scroll: { offset: 0, bodyRows: 20 },
    view: {},
  },
} as const;

const ANSWERS = {
  command: "answers",
  args: "",
  origin: { kind: "composer" },
  presentation: { isFullscreen: true, columns: 100 },
} as const;

/**
 * The engine beneath the plugin: a prompt box held in `box`, the script's
 * output from `open`, and the prompts the plugin submits in `sent`.
 */
const engine = (on: On, open: () => readonly unknown[]) => {
  const state = { box: "", sent: [] as string[] };
  on("session.id", () => ({ value: "session-1" }));
  on("session.cwd", () => ({ value: "/work" }));
  on("env.get", () => ({ value: "/home/neil" }));
  on("fs.exists", () => ({ value: true }));
  on("process.run", () => ({
    value: {
      exitCode: 0,
      stdout: JSON.stringify({ items: open() }),
      stderr: "",
      isStdoutTruncated: false,
      isStderrTruncated: false,
    },
  }));
  on("prompt.read", () => ({
    value: { text: state.box, cursor: state.box.length },
  }));
  on("prompt.fill", (_, e) => {
    state.box = e.text;

    return { isFilled: true };
  });
  on("prompt.submit", (_, e) => {
    state.sent.push(e.text);

    return { text: e.text };
  });
  on("turn.complete", (_, e) => ({ text: e.answer }));
  on("command.register", (_, e) => ({ value: { command: e.name } }));
  on("tool.register", (_, e) => ({
    value: { tool: `mcp__${PLUGIN}__${e.name}` },
  }));

  return state;
};

/** A reply of the main loop finishing, which refreshes the open items. */
const replyDone = (turnId: string) =>
  ({
    turnId,
    reason: "answer",
    answer: "reply",
    durationMs: 1000,
    isAborted: false,
  }) as const;

const headerText = async (ui: {
  find: (q: {
    type: string;
    text: RegExp;
  }) => Promise<{ text: string } | undefined>;
}) => (await ui.find({ type: "Text", text: /🧠/ }))?.text;

for (const surface of ["terminal", "desktop"] as const) {
  test(`the band builds the draft and walks the items, on ${surface}`, async ($, on) => {
    const state = engine(on, () => ITEMS);
    await $.command.run(ANSWERS);
    const ui = await $.ui.mount({ ...BAND, surface });

    expect(await headerText(ui)).toBe("🧠 1/3 · Which cache to keep");

    // A radio option writes its reference and moves on.
    await ui.press({ key: "option-B" });
    expect(state.box).toBe("9efb08a1.Decide.1.B");
    expect(await headerText(ui)).toBe("🧠 2/3 · Cleanups to start");

    // A checkbox item takes several letters and stays put.
    await ui.press({ key: "option-C" });
    await ui.press({ key: "option-A" });
    expect(state.box).toBe("9efb08a1.Decide.1.B 9efb08a1.Decide.2.A,C");
    expect(await headerText(ui)).toBe("🧠 2/3 · Cleanups to start");

    // Back to the first item: another option replaces its reference.
    await ui.press({ key: "prev" });
    await ui.press({ key: "option-A" });
    expect(state.box).toBe("9efb08a1.Decide.1.A 9efb08a1.Decide.2.A,C");
    expect(await headerText(ui)).toBe("🧠 3/3 · Ship tonight?");

    // Next wraps; skip goes to the next unanswered item.
    await ui.press({ key: "next" });
    expect(await headerText(ui)).toBe("🧠 1/3 · Which cache to keep");
    await ui.press({ key: "skip" });
    expect(await headerText(ui)).toBe("🧠 3/3 · Ship tonight?");

    // No click sent anything.
    expect(state.sent).toEqual([]);
    await ui.unmount();
  });
}

test("dismiss hides the band, and /answers brings it back at the first unanswered item", async ($, on) => {
  const state = engine(on, () => ITEMS);
  await $.command.run(ANSWERS);
  const ui = await $.ui.mount({ ...BAND, surface: "terminal" });
  await ui.press({ key: "option-A" });
  await ui.press({ key: "dismiss" });

  expect(await headerText(ui)).toBeUndefined();

  await $.command.run(ANSWERS);
  expect(await headerText(ui)).toBe("🧠 2/3 · Cleanups to start");
  expect(state.box).toBe("9efb08a1.Decide.1.A");
  await ui.unmount();
});

for (const surface of ["terminal", "desktop"] as const) {
  test(`dismiss leaves a 🧠 that reopens the band at the first unanswered item, on ${surface}`, async ($, on) => {
    const state = engine(on, () => ITEMS);
    await $.command.run(ANSWERS);
    const ui = await $.ui.mount({ ...BAND, surface });
    await ui.press({ key: "option-A" });
    await ui.press({ key: "dismiss" });

    expect(await headerText(ui)).toBeUndefined();
    expect((await ui.find({ type: "Button", key: "reopen" }))?.text).toBe("🧠");

    await ui.press({ key: "reopen" });
    expect(await headerText(ui)).toBe("🧠 2/3 · Cleanups to start");
    expect(await ui.find({ type: "Button", key: "reopen" })).toBeUndefined();
    expect(state.box).toBe("9efb08a1.Decide.1.A");
    expect(state.sent).toEqual([]);
    await ui.unmount();
  });
}

test("with no open items a dismissed band leaves no 🧠", async ($, on) => {
  const open: unknown[] = [...ITEMS];
  engine(on, () => open);
  await $.command.run(ANSWERS);
  const ui = await $.ui.mount({ ...BAND, surface: "terminal" });
  await ui.press({ key: "dismiss" });
  open.splice(0, open.length);
  await $.turn.complete(replyDone("t1"));

  expect(await ui.find({ type: "Button", key: "reopen" })).toBeUndefined();
  await ui.unmount();
});

test("a dismissed band stays hidden until a refresh raises a new item", async ($, on) => {
  const open: unknown[] = [...ITEMS];
  engine(on, () => open);
  await $.command.run(ANSWERS);
  const ui = await $.ui.mount({ ...BAND, surface: "terminal" });
  await ui.press({ key: "dismiss" });

  await $.turn.complete(replyDone("t1"));
  expect(await headerText(ui)).toBeUndefined();

  open.push({ ...ITEMS[0], turn: "b2c3d4e5", ref: "b2c3d4e5.Decide.1" });
  await $.turn.complete(replyDone("t2"));
  expect(await headerText(ui)).toBe("🧠 1/4 · Which cache to keep");
  await ui.unmount();
});

test("a progress circle jumps to its item", async ($, on) => {
  engine(on, () => ITEMS);
  await $.command.run(ANSWERS);
  const ui = await $.ui.mount({ ...BAND, surface: "terminal" });
  await ui.press({ key: "mark-2" });

  expect(await headerText(ui)).toBe("🧠 3/3 · Ship tonight?");
  await ui.press({ key: "mark-0" });
  expect(await headerText(ui)).toBe("🧠 1/3 · Which cache to keep");
  await ui.unmount();
});

test("Reassess submits the reassess command", async ($, on) => {
  const state = engine(on, () => ITEMS);
  await $.command.run(ANSWERS);
  const ui = await $.ui.mount({ ...BAND, surface: "terminal" });
  await ui.press({ key: "reassess" });

  expect(state.sent).toEqual(["reassess"]);
  expect(state.box).toBe("");
  await ui.unmount();
});

test("the tool row draws buttons that build the draft, and dims a settled item", async ($, on) => {
  const open: unknown[] = [...ITEMS];
  const state = engine(on, () => open);
  on("ui.render", ($, e) => {
    const { Text } = $.ui.resolve(e);

    return <Text>engine row</Text>;
  });
  await $.tool.call({ tool: TOOL, items: ITEMS } as never);
  await $.command.run(ANSWERS);
  const row = await $.ui.mount({
    plugin: PLUGIN,
    surface: "terminal",
    component: "ToolUse",
    requestId: "toolu_1",
    props: {
      tool_use_id: "toolu_1",
      tool: TOOL,
      input: { items: ITEMS },
      isRunning: false,
      isErrored: false,
      isInterrupted: false,
    },
  });

  expect(await row.find({ type: "Text", text: /engine row/ })).toBeDefined();
  await row.press({ key: "9efb08a1.Decide.3.N" });
  expect(state.box).toBe("9efb08a1.Decide.3.N");

  // Item 1 is answered elsewhere: the next refresh no longer lists it.
  open.splice(0, 1);
  await $.turn.complete(replyDone("t1"));
  expect((await row.find({ type: "Text", text: /Decide\.1/ }))?.text).toContain(
    "(settled)",
  );
  await row.press({ key: "9efb08a1.Decide.1.A" });
  expect(state.box).toBe("9efb08a1.Decide.3.N");
  await row.unmount();
});
