---
name: coding-agent-review-queue-in-browser
description: |
  Use when the user asks to review, merge or go through what's waiting on
  them, says "next" during a review, or anything under review changes: a
  report pushed, a pull request force-pushed or re-synced, an item settled
  or added. Brings the Claude in Chrome tab group to one end state after
  every change: the current review chunk's items and nothing else, each
  at its latest version, in order with stacked pull requests side by side
  bottom first, pull requests on their Overview, the first tab its
  window's active tab without ever taking focus from the user, and the
  user told with a sound and one notification, after one listing the
  steps about to happen. While it updates, the window sits on a new tab,
  and each changed item's tab closes and reopens at its new version. The
  review queue is the kanban replies' open Review and Todo items (pull
  requests to review or merge, reports on GitHub, issue drafts to
  submit), and a bundled Babashka program works out the tab actions. An
  unsubmitted form or draft is never touched.
---

# Review queue in the browser

_After every change under review, the session's tab group reaches one end state. A program works out the actions that reach it; the agent applies them._

## The end state

Before every reconcile, the user has been told what it will do, with one sound and one notification, 1 second before anything moves.
After every reconcile, the tab group:

- **holds the current chunk, and nothing else:** one tab per item of the queue's first chunk, or of every chunk with the `all-open` chunk mode, where nothing closes;
- **is in order:** the chunk's order, with the pull requests of one stack side by side, in merge order, bottom first, nothing between them;
  - a stack is a GitHub stack, or a chain where one pull request's base is another's head branch;
  - a stack has all its open members, and sits where its first member in the chunk is;
- **is on the Overview:** every pull request tab at its plain `/pull/<n>` URL, never `/files`, `/changes` or `/commits`;
- **is up to date:** every tab at its item's latest version, finished loading, a changed item's tab closed and reopened rather than reloaded in place;
- **starts at the first tab:** the first tab is its window's active tab, and neither the window nor the browser app is raised, so the review queue never takes focus from the user;
- **has told the user,** when it gained a new or changed item or a new chunk opened: one "Review ready" sound and one macOS notification, never one per tab, naming how many items there are to review and the first one, and opening it when clicked.

## While it updates

Whenever a reconcile opens, closes or re-points a tab, the update is under way until its last tab loads:

- **While an update is under way:** the review window's active tab is a new tab, Chrome's new tab page, so the user sees a neutral page, not a half-updated review item.
  AppleScript appends it last with `make new tab at end of tabs of w` and makes it the window's active tab with `set active tab index`; it never runs `activate` or raises the window.
- **When the update starts:** the tab of each changed item closes, rather than reloading in place; a tab holding an unsubmitted form or draft is never closed.
- **When the update lands:** each changed item's tab reopens at its new version, in its place in the order, the first tab becomes the window's active tab, and the parking tab closes.

## When to reconcile

Whenever anything the user reviews changes, mark it in the queue, then reconcile:

- **An item changed,** such as a report pushed or a pull request force-pushed or re-synced: mark it `:changed`.
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
| `:changed`  | true when it changed since its tab last loaded               |
| `:done`     | true once the user says it is reviewed or submitted          |
| `:deferred` | true for an item the user skipped with "next"                |

## How the program reaches it

1. Load `coding-agent-browser-selection`, and find out from its wake step whether waking the browser will launch the app or open a new window, before doing either.
2. When it will do neither, read the group now, since reading moves nothing: check the browser, noting the app and window id it finds, call `tabs_context_mcp` for the group's tabs in its order, and mark each tab holding an unsubmitted form or draft `"untouchable": true`.
3. Before anything moves, announce the reconcile, so the user is ready for the disruption.
   Pass the tabs when step 2 read them, else `--launch` and `--open-window` as the wake step will do them:

   ```bash
   bb --config ~/.agents/skills/coding-agent-review-queue-in-browser/scripts/bb.edn --main review-queue.main --chunk-size 5 --chunk-mode current-only --app 'Google Chrome' --launch --open-window --announce --announce-sound /System/Library/PrivateFrameworks/ToneLibrary.framework/Versions/A/Resources/AlertTones/EncoreInfinitum/Slide-EncoreInfinitum.caf <<'EOF'
   [{:url "https://github.com/owner/repo/pull/12" :kind :merge :topic "kanban"}]
   EOF
   ```

   The program plays the sound and, at the same time, shows one notification listing only the steps that will happen, then waits 1 second:

   ```text
   Opening the review queue in Google Chrome:
   • Launch Google Chrome
   • Wait for its extension
   • Open a new window
   • Show a new tab while updating
   • Close 2 changed review items
   • Load 11 review items
   ```

4. When step 2 didn't read the group, wake and check the browser now, and read the group as in step 2.
5. Run the program with the tabs, the window id and `--notify`.
   Through Chrome's AppleScript, in that window, it parks the window on a new tab when `:park` is true, then re-points tabs in the background, and prints the rest, with the parking tab's id as `:parked`:

   ```bash
   bb --config ~/.agents/skills/coding-agent-review-queue-in-browser/scripts/bb.edn --main review-queue.main --chunk-size 5 --chunk-mode current-only --app 'Google Chrome' --apply-window 1234 --notify --sound /System/Library/PrivateFrameworks/ToneLibrary.framework/Versions/A/Resources/AlertTones/EncoreInfinitum/Handoff-EncoreInfinitum.caf --tabs '[{"tabId": 1, "url": "https://github.com/owner/repo/pull/12/files"}, {"tabId": 2, "url": "https://github.com/owner/repo/issues/new", "untouchable": true}]' <<'EOF'
   [{:url "https://github.com/owner/repo/pull/12" :kind :merge :topic "kanban"}]
   EOF
   ```

   When step 2 read the group, steps 3 and 5 are one run, with both sets of options.
   Without `bb` on the path, run it through `nix shell nixpkgs#babashka --command bb`.

