import { describe, expect, test } from "claude-code/testing";

import {
  afterAnswer,
  choose,
  dismissed,
  drawnByTool,
  emptyBand,
  firstUnanswered,
  header,
  itemsOf,
  lettersFor,
  nextPosition,
  prevPosition,
  codeSpans,
  fitsBand,
  rowsNeeded,
  progress,
  refreshed,
  reopened,
  skipped,
} from "../hooks/answers";
import type { Band, DecideItem } from "../types";

const radio: DecideItem = {
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
};
const checkbox: DecideItem = {
  ...radio,
  number: 2,
  summary: "Cleanups to start",
  kind: "checkbox",
  ref: "9efb08a1.Decide.2",
  options: [
    { letter: "A", name: "Matchers" },
    { letter: "B", name: "Dead code" },
    { letter: "C", name: "Stale render" },
  ],
};
const binary: DecideItem = {
  ...radio,
  number: 3,
  summary: "Ship tonight?",
  kind: "binary",
  ref: "9efb08a1.Decide.3",
  options: [
    { letter: "Y", name: "Ship" },
    { letter: "N", name: "Hold" },
  ],
};
const items = [radio, checkbox, binary];
const band: Band = { ...emptyBand, items, knownRefs: items.map((i) => i.ref) };

describe("building and replacing references in the draft", () => {
  test("a click on an empty draft writes the reference", () => {
    expect(choose("", radio, "A")).toBe("9efb08a1.Decide.1.A");
  });

  test("a click appends after what the person typed, with one space", () => {
    expect(choose("Go ahead:", radio, "B")).toBe(
      "Go ahead: 9efb08a1.Decide.1.B",
    );
    expect(choose("Go ahead: ", radio, "B")).toBe(
      "Go ahead: 9efb08a1.Decide.1.B",
    );
  });

  test("another option of an answered item replaces its reference in place", () => {
    const draft = "x 9efb08a1.Decide.1.A y 9efb08a1.Decide.3.Y";
    expect(choose(draft, radio, "B")).toBe(
      "x 9efb08a1.Decide.1.B y 9efb08a1.Decide.3.Y",
    );
  });

  test("a reference typed with a shorter turn id is found and replaced", () => {
    expect(choose("9efb08a.Decide.3.Y", binary, "N")).toBe(
      "9efb08a1.Decide.3.N",
    );
  });

  test("the same option clicked again leaves the draft as it was", () => {
    expect(choose("9efb08a1.Decide.1.A", radio, "A")).toBe(
      "9efb08a1.Decide.1.A",
    );
  });

  test("an item of another turn with the same number is not touched", () => {
    expect(choose("0f311c94.Decide.1.A", radio, "B")).toBe(
      "0f311c94.Decide.1.A 9efb08a1.Decide.1.B",
    );
  });

  test("the letters a draft picks are read back", () => {
    expect(lettersFor("9efb08a1.Decide.2.A,C", checkbox)).toEqual(["A", "C"]);
    expect(lettersFor("nothing here", checkbox)).toEqual([]);
  });
});

describe("checkbox items", () => {
  test("a second letter joins the first, in option order", () => {
    const once = choose("", checkbox, "C");
    expect(once).toBe("9efb08a1.Decide.2.C");
    expect(choose(once, checkbox, "A")).toBe("9efb08a1.Decide.2.A,C");
  });

  test("a letter clicked again is taken out", () => {
    expect(choose("9efb08a1.Decide.2.A,C", checkbox, "A")).toBe(
      "9efb08a1.Decide.2.C",
    );
  });

  test("the last letter taken out drops the reference and its space", () => {
    expect(choose("ok 9efb08a1.Decide.2.B thanks", checkbox, "B")).toBe(
      "ok thanks",
    );
    expect(choose("ok 9efb08a1.Decide.2.B", checkbox, "B")).toBe("ok");
  });
});

