---
name: coding-agent-review-queue-in-browser
description: |
  Use when the user asks to review, merge or go through what's waiting on
  them, says "next" during a review, or anything under review changes: a
  report pushed, a pull request force-pushed or re-synced, an item settled
  or added. Brings a named Google Chrome tab group, `Review` by default,
  to one end state after every change: the current review chunk's items
  and nothing else, each freshly loaded, in order with stacked pull
  requests side by side bottom first, pull requests on their Overview,
  set through the `declarative-tab-groups` command without ever taking
  focus from the user, and the user told with a sound and one
  notification. The review queue is the kanban replies' open Review and
  Todo items (pull requests to review or merge, reports on GitHub, issue
  drafts to submit), and a bundled Babashka program orders and chunks it
  and sets the group. A tab holding an unsubmitted form stays open.
---

# Review queue in the browser

_After every change under review, a named Google Chrome tab group reaches one end state. A bundled program works out the group's items and sets it through the `declarative-tab-groups` command._

## The end state

After every reconcile, the tab group titled `Review`, or the title the preferences give:

- **holds the current chunk, and nothing else:** after the group's status page, one tab per item of the queue's first chunk, or of every chunk with the `all-open` chunk mode;
- **is in order:** the chunk's order, with the pull requests of one stack side by side, in merge order, bottom first, nothing between them;
  - a stack is a GitHub stack, or a chain where one pull request's base is another's head branch;
  - a stack has all its open members, and sits where its first member in the chunk is;
- **is on the Overview:** every pull request tab at its plain `/pull/<n>` URL, never `/files`, `/changes` or `/commits`;
- **is up to date:** every tab freshly loaded at its item's latest version;
- **took no focus:** no window was raised or focused and no review tab made active, so the review queue never takes focus from the user; the group's status page, its first tab, shows the update's progress;
- **has told the user,** when it holds any item: one "Review ready" sound and one macOS notification, never one per tab, naming how many items there are to review and the first one, and opening it when clicked.

Before every reconcile that loads any item, the user has been told how many will load, with one sound and one notification, 1 second before anything moves.

## When to reconcile

Whenever anything the user reviews changes, update the queue, then reconcile:

- **An item changed,** such as a report pushed or a pull request force-pushed or re-synced.
- **An item settled,** merged, closed or submitted, or reviewed by the user's say: mark it `:done`, or let the program find it merged or closed.
- **An item added** to the kanban's Review or Todo items.
- **"next",** or the kanban mod's `next-chunk` command: mark the current chunk's unfinished items `:deferred`, which moves them to the back of the queue.
- **The review starts.**

## The queue

The queue is every 🔍 Review and 👉 Todo item the kanban replies list that the user acts on in a browser: a pull request to review or merge, a report on GitHub, or an issue or comment draft to submit.
Work it out afresh at each reconcile, from the kanban's open Review and Todo items; for now nothing stores it, and the kanban mod may keep it later.
Write it as an EDN or JSON list, one map per item:

| Key         | Value                                                        |
| ----------- | ------------------------------------------------------------ |
| `:url`      | the page to open                                             |
| `:kind`     | `decision`, `report`, `merge`, `review` or `draft`           |
| `:topic`    | a short name shared by items that belong together            |
| `:priority` | optional; lower comes first, overriding the kind's order     |
| `:stack-id` | optional; names a GitHub stack the program can't find itself |
| `:stack`    | optional; a stacked pull request's position, 1 at the bottom |
| `:label`    | optional; its name in the notification, else `owner/repo#N`  |
| `:done`     | true once the user says it is reviewed or submitted          |
| `:deferred` | true for an item the user skipped with "next"                |

## The command

