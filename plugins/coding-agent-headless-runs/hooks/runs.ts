// The mod's pure core: reading a status file's JSON, choosing and grouping the
// runs to show, and the words of each row. No `$`, no I/O: register.tsx reads
// the files and the clock, calls these, and draws what they return.

import type { Eta, RunState, RunStatus, Runs } from "../types";

/** How long a finished run stays in the pane. */
export const FINISHED_WINDOW_MS = 6 * 60 * 60 * 1000;
/** A live run with no write for this long has lost its runner. */
export const STALE_MS = 2 * 60 * 1000;

const STATES: readonly RunState[] = [
  "waiting",
  "running",
  "ok",
  "failed",
  "limit",
  "skipped",
];

export const EMOJI: Record<RunState, string> = {
  running: "🏃",
  waiting: "⏳",
  ok: "✅",
  failed: "❌",
  limit: "❌",
  skipped: "💤",
};

export const emptyRuns: Runs = {
  runs: [],
  now: 0,
  problem: "",
  openedFor: [],
};

const text = (value: unknown): string | null =>
  typeof value === "string" && value !== "" ? value : null;

const count = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;

const time = (value: unknown): number | null => {
  const parsed = typeof value === "string" ? Date.parse(value) : NaN;

  return Number.isNaN(parsed) ? null : parsed;
};

const etaOf = (value: unknown): Eta | null => {
  const v = value as { figure?: unknown; seconds?: unknown; at?: unknown };

  return typeof v === "object" &&
    v !== null &&
    typeof v.figure === "string" &&
    count(v.seconds) !== null
    ? { figure: v.figure, seconds: count(v.seconds) ?? 0, at: text(v.at) }
    : null;
};

/** One status file's record, or undefined when it isn't one. */
export const parseStatus = (value: unknown): RunStatus | undefined => {
  if (typeof value !== "object" || value === null) {
    return undefined;
  }

  const v = value as Record<string, unknown>;
  const state = STATES.find((s) => s === v.state);
  const job = text(v.job);
  const label = text(v.label);
  const started = time(v.started);

  if (
    state === undefined ||
    job === null ||
    label === null ||
    started === null
  ) {
    return undefined;
  }

  const parent = v.parent as { session_id?: unknown } | null | undefined;

  return {
    job,
    label,
    workdir: text(v.workdir) ?? "",
    branch: text(v.branch),
    log: text(v.log),
    sessionId: text(v.session_id),
    state,
    started,
    updated: time(v.updated) ?? started,
    ended: time(v.ended),
    turns: count(v.turns),
    toolCalls: count(v.tool_calls) ?? 0,
    lastTool: text(v.last_tool),
    eta: etaOf(v.eta),
    parentSessionId:
      typeof parent === "object" && parent !== null
        ? text(parent.session_id)
        : null,
  };
};

/** A run's identity across reads: a rerun under the same job and label is a new run. */
export const runKey = (run: RunStatus): string =>
  `${run.job}/${run.label}@${run.started}`;

export const isLive = (run: RunStatus): boolean =>
  run.state === "running" || run.state === "waiting";

export const isStale = (run: RunStatus, now: number): boolean =>
  isLive(run) && now - run.updated > STALE_MS;

/** The runs the pane shows: every live one, and those that finished within the window. */
export const shown = (
  runs: readonly RunStatus[],
  now: number,
  windowMs: number = FINISHED_WINDOW_MS,
): RunStatus[] =>
  runs.filter(
    (run) => isLive(run) || now - (run.ended ?? run.updated) <= windowMs,
  );

/** Live runs first, newest started first; then finished ones, latest ended first. */
const byRow = (a: RunStatus, b: RunStatus): number =>
  isLive(a) !== isLive(b)
    ? isLive(a)
      ? -1
      : 1
    : isLive(a)
      ? b.started - a.started
      : (b.ended ?? b.updated) - (a.ended ?? a.updated);

export type Group = {
  job: string;
  runs: RunStatus[];
};

/** The runs grouped under their job, groups with a live run first, then the most recently written. */
export const groups = (runs: readonly RunStatus[]): Group[] => {
  const jobs = [...new Set(runs.map((run) => run.job))];
  const grouped = jobs.map((job) => ({
    job,
    runs: runs.filter((run) => run.job === job).sort(byRow),
  }));
  const latest = (g: Group) => Math.max(...g.runs.map((run) => run.updated));
  const hasLive = (g: Group) => g.runs.some(isLive);

  return grouped.sort((a, b) =>
    hasLive(a) !== hasLive(b) ? (hasLive(a) ? -1 : 1) : latest(b) - latest(a),
  );
};

/** `12s`, `4m05s` or `1h02m`. */
export const duration = (ms: number): string => {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const pad = (n: number) => String(n).padStart(2, "0");

  return h > 0 ? `${h}h${pad(m)}m` : m > 0 ? `${m}m${pad(s)}s` : `${s}s`;
};

/** How long the run has gone, or went. */
export const elapsedOf = (run: RunStatus, now: number): number =>
  (run.ended ?? (isStale(run, now) ? run.updated : now)) - run.started;

/** A live run's ETA counting down from its last report, or how far past it the run is. */
export const etaText = (run: RunStatus, now: number): string | undefined => {
  const at = run.eta?.at ? Date.parse(run.eta.at) : NaN;

  if (run.eta === null || !isLive(run) || Number.isNaN(at)) {
    return undefined;
  }

  const left = at + run.eta.seconds * 1000 - now;

  return left >= 0
    ? `ETA ${duration(left)}`
    : `${duration(-left)} past ETA ${run.eta.figure}`;
};

const plural = (n: number, one: string): string =>
  `${n} ${one}${n === 1 ? "" : "s"}`;

/** One run's row: `🏃 alpha · 12m03s · ETA 4m10s · 23 turns · 87 tools · last Bash`. */
export const rowText = (run: RunStatus, now: number): string =>
  [
    `${EMOJI[run.state]} ${run.label}`,
    duration(elapsedOf(run, now)),
    etaText(run, now),
    isStale(run, now)
      ? `no update for ${duration(now - run.updated)}`
      : undefined,
    run.turns === null ? undefined : plural(run.turns, "turn"),
    plural(run.toolCalls, "tool"),
    run.lastTool === null ? undefined : `last ${run.lastTool}`,
  ]
    .filter((part) => part !== undefined)
    .join(" · ");

/** A group's header: `wave-3 · 🏃 2 · ✅ 3 · ❌ 1`, the counts by emoji in drawing order. */
export const groupHeader = (group: Group): string => {
  const counts = ["🏃", "⏳", "✅", "❌", "💤"]
    .map((emoji) => ({
      emoji,
      n: group.runs.filter((run) => EMOJI[run.state] === emoji).length,
    }))
    .filter(({ n }) => n > 0)
    .map(({ emoji, n }) => `${emoji} ${n}`);

  return [group.job, ...counts].join(" · ");
};

const quoted = (path: string): string => `'${path.replaceAll("'", `'\\''`)}'`;

/** What a row's button copies: the command that resumes its session, else its stream log's path. */
export const copyText = (run: RunStatus): string | undefined =>
  run.sessionId !== null
    ? `cd ${quoted(run.workdir)} && claude --resume ${run.sessionId}`
    : (run.log ?? undefined);

/** Live runs a job of this session started that the pane hasn't opened itself for yet. */
export const newOwnLive = (
  runs: readonly RunStatus[],
  sessionId: string,
  openedFor: readonly string[],
): string[] =>
  runs
    .filter((run) => isLive(run) && run.parentSessionId === sessionId)
    .map(runKey)
    .filter((key) => !openedFor.includes(key));