describe("prev and next, skip, dismiss and bring back", () => {
  test("next and prev wrap around the items", () => {
    expect(nextPosition({ ...band, position: 2 })).toBe(0);
    expect(prevPosition({ ...band, position: 0 })).toBe(2);
  });

  test("after an answer the band goes to the next unanswered item", () => {
    expect(
      afterAnswer(
        { ...band, position: 0 },
        "9efb08a1.Decide.1.A 9efb08a1.Decide.2.B",
      ),
    ).toBe(2);
  });

  test("after the last answer the band stays where it is", () => {
    const all = "9efb08a1.Decide.1.A 9efb08a1.Decide.2.B 9efb08a1.Decide.3.Y";
    expect(afterAnswer({ ...band, position: 2 }, all)).toBe(2);
  });

  test("skip passes answered items, and moves on when all are answered", () => {
    expect(skipped({ ...band, position: 0 }, "9efb08a1.Decide.2.A")).toBe(2);
    const all = "9efb08a1.Decide.1.A 9efb08a1.Decide.2.B 9efb08a1.Decide.3.Y";
    expect(skipped({ ...band, position: 0 }, all)).toBe(1);
  });

  test("dismiss hides the band until a refresh raises a new item", () => {
    const hidden = dismissed(band);
    expect(hidden.isDismissed).toBe(true);
    expect(refreshed(hidden, items, "").isDismissed).toBe(true);
    const newer = { ...radio, turn: "b2c3d4e5", ref: "b2c3d4e5.Decide.1" };
    expect(refreshed(hidden, [...items, newer], "").isDismissed).toBe(false);
  });

  test("/answers brings it back at the first unanswered item", () => {
    const back = reopened(
      { ...dismissed(band), position: 2 },
      "9efb08a1.Decide.1.A",
    );
    expect(back.isDismissed).toBe(false);
    expect(back.position).toBe(1);
  });

  test("a refresh keeps the shown item, and settles an item no longer open", () => {
    const after = refreshed({ ...band, position: 2 }, [checkbox, binary], "");
    expect(after.position).toBe(1);
    expect(after.settledRefs).toEqual(["9efb08a1.Decide.1"]);
  });

  test("a tool row makes its items known, so a refresh that drops them settles them", () => {
    const drawn = drawnByTool(emptyBand, [binary]);
    expect(refreshed(drawn, [radio], "").settledRefs).toEqual([
      "9efb08a1.Decide.3",
    ]);
  });

  test("the first unanswered item, and the first item when all are answered", () => {
    expect(firstUnanswered(items, "9efb08a1.Decide.1.A")).toBe(1);
    expect(
      firstUnanswered(
        items,
        "9efb08a1.Decide.1.A 9efb08a1.Decide.2.A 9efb08a1.Decide.3.N",
      ),
    ).toBe(0);
  });
});

describe("what the band says", () => {
  test("the header counts the items and names the shown one", () => {
    expect(header({ ...band, position: 1 })).toBe("🧠 2/3 · Cleanups to start");
  });

  test("the progress marks the answered items and rings the shown one", () => {
    expect(progress({ ...band, position: 1 }, "9efb08a1.Decide.1.A")).toBe(
      "● ◎ ○",
    );
    expect(progress({ ...band, position: 0 }, "9efb08a1.Decide.1.A")).toBe(
      "◉ ○ ○",
    );
  });

  test("an item's rows count its lines, wrapped at their indent", () => {
    const item = {
      turn: "9efb08a1",
      list: "Decide" as const,
      number: 1,
      summary: "Short",
      kind: "radio" as const,
      ref: "9efb08a1.Decide.1",
      note: ["A note."],
      options: [
        { letter: "A", name: "One", pros: ["Good."], cons: ["x".repeat(150)] },
        { letter: "B", name: "Two" },
      ],
    };

    // Border, controls and gap 4, title 1, note 1, A 1 + pro 1 + con 2, B 1.
    expect(rowsNeeded(item, 100)).toBe(11);
    expect(fitsBand([item], { rows: 11, columns: 100 })).toBe(true);
    expect(fitsBand([item], { rows: 10, columns: 100 })).toBe(false);
    expect(fitsBand([item], { rows: 0, columns: 0 })).toBe(false);
  });

  test("code spans split at backticks and lose their bold marks", () => {
    expect(codeSpans("Keep **`old-forks`** as is")).toEqual([
      { text: "Keep ", isCode: false },
      { text: "old-forks", isCode: true },
      { text: " as is", isCode: false },
    ]);
  });
});

describe("the items a tool call or the script hands over", () => {
  test("a ref and a kind left out are filled in, and a malformed item dropped", () => {
    const found = itemsOf({
      items: [
        {
          turn: "abc12345",
          number: 4,
          summary: "S",
          options: [{ letter: "A", name: "a" }],
        },
        { turn: 1 },
      ],
    });
    expect(found).toEqual([
      {
        turn: "abc12345",
        list: "Decide",
        number: 4,
        summary: "S",
        kind: "radio",
        ref: "abc12345.Decide.4",
        options: [{ letter: "A", name: "a" }],
      },
    ]);
  });
});
