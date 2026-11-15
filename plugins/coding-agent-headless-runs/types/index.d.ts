/** A run's state, as `run_headless.py` writes it in `<label>.status.json`. */
export type RunState =
  | "waiting"
  | "running"
  | "ok"
  | "failed"
  | "limit"
  | "skipped";

/** The last ETA line a run's session wrote. */
export type Eta = {
  /** As written, such as `4m`. */
  figure: string;
  seconds: number;
  /** When it was written, an ISO 8601 date-time; null when unknown. */
  at: string | null;
};

/** One run's status file, the fields the pane reads. */
export type RunStatus = {
  job: string;
  label: string;
  workdir: string;
  branch: string | null;
  log: string | null;
  sessionId: string | null;
  state: RunState;
  /** Epoch milliseconds. */
  started: number;
  updated: number;
  ended: number | null;
  turns: number | null;
  toolCalls: number;
  lastTool: string | null;
  eta: Eta | null;
  /** The session that started the runner, when Claude Code named it. */
  parentSessionId: string | null;
};

/** What the pane draws: the runs from the last read, and when it was. */
export type Runs = {
  runs: RunStatus[];
  /** Epoch milliseconds of the last read, the time the pane counts from. */
  now: number;
  /** Why the last read found nothing, for the pane to say; empty when it worked. */
  problem: string;
  /** The runs of this session's jobs the pane has opened itself for, `<job>/<label>@<started>`. */
  openedFor: string[];
};

declare module "claude-code" {
  interface PluginState {
    "coding-agent-headless-runs": {
      runs: Shaped<Runs>;
    };
  }
}
