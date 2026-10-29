# Bringing back earlier turns' items

_The commands of the [`coding-agent-kanban-turn-responses` skill](SKILL.md) that reprint what earlier turns left open: as written, worked out afresh, or one item at the depth its list needs._

| Command                                                     | Reads                                                                                            | Prints                                                                                                                                                                                                                    | Afterwards                                       |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ |
| `pending`                                                   | the open Review, Todo and Decisions items of every earlier turn                                  | each item as written, a Decisions item with its context and options, a Todo item with its path and what it frees, numbered afresh from 1 within its list, each naming the turn and item it came from, `(from 4a8683 2.C)` | the earlier turns stay open, rolled up as before |
| `reassess`                                                  | the same, and the work's state now: what has landed, what is running, what has been learnt since | the items still open, worked out afresh, each list numbered from 1                                                                                                                                                        | the reassessing turn replaces every turn it read |
| `Expand <list>.<n>[.<letter>]`, or a 📌 item by its subject | that item or option                                                                              | it again, at the depth its list needs                                                                                                                                                                                     | the expansion is the item's wording from then on |

Both `pending` and `reassess` leave out an item a later turn settled or made moot, a Todo item as much as a Decisions one, and print into the 🔍 Review, 👉 Todo and 🧠 Decisions lists, never ❓ Answers. Both read the open items with `scripts/reply_turns.py open`, which prints each turn's Review, Todo and Decisions sections under the turn id; `--since ID` starts at one turn, and `decisions` prints the Decisions sections alone. `outstanding.py items` lists the same items one line each, by the turn that raised them ([scripts.md](scripts.md)).

## `pending`: the open items as they were written

The items are reprinted with their wording, grouping and options unchanged, so the user can answer the list they were already shown; a Todo item keeps its path and what it frees.

## `reassess`: the open items, worked out afresh

The earlier items are evidence of what is undecided, not a structure to keep. The reassessment takes no item's wording, grouping, numbering or options as given:

- **Merged:** items that are one decision become one item, such as a sending date raised in one turn and what the send waits for raised in another.
- **Split:** an item that holds 2 decisions becomes 2 items.
- **Dropped:** an item that the state of the work has settled or made moot is left out.
- **Changed:** an option whose cost or gain has changed since is rewritten with today's figures.
- **Added:** a decision the work's state now needs, and that no earlier item asked, is raised.
- **Reordered:** the decision that gates the most work is printed first.

Each Decisions item follows the skill's rules for a Decisions item; each Todo item still open stays an action of the user's with its path and what it frees, merged only where 2 ask the same action. The reassessing turn's lists replace every earlier turn it read: the turn prints no 📌 roll-up, the next roll-up holds that turn's items and later ones alone, and `outstanding.py render` reaches back no further than it. An answer to an item of a replaced turn is read against the reassessed item that took it in.

## `Expand`: one item at the depth its list needs

An expanded item, or option, holds what the user needs to act on it without reading anything else, and what that is depends on its list:

| List         | An expanded item gives                                                                                                                                                                                                                                                                                                                |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 🔍 Review    | what the thing is and why it is up for review, where to open it as a link they can click, what to look for, and what their review frees                                                                                                                                                                                               |
| 👉 Todo      | numbered steps; enough context to find the thing, its name as it appears where they will look for it, a date or a size that tells it from its neighbours; and every link or text they need, in the form its destination takes: a URL to click, a command or a prompt in its own `text` block to copy, a path from the repository root |
| 🧠 Decisions | what the thing being decided is and how it came up, the facts each option turns on, with figures from the database or the run, what each option does and costs, which one is recommended and why, and what happens if they do not decide                                                                                              |

An expanded option expands the same way, under its own item's summary. The expansion is printed in its list as new this turn.
