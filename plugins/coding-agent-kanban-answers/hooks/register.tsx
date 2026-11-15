// Clickable answers to the kanban turn responses' Decide items: a band above
// the prompt that walks the open items one at a time, the same buttons on the
// row of the `kanban_options` tool the agent calls before its reply, and two
// ways to bring a dismissed band back: the 🧠 it leaves in its place, and the
// /answers command. A click writes the
// item's reference into the prompt draft and never sends it; Reassess alone
// sends a prompt, the skill's `reassess` command.
//
// An item is drawn as the skill writes it: its summary, its note, then each
// option as `glyph letter. name: consequence` with its ➕ and ➖ lines indented
// under it, inside a rounded border. Backgrounds tell the parts apart: the
// option the draft picks, the pros and the cons each have their own.

import { atom, read, update } from "claude-code";
import type { EngineInterface, Register } from "claude-code";

import type { Band, DecideItem } from "../types";
import {
  afterAnswer,
  choose,
  codeSpans,
  dismissed,
  glyphOf,
  drawnByTool,
  emptyBand,
  header,
  itemsOf,
  lettersFor,
  nextPosition,
  positionIn,
  prevPosition,
  progressMarks,
  refOf,
  refreshed,
  reopened,
  skipped,
} from "./answers";

const TOOL = "kanban_options";
const TOOL_CALLED = "mcp__coding-agent-kanban-answers__kanban_options";
const REASSESS = "reassess";
const SCRIPT =
  "skills/coding-agent-kanban-turn-responses/scripts/outstanding.py";
// Hotkeys for the band's controls, pressed while the band holds the keys
// (ctrl+x tab or a click).
const KEYS = { prev: "h", skip: "j", next: "l", dismiss: "q" } as const;

// Theme colours, so each part keeps its contrast in light and dark themes.
const COLOR = {
  border: "promptBorder",
  title: "claude",
  code: "permission",
  chosen: "diffAddedWord",
  pro: "diffAddedDimmed",
  con: "diffRemovedDimmed",
} as const;
// Columns an option sits in from its summary, and its ➕ and ➖ lines from it.
const INDENT = 3;

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

/** /answers and the 🧠 left after ✕: re-reads the open items and shows the band at the first unanswered one. */
const reopen = async ($: EngineInterface): Promise<void> => {
  await refresh($);
  const text = await read($, draft);
  await update($, band, (b) => reopened(b, text));
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
    await reopen($);
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

    if (e.props.hasSurvey || item === undefined) {
      return next(e);
    }

    const { Box, Button, Text } = $.ui.resolve(e);

    if (b.isDismissed) {
      return (
        <Box>
          <Button key="reopen" label="🧠" plain onPress={() => reopen($)} />
        </Box>
      );
    }
    const move = (position: (b: Band) => number) => () =>
      update($, band, (current) => ({
        ...current,
        position: position(current),
      }));
    // A control's emoji, then its word underlined, so it reads as a link.
    const control = (
      key: string,
      emoji: string,
      word: string,
      onPress: () => unknown,
      hotkey?: string,
    ) => (
      <Button
        key={key}
        label={word}
        plain
        dimColor
        {...(hotkey ? { hotkey } : {})}
        onPress={onPress}
      >
        {emoji} <Text underline>{word}</Text>
      </Button>
    );

    return (
      <Box
        flexDirection="column"
        borderStyle="round"
        borderColor={COLOR.border}
        paddingX={1}
      >
        <Box marginBottom={1} flexWrap="wrap" columnGap={2}>
          {control("prev", "⏪", "Prev", move(prevPosition), KEYS.prev)}
          {control(
            "skip",
            "⏭️",
            "Skip",
            move((current) => skipped(current, text)),
            KEYS.skip,
          )}
          {control("next", "⏩", "Next", move(nextPosition), KEYS.next)}
          {control("reassess", "🔄", "Reassess", () =>
            $.prompt.submit({ text: REASSESS }),
          )}
          <Button
            key="dismiss"
            label="❎"
            plain
            dimColor
            role="dismiss"
            hotkey={KEYS.dismiss}
            onPress={() => update($, band, dismissed)}
          />
          <Box columnGap={1}>
            {progressMarks(b, text).map(({ mark, isShown }, n) => (
              <Button
                key={`mark-${n}`}
                plain
                dimColor={!isShown}
                onPress={move(() => n)}
              >
                <Text color={isShown ? COLOR.title : undefined} bold={isShown}>
                  {isShown ? (mark === "●" ? "◉" : "◎") : mark}
                </Text>
              </Button>
            ))}
          </Box>
        </Box>
        {itemView({ Box, Button, Text }, item, {
          title: header(b),
          chosen: lettersFor(text, item),
          keyOf: (letter) => `option-${letter}`,
          onPick: (letter) => answer($, item, letter),
        })}
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

          return (
            <Box
              key={refOf(item)}
              flexDirection="column"
              borderStyle="round"
              borderColor={COLOR.border}
              borderDimColor={isSettled}
              paddingX={1}
            >
              {itemView({ Box, Button, Text }, item, {
                title: `🧠 Decide.${item.number} · ${item.summary}${isSettled ? " (settled)" : ""}`,
                chosen: isSettled ? [] : lettersFor(text, item),
                isSettled,
                keyOf: (letter) => `${refOf(item)}.${letter}`,
                onPick: (letter) =>
                  isSettled ? undefined : answer($, item, letter),
              })}
            </Box>
          );
        })}
      </Box>
    );
  });
};