`declarative-tab-groups` comes from the public repository [nhooey/chrome-extension-declarative-tab-groups](https://github.com/nhooey/chrome-extension-declarative-tab-groups), with the Google Chrome extension and native-messaging host it talks to.
Install them as its README says.
The program finds the command on the `PATH`, like `bb` and `gh`; the command never starts Chrome.

## How the program reaches it

1. Run the program with the queue, once per reconcile:

   ```bash
   bb --config ~/.agents/skills/coding-agent-review-queue-in-browser/scripts/bb.edn --main review-queue.main --chunk-size 5 --chunk-mode current-only --group Review --announce --announce-sound /System/Library/PrivateFrameworks/ToneLibrary.framework/Versions/A/Resources/AlertTones/EncoreInfinitum/Slide-EncoreInfinitum.caf --notify --sound /System/Library/PrivateFrameworks/ToneLibrary.framework/Versions/A/Resources/AlertTones/EncoreInfinitum/Handoff-EncoreInfinitum.caf <<'EOF'
   [{:url "https://github.com/owner/repo/pull/12" :kind :merge :topic "kanban"}]
   EOF
   ```

   Without `bb` on the path, run it through `nix shell nixpkgs#babashka --command bb`.

2. In the kanban reply, name the chunk, its topic and how many chunks are left, and list the `:finished` items with their links, by `github-hygiene-refer-to-issues-and-pull-requests`.
   Tell the user:
   - each tab under `:tab-group`'s `:kept`, by title and link, left open for its unsubmitted form;
   - a notification the program reports as `:delivered false`;
   - the `:failure`, when the program exits non-zero.

The program:

- asks `gh` for each pull request's and issue's state, and drops the finished ones;
- finds stacks with `gh pr list --state open --json url,baseRefName,headRefName` in each repository the queue's pull requests are in, and brings in each stack's open members the queue lacks, with the kind and topic of its first member in the queue;
- orders the rest, and splits it into `:chunks` of at most `--chunk-size`:
  1. blocking decisions;
  2. reports;
  3. pull requests to merge;
  4. the rest;
  5. deferred items, in the same order;
- keeps each chunk to one topic, except that one-item topics come after the bigger ones and adjacent ones share a `mixed` chunk, and never splits a stack, even past `--chunk-size`;
- with `--announce`, sends how many items will load as an `:announcement`, in the `review-start` group, with the `--announce-sound`, and waits 1 second;
- runs `declarative-tab-groups set --group <title> --json -- <url>…` once, with the group's URLs, or none for an empty queue, and prints the response as `:tab-group`;
- with `--notify`, once the group is set, sends the `:notification`, in the `review` group, with the `--sound`;
- sends each one with `terminal-notifier`, or `osascript` without terminal-notifier, playing its sound with `afplay` at the same time, then checks with `terminal-notifier -list <group>` that it was delivered, and says `:delivered false`, on standard error too, when it wasn't;
- names each `:kept` tab on standard error, as a success;
- exits 1 with a `:failure`, on standard error too, when the command isn't on the `PATH`, can't reach Chrome's extension, refuses its arguments, fails or answers with no JSON response; the first two name the install step.

## Exceptions

- **A tab holding an unsubmitted form or draft is never closed:** the command keeps it open, beside the group's fresh tabs, and lists it under `:kept`.
- **Only Google Chrome is used, through `declarative-tab-groups` alone:** when Chrome or its extension isn't running, the program fails and the user starts it.

## Your preferences

!`cat "$(dirname "${CLAUDE_SKILL_DIR}")/coding-agent-review-queue-in-browser.preferences.md" "${CLAUDE_PROJECT_DIR}/.agents/skills/coding-agent-review-queue-in-browser.preferences.md" 2>/dev/null || true`

If your agent doesn't run the line above, read these files yourself if they
exist: `coding-agent-review-queue-in-browser.preferences.md` next to this skill's folder, then
`.agents/skills/coding-agent-review-queue-in-browser.preferences.md` in the project. A project's
file overrides the user's, and the user's overrides this skill's defaults.

The preferences file holds up to 5 keys, as a Markdown list:

- **Chunk mode:** `current-only`, the default, or `all-open`.
- **Chunk size:** the most items in a chunk; 5 by default.
- **Group:** the tab group's title, passed as `--group`; `Review` by default.
- **Sound:** the sound file the "Review ready" notification plays, passed as `--sound`; `/System/Library/PrivateFrameworks/ToneLibrary.framework/Versions/A/Resources/AlertTones/EncoreInfinitum/Handoff-EncoreInfinitum.caf` by default.
- **Announce sound:** the sound file the notice before a reconcile plays, passed as `--announce-sound`; `/System/Library/PrivateFrameworks/ToneLibrary.framework/Versions/A/Resources/AlertTones/EncoreInfinitum/Slide-EncoreInfinitum.caf` by default.

## Related skills

When one of these applies and it's in your skill listing, load it
without asking. If it isn't in your listing, tell the user which skill is
missing and ask whether to install it from the same collection this skill
came from; don't apply it from memory.

- `coding-agent-draft-in-browser`: fills the issue and comment drafts the queue holds, and never submits them.
- `coding-agent-kanban-turn-responses`: lists the Review and Todo items the queue is built from, and the finished ones.
- `github-hygiene-refer-to-issues-and-pull-requests`: how the reply names each finished pull request and issue.
