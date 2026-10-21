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
  none does, and bringing only the preferred app forward. Load it before the
  first mcp__claude-in-chrome__* call of a session, and again after any
  select_browser or switch_browser.
---

# Browser selection

_Before acting in a browser through Claude in Chrome, find out which app and window the session's tab is in, and switch until it is the one the user prefers. Never act in a browser the user said not to use._

## Why

Each browser with the Claude in Chrome extension connected shows up in `list_connected_browsers` as "Browser 1", "Browser 2" and so on. The labels say nothing about which app is which, and the numbering changes between sessions. A session that takes the one marked `inUse` may be driving the user's personal browser, its signed-in accounts and open windows.

The tools can't tell you which app a browser is, but the app can: put a unique marker in the session's tab URL, then ask each running browser through AppleScript which window has a tab with that URL.

## Defaults

With no preferences set, don't switch. Find out which app and window the session is in, tell the user, and go on.

## Check the browser

Do this before the first browser action of a session, and again after any `select_browser` or `switch_browser`.

1. Call `list_connected_browsers` and note the one marked `inUse`.
2. Call `tabs_context_mcp` with `createIfEmpty` true, to get this session's tab and its URL.
3. Navigate that tab to its current URL plus a unique fragment, such as `#which-browser-3f9a1c`. Use a fresh random hex value each time, so an old tab can't match.
4. Run the bundled script with the marker:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/which_browser.py" 'which-browser-3f9a1c'
   ```

   It prints one tab-separated line per window holding the tab: app, window id, the window's given name, and its title. It exits 1 when no window matches.

5. Compare the app and window name with the preferences:
   - **Matches:** go on.
   - **Doesn't match, or the app is one never to use:** call `select_browser` with the next browser's `deviceId` and go back to step 2.
   - **No browser matches:** stop and ask the user which to use, through `AskUserQuestion`. Never pick one silently.
   - **Nothing found:** the marker isn't in any running browser the script can read. Say so and ask the user.
6. Once one matches, navigate the tab back to its URL without the marker if the fragment would change the page.
7. If the session moved off the browser it started in, tell the user which app and window it uses now.

## Bring the browser forward

When someone is watching and the browser should be in front, activate the preferred app, never another one:

```bash
osascript -e 'tell application "Google Chrome" to activate'
```

Use the app named in the preferences, or with none set, the app the check found.

## Writing preferences

To see the app and window names to put in a preferences file, list every window of every running Chromium-family app:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/which_browser.py" --list
```

Add `--urls` to print each window's tab URLs under it, to tell unnamed windows apart. A window has a given name only when the user named it, with Window, then Name Window in Chrome; otherwise its given name is empty and only its title, the active tab's title, shows.

The preferences file holds up to 3 keys, as a Markdown list:

- **Preferred app:** the app name as macOS knows it, such as `Google Chrome`.
- **Preferred window:** the window's given name, such as `Claude in Chrome`. Match it exactly.
- **Never use:** apps not to act in, such as `Brave Browser`. One per nested bullet.

For example:

```markdown
- Preferred app: Google Chrome
- Preferred window: Claude in Chrome
- Never use:
  - Brave Browser
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

  It checks that an app is running before asking it, so it never launches one, and skips an app that doesn't answer. Google Chrome and Brave Browser are tested; the others may lack a window's given name or tab URLs.

- **No tab groups.** AppleScript can't see tab groups, so the match is by window. The extension keeps its tabs in a tab group; if that group opens in another window of the right app, the window won't match, and only the user can move it. Tell them.

## When to apply

- Before the first `mcp__claude-in-chrome__*` action of a session.
- After any `select_browser` or `switch_browser`.
- When the user asks which browser the session is using, or to write browser preferences.

## Your preferences

!`cat "${CLAUDE_SKILL_DIR}/../coding-agent-browser-selection.preferences.md" "${CLAUDE_PROJECT_DIR}/.agents/skills/coding-agent-browser-selection.preferences.md" 2>/dev/null || true`

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