6. With Claude in Chrome's tools, close the `:close` tabs, the `:updated` changed items' tabs among them, and open the `:open` URLs in order, which only the extension can do inside the tab group.
7. Land the update, once: make the `:focus` tab its window's active tab and close the parking tab, with the app and window id from the browser check and `--unpark` set to `:parked`, without raising the window or the app:

   ```bash
   bb --config ~/.agents/skills/coding-agent-review-queue-in-browser/scripts/bb.edn --main review-queue.main --app 'Google Chrome' --focus-window 1234 --focus-url 'https://github.com/owner/repo/pull/12' --unpark 5678
   ```

8. In the kanban reply, name the chunk, its topic and how many chunks are left, and list the `:finished` items with their links, by `github-hygiene-refer-to-issues-and-pull-requests`.
   Tell the user when the program reports a notification as `:delivered false`.

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
- checks each end-state property in order, one function each, and prints the `:tab-actions` that make it hold: the URLs to `:open`, the tabs to `:repoint` with their URLs and the properties they serve, the changed items' tabs, `:updated`, the tabs to `:close`, whether to `:park` on a new tab, the `:focus` tab, and the `:notification`;
- with `--announce`, sends the steps a reconcile will take as an `:announcement`, in the `review-start` group, with the `--announce-sound`, before any tab moves;
- with `--apply-window`, parks that window on a new tab, then runs the `:repoint` actions through Chrome's AppleScript, finding each tab by its URL first;
- with `--notify`, sends the `:notification`, in the `review` group, with the `--sound`;
- sends each one with `terminal-notifier`, or `osascript` without it, playing its sound with `afplay` at the same time, then checks with `terminal-notifier -list <group>` that it was delivered, and says `:delivered false`, on standard error too, when it wasn't.

No tool moves a tab, so the program keeps the order by re-pointing tabs in their slots: a tab showing another item is set to the URL its slot needs, which loads it afresh.
A tab whose item didn't change already shows its latest version, so only a changed item's tab closes and reopens, and the program fills the slots after it as if it were gone, so the item reopens in its place.

## Exceptions

- **An unsubmitted form or draft is never touched:** its tab is never re-pointed or closed, even when its item changed.
  The program fixes it in its slot and fills the other slots around it; a stack that would straddle it goes before it, and the tab ends up just after the stack.
- **Only Chrome is used:** Chrome's AppleScript, in the window the browser check found and never the frontmost one, to open and close the parking tab, re-point tabs and pick the window's active tab, all in the background, never activating the app or raising the window, and Claude in Chrome's tools only for what AppleScript can't do, opening and closing tabs in the tab group.
  Claude in Chrome's `navigate` makes each tab active in turn, so it is never used to re-point.
  The tools' limits stand, and nothing works around them:
  - a session gets one tab group, and can't name it, create another or see a tab outside it;
  - no extension tool moves a tab or makes one active;
  - AppleScript can't see tab groups, and the program takes `tabs_context_mcp`'s list to be in the group's order.

## Your preferences

!`cat "${CLAUDE_SKILL_DIR}/../coding-agent-review-queue-in-browser.preferences.md" "${CLAUDE_PROJECT_DIR}/.agents/skills/coding-agent-review-queue-in-browser.preferences.md" 2>/dev/null || true`

If your agent doesn't run the line above, read these files yourself if they
exist: `coding-agent-review-queue-in-browser.preferences.md` next to this skill's folder, then
`.agents/skills/coding-agent-review-queue-in-browser.preferences.md` in the project. A project's
file overrides the user's, and the user's overrides this skill's defaults.

The preferences file holds up to 5 keys, as a Markdown list:

- **Chunk mode:** `current-only`, the default, or `all-open`.
- **Chunk size:** the most items in a chunk; 5 by default.
- **Browser:** the browser app, overriding `coding-agent-browser-selection`'s preferences.
- **Sound:** the sound file the "Review ready" notification plays, passed as `--sound`; `/System/Library/PrivateFrameworks/ToneLibrary.framework/Versions/A/Resources/AlertTones/EncoreInfinitum/Handoff-EncoreInfinitum.caf` by default.
- **Announce sound:** the sound file the notice before a reconcile plays, passed as `--announce-sound`; `/System/Library/PrivateFrameworks/ToneLibrary.framework/Versions/A/Resources/AlertTones/EncoreInfinitum/Slide-EncoreInfinitum.caf` by default.

## Related skills

When one of these applies and it's in your skill listing, load it
without asking. If it isn't in your listing, tell the user which skill is
missing and ask whether to install it from the same collection this skill
came from; don't apply it from memory.

- `coding-agent-browser-selection`: picks the browser app and window the tabs open in.
- `coding-agent-draft-in-browser`: fills the issue and comment drafts the queue holds, and never submits them.
- `coding-agent-kanban-turn-responses`: lists the Review and Todo items the queue is built from, and the finished ones.
- `github-hygiene-refer-to-issues-and-pull-requests`: how the reply names each finished pull request and issue.
