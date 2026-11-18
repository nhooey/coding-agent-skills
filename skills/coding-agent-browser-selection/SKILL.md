---
name: coding-agent-browser-selection
description: |
  Before any browser work with the Claude in Chrome tools
  (mcp__claude-in-chrome__*), make sure the session drives the browser app
  and window the user prefers. Several browsers can have the extension
  connected, and list_connected_browsers names them only "Browser 1",
  "Browser 2", in no stable order, so a session can act in the wrong one,
  such as the user's personal browser. Covers marking the session's tab URL,
  finding which app and window holds it with the bundled macOS script,
  switching browsers until one matches the user's preferences, asking when
  none does, waking the preferred app when it has no window and so dropped
  off the list, before any tab is made, and bringing only the preferred app
  forward. Load it before the first mcp__claude-in-chrome__* call of a
  session, again after any select_browser or switch_browser, and when
  list_connected_browsers shows only browsers that could be one the user said
  not to use.
---

# Browser selection

_Before acting in a browser through Claude in Chrome, find out which app and window the session's tab is in, and switch until it is the one the user prefers. Never act in a browser the user said not to use._

## Why

Each browser with the Claude in Chrome extension connected shows up in `list_connected_browsers` as "Browser 1", "Browser 2" and so on. The labels say nothing about which app is which, and the numbering changes between sessions. A session that takes the one marked `inUse` may be driving the user's personal browser, its signed-in accounts and open windows.

The tools can't tell you which app a browser is, but the app can: put a unique marker in the session's tab URL, then ask each running browser through AppleScript which window has a tab with that URL.

## Defaults

With no preferences set, don't switch, and wake nothing. Find out which app and window the session is in, tell the user, and go on.

## Check the browser

Do this before the first browser action of a session, and again after any `select_browser` or `switch_browser`.

1. Call `list_connected_browsers`, and note each browser's `deviceId` and the one marked `inUse`.
2. Choose a browser known not to be an app never to use. Until one is chosen, call no `tabs_context_mcp`, `tabs_create_mcp` or `navigate`: each can make a tab in whichever browser it lands on. A connected browser is known to be safe when:
   - its `deviceId` is the `Preferred device id`;
   - it is the one browser that appeared after a wake that printed `opened` or `launched`, below;
   - a marker check earlier in this session found an allowed app behind its `deviceId`;
   - or no app is set never to use.

   Of several safe browsers, take the `Preferred device id`, else the one `inUse`. Select it with `select_browser` if it isn't the one `inUse`, and go to step 3. When none is safe, or a `Preferred device id` is set but not listed, wake the preferred app:
   1. Wake nothing, and go to step 2.4, when no `Preferred app` is set, when `Wake` is `off`, or when the `Preferred app` is an app never to use. The script reads no preferences file, so it refuses only the apps passed to it as `--never-use`. Run `which_browser.py resolve --app '<Preferred app>'`, which prints the app's name, bundle id and path, tab-separated, and compare each `Never use` entry with all three, ignoring case; for an entry that is a path, also compare the bundle id `resolve --app '<entry>'` prints. A match on any of them is an app never to use.

      Otherwise run the bundled script's `wake`, passing the `Preferred app` as `--app`, the `Wake` setting, in lower case, as `--mode`, which defaults to `window`, and every `Never use` entry, without its Markdown formatting, as a `--never-use` of its own:

      ```bash
      python3 "${CLAUDE_SKILL_DIR}/scripts/which_browser.py" wake --app '<Preferred app>' --mode '<Wake>' \
        --never-use '<Never use entry>' --never-use '<another entry>'
      ```

      It refuses, with exit 2 and before asking any app anything, an app that matches a `--never-use` entry, ignoring case and a `.app` suffix, by its name, bundle id, path or bundle file name, or by the bundle id at an entry's path. It warns about, and ignores, an entry that names none of the browsers it reads. If the app is running with no window, it opens one through AppleScript. Under `launch`, it first launches the app in the background if it isn't running; under `window`, it never does. It acts on that app alone. It prints the app, the window's id and what it did, `opened`, `launched` or `already-open`, tab-separated, and exits 1, saying why, when it can't, or 2 on bad usage, such as a missing `--app`, or on an app under `--never-use`. After `opened` or `launched` it waits 15 seconds before it returns, for the extension to connect; `--settle` changes the wait.

   2. Only when it printed `opened` or `launched`, call `list_connected_browsers` again. On exit 1 or 2, or `already-open`, wake changed nothing, so go to step 2.4, and on exit 2 tell the user what the script said.
   3. If exactly one browser is listed that wasn't before, select it with `select_browser`, and go to step 3 to check it with a marker. If none or several are new, go to step 2.4.
   4. Stop. Tell the user which browsers are connected and what wake printed, and ask whether to check each browser with a marker anyway, which may make a tab in an app never to use, or to wait while they open a window in the preferred app. When the `Preferred app` is itself an app never to use, say instead that the two preferences contradict each other, and ask which to change. Suggest saving a `Preferred device id` once a check has found the preferred app, so the next session selects it directly. Never make a tab to find out.

