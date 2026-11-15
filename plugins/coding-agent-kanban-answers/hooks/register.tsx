// Clickable answers to the kanban turn responses' Decide items: a band above
// the prompt that walks the open items one at a time, the same buttons on the
// row of the `kanban_options` tool the agent calls before its reply, and the
// /answers command that brings a dismissed band back. A click writes the
// item's reference into the prompt draft and never sends it; Recheck alone
// sends a prompt, the skill's `recheck` command.

import { atom, read, update } from "claude-code";
import type { EngineInterface, Register } from "claude-code";

import type { Band, DecideItem } from "../types";
import {
  afterAnswer,
  choose,
  dismissed,
  drawnByTool,
  emptyBand,
  header,
  itemsOf,
  lettersFor,
  nextPosition,
  positionIn,
  prevPosition,
  progress,
  refOf,
  refreshed,
  reopened,
  skipped,
} from "./answers";

const TOOL = "kanban_options";
const TOOL_CALLED = "mcp__coding-agent-kanban-answers__kanban_options";
const RECHECK = "recheck";
const SCRIPT =
  "skills/coding-agent-kanban-turn-responses/scripts/outstanding.py";
// Hotkeys for the band's controls, pressed while the band holds the keys
// (ctrl+x tab or a click). Letters an option is unlikely to use, since an
// option's own letter is its hotkey.
const KEYS = { prev: "h", skip: "j", next: "l", dismiss: "q" } as const;
const RESERVED: readonly string[] = Object.values(KEYS);

// Change the tag when Band's fields change: it declines what an earlier
// version stored, which outlives a reload.
const band = atom(
  { plugin: "coding-agent-kanban-answers", key: "band" } as const,
  emptyBand,
  {
    shape: "band-1",
  },
);
const draft = atom(
  { plugin: "coding-agent-kanban-answers", key: "draft" } as const,
  "",
);

const ITEM_SCHEMA = {
  type: "object",
  required: ["turn", "number", "summary", "kind", "options"],
  properties: {
    turn: {
      type: "string",
      description:
        "The turn id, the first 8 characters of this turn's promptId.",
    },
    list: { type: "string", enum: ["Decide"] },
    number: {
      type: "integer",
      description: "The item number in the Decide list.",
    },
    summary: { type: "string", description: "The item's bold summary." },
    kind: { type: "string", enum: ["radio", "checkbox", "binary"] },
    ref: {
      type: "string",
      description: "`<turn>.Decide.<number>`; filled in when left out.",
    },
    options: {
      type: "array",
      items: {
        type: "object",
        required: ["letter", "name"],
        properties: {
          letter: {
            type: "string",
            description: "The capital letter, A, B, C, or Y and N.",
          },
          name: { type: "string", description: "The option's bold name." },
        },
      },
    },
  },
} as const;

const TOOL_DESCRIPTION = [
  "Draws clickable buttons for this turn's Decide items in the transcript, just above the final response.",
  "Call it once, right before writing the final response, with every Decide item that response will hold, in the shape `outstanding.py decide --json` prints.",
  "A click writes the item's reference into the user's prompt draft; nothing is sent.",
].join(" ");

/** Where the skill's `outstanding.py` is: beside this plugin in its repository, else where the skill is installed. */
const scriptPath = async (
  $: EngineInterface,
  cwd: string,
): Promise<string | undefined> => {
  const home = await $.env.get("HOME");
  const repository = $.plugin.root.split("/").slice(0, -2).join("/");
  const candidates = [
    `${repository}/${SCRIPT}`,
    `${cwd}/.claude/skills/coding-agent-kanban-turn-responses/scripts/outstanding.py`,
    ...(home
      ? [
          `${home}/.claude/skills/coding-agent-kanban-turn-responses/scripts/outstanding.py`,
        ]
      : []),
  ];
  const found = await Promise.all(candidates.map((path) => $.fs.exists(path)));

  return candidates.find((_, n) => found[n]);
};

/** Runs `outstanding.py decide --json` over this session's transcript: the open items, or why there are none. */
const openItems = async (
  $: EngineInterface,
): Promise<{ items: DecideItem[]; problem: string }> => {
  const cwd = await $.session.cwd();
  const session = await $.session.id();
  const script = await scriptPath($, cwd);

  if (script === undefined) {
    return { items: [], problem: "outstanding.py not found" };
  }

  const ran = await $.process.run(
    ["python3", "-I", script, "--session", session, "decide", "--json"],
    { cwd, timeoutMs: 20_000 },
  );

  return ran.exitCode === 0
    ? { items: itemsOf(JSON.parse(ran.stdout || '{"items": []}')), problem: "" }
    : {
        items: [],
        problem:
          ran.stderr.trim().split("\n").at(-1) ?? "outstanding.py failed",
      };
};

const refresh = async ($: EngineInterface): Promise<void> => {
  const found = await openItems($).catch((error: unknown) => ({
    items: [] as DecideItem[],
    problem: String(error),
  }));
  const text = await read($, draft);
  await update($, band, (b) => ({
    ...refreshed(b, found.items, text),
    problem: found.problem,
  }));
};

