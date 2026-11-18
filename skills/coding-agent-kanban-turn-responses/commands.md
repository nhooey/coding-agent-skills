# Bringing back earlier turns' items

_The commands of the [`coding-agent-kanban-turn-responses` skill](SKILL.md) that reprint what earlier turns left open: as written, worked out afresh, or one item at the depth its list needs._

| Command                                                     | Reads                                                                                            | Prints                                                                                                                                                                                                               | Afterwards                                       |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ |
| `open`, or `pending` or `restate`                           | the open Authorizations, Review, Todo and Decide items of every earlier turn                     | each item as written, a Decide item with its context and options, a Todo item with its path and what it frees, grouped by topic and numbered afresh, each naming the turn and item it came from, `(from 4a8683 2.C)` | the earlier turns stay open, rolled up as before |
| `reassess`, or `recheck`, `regenerate` or `recalculate`     | the same, and the work's state now: what has landed, what is running, what has been learnt since | the items still open, worked out afresh, grouped by topic and numbered afresh                                                                                                                                        | the reassessing turn replaces every turn it read |
| `Expand <list>.<n>[.<letter>]`, or a 📌 item by its subject | that item or option                                                                              | it again, at the depth its list needs                                                                                                                                                                                | the expansion is the item's wording from then on |

A prefix of a command's name runs that command where it is a prefix of no other command's name, so `regen` runs `reassess` and `re` runs nothing; a prompt opening on a name or such a prefix, bare or after `/coding-agent-kanban-turn-responses`, runs it.

Both `open` and `reassess` leave out an item a later turn settled or made moot, a Todo item as much as a Decide one, and an Authorizations item once granted or withdrawn, and print into the 🔑 Authorizations, 🔍 Review, 👉 Todo and 🧠 Decide lists, never ❓ Answers. Both read the open items with `scripts/reply_turns.py open`, which prints each turn's Authorizations, Review, Todo and Decide sections under the turn id; `--since ID` starts at one turn, and `decide` prints the Decide sections alone. `outstanding.py items` lists the same items one line each, by the turn that raised them ([scripts.md](scripts.md)).

## Grouping by topic

Both print their lists grouped by topic, as [the skill's commands](SKILL.md#the-commands) lay out and [examples.md](examples.md#a-reassess-grouped-by-topic) draws:

1. Sort the items into topics by their content, each topic one unit of work as the user thinks of it: a repository, a plan, a pull-request stack, a workstream. A `reassess` names a topic carried over from the previous `reassess` by the name that turn gave it.
2. Keep a topic of 3 items or more, at most 6 of them, and put every other item under `Miscellaneous`.
3. Order the topics by how much each holds to decide or do, the most first, `Miscellaneous` last.
4. Under each topic header and its `═` underline, print the topic's lists in the lists' order, a list with no items in the topic left out.
5. Number each list on across topics: the second topic's Decide list starts one past the first topic's last Decide item.

## `open`: the open items as they were written

The items are reprinted with their wording and options unchanged, so the user can answer the items they were already shown; a Todo item keeps its path and what it frees. Grouping only moves them under their topics and renumbers them. `pending` and `restate` are other names for it.

## `reassess`: the open items, worked out afresh

`recheck`, `regenerate` and `recalculate` are other names for it.

The earlier items are evidence of what is undecided, not a structure to keep. The reassess takes no item's wording, grouping, numbering or options as given:

- **Merged:** items that are one decision become one item, such as a sending date raised in one turn and what the send waits for raised in another.
- **Split:** an item that holds 2 decisions becomes 2 items.
- **Dropped:** an item that the state of the work has settled or made moot is left out.
- **Changed:** an option whose cost or gain has changed since is rewritten with today's figures.
- **Added:** a decision the work's state now needs, and that no earlier item asked, is raised.
- **Reordered:** within its topic's list, the decision that gates the most work is printed first.

Each Decide item follows the skill's rules for a Decide item; each Todo item still open stays an action of the user's with its path and what it frees, merged only where 2 ask the same action. The reassessing turn's lists replace every earlier turn it read: the turn prints no 📌 roll-up, the next roll-up holds that turn's items and later ones alone, and `outstanding.py render` and `decide` reach back no further than it. An answer to an item of a replaced turn is read against the reassessed item that took it in.

## `Expand`: one item at the depth its list needs

An expanded item, or option, holds what the user needs to act on it without reading anything else, and what that is depends on its list:

| List              | An expanded item gives                                                                                                                                                                                                                                                                                                                |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 🔑 Authorizations | what the grant is and what asks for it, where to give it, the prompt's window or the exact approval message to send, when it times out, everything it covers as a nested list, and what granting it frees                                                                                                                             |
| 🔍 Review         | what the thing is and why it is up for review, where to open it as a link they can click, what to look for, and what their review frees                                                                                                                                                                                               |
| 👉 Todo           | numbered steps; enough context to find the thing, its name as it appears where they will look for it, a date or a size that tells it from its neighbours; and every link or text they need, in the form its destination takes: a URL to click, a command or a prompt in its own `text` block to copy, a path from the repository root |
| 🧠 Decide         | what the thing being decided is and how it came up, the facts each option turns on, with figures from the database or the run, what each option does and costs, which one is recommended and why, and what happens if they do not decide                                                                                              |

An expanded option expands the same way, under its own item's summary. The expansion is printed in its list as new this turn.