3. Call `tabs_context_mcp` with `createIfEmpty` true, to get this session's tab and its URL.
4. Navigate that tab to its current URL plus a unique fragment, such as `#which-browser-3f9a1c`. Use a fresh random hex value each time, so an old tab can't match.
5. Run the bundled script with the marker:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/which_browser.py" 'which-browser-3f9a1c'
   ```

   It prints one tab-separated line per window holding the tab: app, window id, the window's given name, and its title. It exits 1 when no window matches.

6. Compare the app and window name with the preferences. When the `Preferred app` is a path, compare with the name `which_browser.py resolve --app '<path>'` prints first.
   - **Matches:** go on.
   - **Doesn't match, or the app is one never to use:** call `select_browser` with the next browser step 2 allows, and go back to step 3. If step 2 allows none and this check hasn't woken the preferred app yet, wake it as in step 2.1; otherwise stop as in step 2.4.
   - **No browser matches:** stop and ask the user which to use. Never pick one silently.
   - **Nothing found:** the marker isn't in any running browser the script can read. Say so and ask the user.
7. Once one matches, navigate the tab back to its URL without the marker if the fragment would change the page. If no `Preferred device id` is set, offer to save this browser's `deviceId` as one, in the user's preferences file on this machine, not the project's, since a `deviceId` belongs to one machine's browser. If that file is generated, by Home Manager for one, give the user the line to add to its source instead.
8. If the session moved off the browser it started in, tell the user which app and window it uses now.

When the browser check hook catches a call, do the check above before the next page action.

## Bring the browser forward

When someone is watching and the browser should be in front, activate the preferred app, never another one, by the bundle id `which_browser.py resolve --app '<Preferred app>'` prints:

```bash
osascript -e 'if application id "com.google.Chrome" is running then tell application id "com.google.Chrome" to activate'
```

With no preferred app set, use the app the check found. The `is running` guard matters: `activate` launches a stopped app.

## Writing preferences

To see the app and window names to put in a preferences file, list every window of every running Chromium-family app:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/which_browser.py" --list
```

Add `--urls` to print each window's tab URLs under it, to tell unnamed windows apart. A window has a given name only when the user named it, with Window, then Name Window in Chrome; otherwise its given name is empty and only its title, the active tab's title, shows.

The preferences file holds up to 6 keys, as a Markdown list:

- **Preferred app:** the app's name, such as `Google Chrome`, or the path to its bundle, such as `/Applications/Google Chrome.app` or a Home Manager or Nix store `.app`. The script finds a name with Spotlight, as `<name>.app`, and reads the bundle id from the app's `Info.plist`; it stops when a name matches no app or several, and then the path is what to set. `which_browser.py resolve --app '<name or path>'` shows what it resolves to.
- **Preferred window:** the window's given name, such as `Claude in Chrome`. Match it exactly.
- **Preferred device id:** the `deviceId` that `list_connected_browsers` gives the preferred app, so step 2 selects it directly. It has been seen to survive the extension disconnecting and reconnecting, but may change when the extension or the browser is reinstalled. A stale one is never listed, so step 2 wakes the app; when the marker check then finds the preferred app behind a new `deviceId`, tell the user the saved one is stale and offer the new one.
- **Never use:** apps not to act in, by the name the script prints, such as `Brave Browser`, or by bundle id or path. One per nested bullet. Unlike every other key, a project's file doesn't override the user's here: the entries of both files together are the apps never to use, so a project can't drop an app the user never wants touched.
- **Wake:** what wake may do to the preferred app, `window`, `launch` or `off`; **`window` is the default**:
  - **`window`:** open a window in the app when it is running with none. Never launch it.
  - **`launch`:** also launch the app, in the background, when it isn't running.
  - **`off`:** nothing; stop and tell the user instead.
- **Browser check:** the browser check hook's setting, `deny`, `remind` or `off`, and `remind` when unset; the hooks plugin's section of the coding-agent-skills README says what each does.

For example:

```markdown
- Preferred app: Google Chrome
- Preferred window: Claude in Chrome
- Preferred device id: 6f1c0b2e-…
- Never use:
  - Brave Browser
- Wake: launch
```

With only a preferred app set, any window of it matches. With only apps to never use set, any other app matches.

## Limits

- **macOS only.** The script asks the apps through AppleScript, with `osascript`. Elsewhere, report the `inUse` browser and ask the user if it is the right one.
- **Chromium apps only.** The script asks these, if running:
  - Google Chrome
  - Brave Browser
  - Microsoft Edge
  - Chromium
  - Vivaldi
  - Arc

  It checks that an app is running before asking it, so it never launches one, except `wake --mode launch`, and skips an app that doesn't answer. Google Chrome and Brave Browser are tested; the others may lack a window's given name or tab URLs.

- **Automation permission.** The script reaches each app through Apple Events, so the terminal, or the app running the agent, needs the Automation permission for it, under System Settings, Privacy & Security, Automation. Without it macOS asks once, or `wake` says the app didn't answer.
- **No window, no extension.** Observed, not documented: when Google Chrome runs with no window, the extension's service worker disconnects, and the browser drops off `list_connected_browsers`. After a window opened, it came back within about 10 seconds, with the same `deviceId` as before.
- **Browser profiles.** `wake` counts and opens windows across all of an app's profiles. If the extension's profile has no window but another profile has one, `wake` prints `already-open` and does nothing, and a window it opens may open in the profile the app last used rather than the extension's. Either way no new browser appears, and step 2.4 applies.

- **No tab groups.** AppleScript can't see tab groups, so the match is by window. The extension keeps its tabs in a tab group; if that group opens in another window of the right app, the window won't match, and only the user can move it. Tell them.

## Your preferences

!`cat "$(dirname "${CLAUDE_SKILL_DIR}")/coding-agent-browser-selection.preferences.md" "${CLAUDE_PROJECT_DIR}/.agents/skills/coding-agent-browser-selection.preferences.md" 2>/dev/null || true`

If your agent doesn't run the line above, read these files yourself if they
exist: `coding-agent-browser-selection.preferences.md` next to this skill's folder, then
`.agents/skills/coding-agent-browser-selection.preferences.md` in the project. A project's
file overrides the user's, and the user's overrides this skill's defaults.

## Related skills

When one of these applies and it's in your skill listing, load it
without asking. If it isn't in your listing, tell the user which skill is
missing and ask whether to install it from the same collection this skill
came from; don't apply it from memory.

- `coding-agent-questions-as-first-class-prompts`: asks the user which browser to use through the structured-question tool, not prose.
- `coding-agent-skill-references`: where this skill's preferences files live and who writes them.
