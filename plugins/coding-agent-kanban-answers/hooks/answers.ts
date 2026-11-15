// The mod's pure core: how a click changes the prompt draft, and how the band
// moves among the open Decide items. No `$`, no I/O: register.tsx reads the
// draft and the state, calls these, and writes what they return.

import type { Band, DecideItem } from "../types";

/** One answer written in the draft, `<turn>.Decide.<n>.<letters>`, and where it sits. */
export type Answer = {
  start: number;
  end: number;
  turn: string;
  number: number;
  letters: string[];
};

// A turn id of 6 to 8 hex characters (a prefix of the 8 is as good), the item
// number, and one capital or several joined by commas. Not part of a longer word.
const ANSWER =
  /(?<![\w.])([0-9a-f]{6,8})\.Decide\.(\d+)\.([A-Z](?:,[A-Z])*)(?!\w)/g;

export const emptyBand: Band = {
  items: [],
  position: 0,
  isDismissed: false,
  dismissedRefs: [],
  knownRefs: [],
  settledRefs: [],
  problem: "",
};

/** The reference an answer names the item by, without its letters. */
export const refOf = (item: DecideItem): string =>
  item.ref || `${item.turn}.Decide.${item.number}`;

/** Every answer written in the draft, in order. */
export const answersIn = (draft: string): Answer[] =>
  [...draft.matchAll(ANSWER)].map((m) => ({
    start: m.index ?? 0,
    end: (m.index ?? 0) + m[0].length,
    turn: m[1] ?? "",
    number: Number(m[2]),
    letters: (m[3] ?? "").split(","),
  }));

const isFor = (answer: Answer, item: DecideItem): boolean =>
  answer.number === item.number &&
  (item.turn.startsWith(answer.turn) || answer.turn.startsWith(item.turn));

/** The draft's answer to the item, if it holds one. */
export const answerTo = (draft: string, item: DecideItem): Answer | undefined =>
  answersIn(draft).find((answer) => isFor(answer, item));

/** The letters the draft picks for the item; none when it does not answer it. */
export const lettersFor = (draft: string, item: DecideItem): string[] =>
  answerTo(draft, item)?.letters ?? [];

export const isAnswered = (draft: string, item: DecideItem): boolean =>
  answerTo(draft, item) !== undefined;

const inOptionOrder = (item: DecideItem, letters: string[]): string[] =>
  item.options
    .map((o) => o.letter)
    .filter((letter) => letters.includes(letter));

/** The letters an item holds once `letter` is clicked: a checkbox toggles it, the others take it alone. */
export const lettersAfter = (
  item: DecideItem,
  held: string[],
  letter: string,
): string[] =>
  item.kind === "checkbox"
    ? inOptionOrder(
        item,
        held.includes(letter)
          ? held.filter((l) => l !== letter)
          : [...held, letter],
      )
    : [letter];

const withoutAnswer = (draft: string, answer: Answer): string => {
  const before = draft.slice(0, answer.start);
  const after = draft.slice(answer.end);

  return before.endsWith(" ") && (after.startsWith(" ") || after === "")
    ? before.slice(0, -1) + after
    : before + after.replace(/^ /, "");
};

const appended = (draft: string, text: string): string =>
  draft === "" || /\s$/.test(draft) ? draft + text : `${draft} ${text}`;

/**
 * The draft once an option is clicked: the item's answer written in place of
 * the one the draft held, or added at the end; a checkbox item's letter
 * toggled, its answer dropped when no letter is left.
 */
export const choose = (
  draft: string,
  item: DecideItem,
  letter: string,
): string => {
  const held = answerTo(draft, item);
  const letters = lettersAfter(item, held?.letters ?? [], letter);
  const text = `${refOf(item)}.${letters.join(",")}`;

  return held === undefined
    ? appended(draft, text)
    : letters.length === 0
      ? withoutAnswer(draft, held)
      : draft.slice(0, held.start) + text + draft.slice(held.end);
};

const clamp = (position: number, length: number): number =>
  length === 0 ? 0 : Math.min(Math.max(position, 0), length - 1);

/** The first item the draft does not answer; the first item when it answers all. */
export const firstUnanswered = (items: DecideItem[], draft: string): number =>
  Math.max(
    items.findIndex((item) => !isAnswered(draft, item)),
    0,
  );

/** The next item after `position` the draft does not answer, wrapping; `fallback` when there is none. */
const nextUnanswered = (
  items: DecideItem[],
  draft: string,
  position: number,
  fallback: number,
): number => {
  const order = items
    .map((_, n) => (position + 1 + n) % items.length)
    .slice(0, -1);
  const found = order.find((n) => {
    const item = items[n];

    return item !== undefined && !isAnswered(draft, item);
  });

  return found ?? fallback;
};

/** Where the band goes after an option is clicked: on to the next unanswered item, or it stays when all are answered. */
export const afterAnswer = (band: Band, draft: string): number =>
  nextUnanswered(band.items, draft, band.position, band.position);

/** Skip: on to the next unanswered item, else simply the next one. */
export const skipped = (band: Band, draft: string): number =>
  nextUnanswered(band.items, draft, band.position, nextPosition(band));

