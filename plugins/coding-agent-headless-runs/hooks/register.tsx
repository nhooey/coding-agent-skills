// A pane of the headless runs `run_headless.py` writes status files for: one
// row per run, grouped by job, read again every few seconds. It opens by
// itself when a job this session started is running, and /runs opens or
// closes it. A row is a button that copies the command resuming its session,
// or its stream log's path.

import { atom, read, update } from "claude-code";
import type { EngineInterface, Register, UiPressArgument } from "claude-code";

import type { RunStatus } from "../types";
import {
  FINISHED_WINDOW_MS,
  copyText,
  emptyRuns,
  groupHeader,
  groups,
  isLive,
  newOwnLive,
  parseStatus,
  rowText,
  runKey,
  shown,
} from "./runs";

const PANE = "headless-runs";
const TITLE = "Headless runs";
const COMMAND = "runs";
const POLL_MS = 3000;
const STATUS_SUFFIX = ".status.json";

// Change the tag when Runs' fields change: it declines what an earlier
// version stored, which outlives a reload.
const runs = atom(
  { plugin: "coding-agent-headless-runs", key: "runs" } as const,
  emptyRuns,
  { shape: "runs-1" },
);

/** Where `run_headless.py` keeps its jobs' log folders by default. */
const stateRoot = async ($: EngineInterface): Promise<string> => {
  const state =
    (await $.env.get("XDG_STATE_HOME")) ||
    `${(await $.env.get("HOME")) ?? ""}/.local/state`;

  return `${state}/coding-agent-headless`;
};

const readStatus = async (
  $: EngineInterface,
  path: string,
): Promise<RunStatus | undefined> => {
  try {
    return parseStatus(JSON.parse(await $.fs.read(path)));
  } catch {
    return undefined;
  }
};

/** Every status file of the last few hours under the state root's job folders. */
const readRuns = async (
  $: EngineInterface,
  now: number,
): Promise<{ runs: RunStatus[]; problem: string }> => {
  const root = await stateRoot($);
  const jobs = await $.fs.list(root).catch(() => undefined);

  if (jobs === undefined) {
    return { runs: [], problem: `No headless runs yet: ${root} is not there.` };
  }

  const files = await Promise.all(
    jobs
      .filter((job) => job.kind === "dir")
      .map(async (job) => {
        const entries = await $.fs.list(`${root}/${job.name}`).catch(() => []);

        return entries
          .filter(
            (entry) =>
              entry.kind === "file" &&
              entry.name.endsWith(STATUS_SUFFIX) &&
              now - entry.mtimeMs <= FINISHED_WINDOW_MS,
          )
          .map((entry) => `${root}/${job.name}/${entry.name}`);
      }),
  );
  const found = await Promise.all(
    files.flat().map((path) => readStatus($, path)),
  );

  return {
    runs: found.filter((run) => run !== undefined),
    problem: "",
  };
};

const open = ($: EngineInterface) => $.ui.open({ id: PANE, title: TITLE });

const isOpen = async ($: EngineInterface): Promise<boolean> =>
  (await $.ui.panes()).some((pane) => pane.id === PANE);

let isPolling = false;

/** Reads the status files, and opens the pane for a run of this session's that it hasn't opened for. */
const poll = async ($: EngineInterface): Promise<void> => {
  if (isPolling) {
    return;
  }

  isPolling = true;

  try {
    const now = await $.clock.now();
    const found = await readRuns($, now);
    const session = await $.session.id();
    const before = await read($, runs);
    const fresh = newOwnLive(found.runs, session, before.openedFor);
    await update($, runs, (current) => ({
      ...current,
      ...found,
      now,
      openedFor: [...current.openedFor, ...fresh],
    }));

    if (fresh.length > 0 && !(await isOpen($))) {
      await open($);
    }
  } finally {
    isPolling = false;
  }
};

export const register: Register = (on) => {
  on("session.start", async ($, e, next) => {
    const started = await next(e);
    await $.command.register({
      name: COMMAND,
      description: "Open or close the pane of headless runs",
    });
    $.clock.every(POLL_MS, () => void poll($).catch(() => undefined));
    void poll($).catch(() => undefined);

    return started;
  });

  on("command.run", { command: COMMAND }, async ($) => {
    if (await isOpen($)) {
      await $.ui.close({ id: PANE });

      return { text: "Headless runs pane closed." };
    }

    await poll($);
    const opened = await open($);
    const r = await read($, runs);
    const live = r.runs.filter(isLive).length;

    return {
      text: opened.isPlaced
        ? `Headless runs pane opened: ${live} running.`
        : `Headless runs pane waits to be placed: ${opened.reason}.`,
    };
  }).catch((_, e, next) => ({
    text: `The headless runs pane could not be opened or closed: ${String(next.error)}`,
  }));

  on("ui.render", { component: "Pane", requestId: PANE }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e);
    const r = await read($, runs);
    const list = groups(shown(r.runs, r.now));

    if (list.length === 0) {
      return (
        <Box flexDirection="column">
          <Text dimColor>
            {r.problem || "No headless runs in the last 6 hours."}
          </Text>
        </Box>
      );
    }

    const copy = (text: string) => (press: UiPressArgument) =>
      void $.ui
        .copy({ text, surface: press.surface })
        .then((done) =>
          $.ui.toast(
            done.isCopied ? `Copied: ${text}` : `Not copied: ${done.reason}`,
          ),
        );

    return (
      <Box flexDirection="column">
        {list.map((group) => (
          <Box key={group.job} flexDirection="column">
            <Text bold wrap="truncate-end">
              {groupHeader(group)}
            </Text>
            {group.runs.map((run) => {
              const line = `  ${rowText(run, r.now)}`;
              const text = copyText(run);

              return text === undefined ? (
                <Text dimColor={!isLive(run)} wrap="truncate-end">
                  {line}
                </Text>
              ) : (
                <Button
                  key={runKey(run)}
                  plain
                  dimColor={!isLive(run)}
                  onPress={copy(text)}
                >
                  {line}
                </Button>
              );
            })}
          </Box>
        ))}
      </Box>
    );
  });
};
