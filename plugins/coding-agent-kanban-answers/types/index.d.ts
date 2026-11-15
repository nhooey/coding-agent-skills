/** One option of a Decide item: its capital letter and its bold name. */
export type DecideOption = { letter: string; name: string };

/** radio: exactly one letter; checkbox: any number; binary: Y or N. */
export type DecideKind = "radio" | "checkbox" | "binary";

/**
 * One open Decide item, as `outstanding.py decide --json` prints it and the
 * `kanban_options` tool takes it.
 */
export type DecideItem = {
  turn: string;
  list: "Decide";
  number: number;
  summary: string;
  kind: DecideKind;
  ref: string;
  options: DecideOption[];
};

/** The band above the prompt: the open items and where it stands among them. */
export type Band = {
  /** The open Decide items, oldest first, from the last refresh. */
  items: DecideItem[];
  /** Which item the band shows, an index into `items`. */
  position: number;
  /** True after ✕, until a refresh raises an item not in `dismissedRefs`, or /answers. */
  isDismissed: boolean;
  /** The items' refs when ✕ was pressed. */
  dismissedRefs: string[];
  /** Every ref a tool row drew or a refresh found open, so a ref gone from the open list reads as settled. */
  knownRefs: string[];
  /** Known refs no longer open: their tool-row buttons are dimmed and do nothing. */
  settledRefs: string[];
  /** Why the last refresh found nothing, for the band to say; empty when it worked. */
  problem: string;
};

declare module "claude-code" {
  interface PluginState {
    "coding-agent-kanban-answers": {
      band: Shaped<Band>;
      draft: string;
    };
  }
}