/** Writes the draft with the item's answer for `letter`, and moves the band on when it shows that item. */
const answer = async (
  $: EngineInterface,
  item: DecideItem,
  letter: string,
): Promise<void> => {
  const box = await $.prompt.read();
  const text = choose(box.text, item, letter);
  await $.prompt.fill({ text, mode: "replace" });
  await update($, draft, () => text);
  await update($, band, (b) => {
    const shown = b.items[positionIn(b)];
    const isShown = shown !== undefined && refOf(shown) === refOf(item);
    const stays = item.kind === "checkbox";

    return isShown && !stays ? { ...b, position: afterAnswer(b, text) } : b;
  });
};

export const register: Register = (on) => {
  on("session.start", async ($, e, next) => {
    const started = await next(e);
    await $.command.register({
      name: "answers",
      description:
        "Show the kanban Decide answers band again, at the first unanswered item",
    });
    await $.tool.register({
      name: TOOL,
      description: TOOL_DESCRIPTION,
      isDeferred: false,
      inputSchema: {
        type: "object",
        required: ["items"],
        properties: { items: { type: "array", items: ITEM_SCHEMA } },
      },
    });
    void refresh($);

    return started;
  });

  on("command.run", { command: "answers" }, async ($) => {
    await refresh($);
    const text = await read($, draft);
    await update($, band, (b) => reopened(b, text));
    const shown = await read($, band);

    return {
      text:
        shown.items.length === 0
          ? `No open Decide items${shown.problem ? `: ${shown.problem}` : ""}.`
          : `Answers band shown: ${shown.items.length} open Decide items.`,
    };
  });

  on("tool.call", { tool: TOOL_CALLED }, async ($, e) => {
    const items = itemsOf(e);
    await update($, band, (b) => drawnByTool(b, items));

    return {
      result: `Drew buttons for ${items.length} Decide items above the final response: ${items
        .map(refOf)
        .join(", ")}.`,
    };
  }).catch(() => ({
    result: "The buttons could not be drawn; the reply reads as before.",
  }));

  on("turn.complete", async ($, e, next) => {
    const done = await next(e);

    if (e.agentId === undefined) {
      await refresh($);
    }

    return done;
  });

  on("prompt.change", async ($, e, next) => {
    const changed = await next(e);
    await update($, draft, () => e.text);

    return changed;
  });

  on("ui.render", { component: "AbovePrompt" }, async ($, e, next) => {
    const b = await read($, band);
    const text = await read($, draft);
    const item = b.items[positionIn(b)];

    if (e.props.hasSurvey || b.isDismissed || item === undefined) {
      return next(e);
    }

    const { Box, Button, Text } = $.ui.resolve(e);
    const chosen = lettersFor(text, item);
    const move = (position: (b: Band) => number) => () =>
      update($, band, (current) => ({
        ...current,
        position: position(current),
      }));

    return (
      <Box flexDirection="column">
        <Box>
          <Text bold wrap="truncate-end">
            {header(b)}
          </Text>
        </Box>
        <Box flexWrap="wrap">
          {item.options.map((option) => (
            <Button
              key={`option-${option.letter}`}
              label={`${option.letter}. ${option.name}`}
              variant={chosen.includes(option.letter) ? "primary" : "secondary"}
              {...(RESERVED.includes(option.letter.toLowerCase())
                ? {}
                : { hotkey: option.letter.toLowerCase() })}
              onPress={() => answer($, item, option.letter)}
            />
          ))}
        </Box>
        <Box flexWrap="wrap">
          <Button
            key="prev"
            label="◀ Prev"
            hotkey={KEYS.prev}
            onPress={move(prevPosition)}
          />
          <Button
            key="skip"
            label="Skip"
            hotkey={KEYS.skip}
            onPress={move((current) => skipped(current, text))}
          />
          <Button
            key="next"
            label="Next ▶"
            hotkey={KEYS.next}
            onPress={move(nextPosition)}
          />
          <Button
            key="recheck"
            label="Recheck"
            onPress={() => $.prompt.submit({ text: RECHECK })}
          />
          <Button
            key="dismiss"
            label="✕"
            role="dismiss"
            hotkey={KEYS.dismiss}
            onPress={() => update($, band, dismissed)}
          />
          <Text dimColor> {progress(b, text)}</Text>
        </Box>
      </Box>
    );
  });

  on("ui.render", { component: "ToolUse" }, async ($, e, next) => {
    if (e.props.tool !== TOOL_CALLED) {
      return next(e);
    }

    const row = await next(e);
    const items = itemsOf(e.props.input);
    const b = await read($, band);
    const text = await read($, draft);
    const { Box, Button, Text } = $.ui.resolve(e);

    return (
      <Box flexDirection="column">
        {row}
        {items.map((item) => {
          const isSettled = b.settledRefs.includes(refOf(item));
          const chosen = lettersFor(text, item);

          return (
            <Box key={refOf(item)} flexDirection="column">
              <Text bold={!isSettled} dimColor={isSettled} wrap="truncate-end">
                🧠 Decide.{item.number} · {item.summary}
                {isSettled ? " (settled)" : ""}
              </Text>
              <Box flexWrap="wrap">
                {item.options.map((option) => (
                  <Button
                    key={`${refOf(item)}.${option.letter}`}
                    label={`${option.letter}. ${option.name}`}
                    dimColor={isSettled}
                    variant={
                      !isSettled && chosen.includes(option.letter)
                        ? "primary"
                        : "secondary"
                    }
                    onPress={() =>
                      isSettled ? undefined : answer($, item, option.letter)
                    }
                  />
                ))}
              </Box>
            </Box>
          );
        })}
      </Box>
    );
  });
};