/** The elements an item is drawn with, from the surface's table. */
type Elements = Pick<
  ReturnType<EngineInterface["ui"]["resolve"]>,
  "Box" | "Button" | "Text"
>;

/**
 * One Decide item as the skill writes it: the title, the note, and each
 * option a plain button reading `glyph letter. name: consequence`, its ➕ and
 * ➖ lines indented under it, always in full.
 */
const itemView = (
  elements: Elements,
  item: DecideItem,
  view: {
    title: string;
    chosen: string[];
    isSettled?: boolean;
    keyOf: (letter: string) => string;
    onPick: (letter: string) => unknown;
  },
) => {
  const { Box, Button, Text } = elements;
  const dim = view.isSettled === true;
  const inline = (
    line: string,
    key: string,
    props: Record<string, unknown> = {},
  ) =>
    codeSpans(line).map((part, n) => (
      <Text
        key={`${key}-${n}`}
        {...props}
        {...(part.isCode ? { color: COLOR.code } : {})}
      >
        {part.text}
      </Text>
    ));
  const lines = (
    prefix: string,
    texts: string[] | undefined,
    background: string | undefined,
    key: string,
  ) =>
    (texts ?? []).map((line, n) => (
      <Box key={`${key}-${n}`} marginLeft={INDENT}>
        <Text
          dimColor={dim}
          {...(background ? { backgroundColor: background } : {})}
          wrap="wrap"
        >
          {prefix ? `${prefix} ` : ""}
          {inline(line, `${key}-${n}`)}
        </Text>
      </Box>
    ));

  return (
    <Box flexDirection="column">
      <Text
        bold={!dim}
        dimColor={dim}
        color={dim ? undefined : COLOR.title}
        wrap="wrap"
      >
        {inline(view.title, "title")}
      </Text>
      {lines("", item.note, undefined, "note")}
      {item.options.map((option) => {
        const isChosen = view.chosen.includes(option.letter);
        const pick = isChosen ? { backgroundColor: COLOR.chosen } : {};

        return (
          <Box
            key={`${view.keyOf(option.letter)}-box`}
            flexDirection="column"
            marginLeft={INDENT}
          >
            <Button
              key={view.keyOf(option.letter)}
              plain
              dimColor={dim}
              onPress={() => view.onPick(option.letter)}
            >
              <Text {...pick}>
                {glyphOf(item, option.letter)} {option.letter}.{" "}
              </Text>
              {inline(option.name, `${option.letter}-name`, {
                ...pick,
                bold: true,
              })}
              {option.consequence ? <Text {...pick}>: </Text> : null}
              {option.consequence
                ? inline(option.consequence, `${option.letter}-then`, pick)
                : null}
            </Button>
            {lines("➕", option.pros, COLOR.pro, `${option.letter}-pro`)}
            {lines("➖", option.cons, COLOR.con, `${option.letter}-con`)}
            {lines("", option.notes, undefined, `${option.letter}-note`)}
          </Box>
        );
      })}
    </Box>
  );
};