export const nextPosition = (band: Band): number =>
  band.items.length === 0 ? 0 : (band.position + 1) % band.items.length;

export const prevPosition = (band: Band): number =>
  band.items.length === 0
    ? 0
    : (band.position - 1 + band.items.length) % band.items.length;

/** ✕: hidden until a refresh raises an item not open now. */
export const dismissed = (band: Band): Band => ({
  ...band,
  isDismissed: true,
  dismissedRefs: band.items.map(refOf),
});

/** /answers: shown again, at the first item the draft does not answer. */
export const reopened = (band: Band, draft: string): Band => ({
  ...band,
  isDismissed: false,
  position: firstUnanswered(band.items, draft),
});

const union = (a: string[], b: string[]): string[] => [
  ...new Set([...a, ...b]),
];

/**
 * The band once a refresh found `items` open: an item no longer open is
 * settled, a new one lifts a dismissal, and the band stays on the item it
 * showed if that is still open, else goes to the first unanswered one.
 */
export const refreshed = (
  band: Band,
  items: DecideItem[],
  draft: string,
): Band => {
  const open = items.map(refOf);
  const known = union(band.knownRefs, open);
  const shown = band.items[band.position];
  const kept = shown === undefined ? -1 : open.indexOf(refOf(shown));
  const isNew = open.some((ref) => !band.dismissedRefs.includes(ref));

  return {
    ...band,
    items,
    position: kept >= 0 ? kept : firstUnanswered(items, draft),
    isDismissed: band.isDismissed && !isNew,
    knownRefs: known,
    settledRefs: known.filter((ref) => !open.includes(ref)),
    problem: "",
  };
};

/** The band once a tool row drew `items`: their refs are known, so a later refresh can settle them. */
export const drawnByTool = (band: Band, items: DecideItem[]): Band => ({
  ...band,
  knownRefs: union(band.knownRefs, items.map(refOf)),
});

/** The band's position, held inside its items. */
export const positionIn = (band: Band): number =>
  clamp(band.position, band.items.length);

/** The header line: `🧠 2/5 · <summary>`. */
export const header = (band: Band): string => {
  const position = positionIn(band);
  const item = band.items[position];

  return item === undefined
    ? ""
    : `🧠 ${position + 1}/${band.items.length} · ${item.summary}`;
};

/** One mark per item, `●` answered in the draft and `○` not, with which one the band shows. */
export const progressMarks = (
  band: Band,
  draft: string,
): { mark: string; isShown: boolean }[] =>
  band.items.map((item, n) => ({
    mark: isAnswered(draft, item) ? "●" : "○",
    isShown: n === positionIn(band),
  }));

/** The marks as one line, the shown one drawn as `◉` answered or `◎` not. */
export const progress = (band: Band, draft: string): string =>
  progressMarks(band, draft)
    .map(({ mark, isShown }) => (isShown ? (mark === "●" ? "◉" : "◎") : mark))
    .join(" ");

/** The glyph an option is drawn with: its own, else its item kind's. */
export const glyphOf = (item: DecideItem, letter: string): string =>
  item.options.find((o) => o.letter === letter)?.glyph ||
  (item.kind === "checkbox"
    ? "🔲"
    : item.kind === "binary"
      ? letter === "N"
        ? "👎"
        : "👍"
      : "🔘");

/** A line split at its backticks: even parts are prose, odd parts code. */
export const codeSpans = (line: string): { text: string; isCode: boolean }[] =>
  line
    .split("`")
    .map((text, n) => ({
      text: text.replaceAll("**", ""),
      isCode: n % 2 === 1,
    }))
    .filter((part) => part.text !== "");

/** How many rows an item takes drawn in full, and with its pros, cons and notes left out. */
export const rowsOf = (item: DecideItem): { full: number; brief: number } => {
  const brief = 1 + item.options.length;
  const under = item.options.reduce(
    (sum, o) =>
      sum +
      (o.pros?.length ?? 0) +
      (o.cons?.length ?? 0) +
      (o.notes?.length ?? 0),
    0,
  );

  return { full: brief + (item.note?.length ?? 0) + under, brief };
};

/** The items a tool call or the script handed over, whatever else the JSON held. */
export const itemsOf = (value: unknown): DecideItem[] => {
  const items =
    typeof value === "object" && value !== null && "items" in value
      ? (value as { items: unknown }).items
      : [];

  return Array.isArray(items) ? items.filter(isItem).map(withRef) : [];
};

const isItem = (value: unknown): value is DecideItem => {
  const v = value as Partial<DecideItem> | null;

  return (
    typeof v === "object" &&
    v !== null &&
    typeof v.turn === "string" &&
    typeof v.number === "number" &&
    typeof v.summary === "string" &&
    Array.isArray(v.options) &&
    v.options.every(
      (o) => typeof o?.letter === "string" && typeof o?.name === "string",
    )
  );
};

const withRef = (item: DecideItem): DecideItem => ({
  ...item,
  list: "Decide",
  kind:
    item.kind === "checkbox" || item.kind === "binary" ? item.kind : "radio",
  ref: refOf(item),
});
