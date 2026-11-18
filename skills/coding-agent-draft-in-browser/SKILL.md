---
name: coding-agent-draft-in-browser
description: Draft anything whose readers are other people in the place it will be sent from, in the user's browser through Claude in Chrome, left unsent for the user to read, edit and send. The audience is the cue, not the wording of the request, so a GitHub issue, pull request comment or review, an email, a chat message, a forum post or an issue for an upstream project is drafted this way even when the user never said "draft it". The agent never clicks send, submit or post, and never sends the text another way. Covers picking the browser through coding-agent-browser-selection, filling the form, leaving it on its rendered view, keeping personal details out of public drafts, showing a requested change to something someone else owns as a before and after, and handing the draft over. Doesn't apply where no browser form does, such as a commit message or a file in the repository. Use whenever the agent is about to write text that someone other than the user will read where it is posted or sent.
---

# Draft in the browser

_Text meant for other people is drafted where it will be sent from, in the user's browser, filled in and unsent. The user reads it, edits it and sends it; the agent never does._

## The cue is the audience

Apply this whenever the text's readers are people other than the user: maintainers, reviewers, colleagues, a mailing list, a forum. The user doesn't have to say "draft it". "Tell the maintainers about this bug", "reply to her review" and "let the team know" are all drafts, because of who reads them.

Examples:

- a GitHub issue, pull request comment, review or review reply;
- an issue or discussion for an upstream project;
- an email;
- a chat message, in Slack, Discord or the like;
- a forum post or reply.

## Where it doesn't apply

- **No browser form:** a commit message, a file in the repository, a code comment. Those reach their readers through git, and the user reviews them there.
- **A pull request that mirrors its commit,** opened by the script in `github-hygiene-pull-request-mirrors-commit`: its text is the commit's.
- **A kind the preferences mark never to draft** (see Your preferences).

## Never send it

- **No send click:** never click send, submit, post, comment, reply, approve or request changes, never press Enter in a box where Enter sends, and never schedule a send. The user does that, in the browser, after reading it.
- **No other route:** never send the same text with `gh issue create`, `gh pr comment`, `gh pr review`, a mail command or an API. That sends it without the user reading it where it lands.

## The procedure

1. **Load the writing skills** before writing any of the draft:
   - `writing-hygiene-tables-for-comparison`
   - `writing-hygiene-prose-to-lists`
   - `writing-hygiene-headings-as-outline`
   - `writing-hygiene-refer-by-canonical-label`
   - `github-hygiene-refer-to-issues-and-pull-requests`
   - `markdown-hygiene-lists-headings-tables`
   - `markdown-hygiene-escape-reserved-characters`

   A subagent that drafts loads them itself, since it doesn't inherit the skills its caller loaded, and a brief to a drafting subagent names them.

2. **Pick the browser.** Load `coding-agent-browser-selection` and run its check, with this skill's `Browser` preference as the preferred app when one is set. Its apps never to use still hold.
3. **Open the place it is sent from** in a new tab: the new-issue or comment form, the mail web app's compose window or the reply to the thread, the chat's message box in the right conversation, the forum's reply form. For GitHub, `github-workflow-browser-draft-preview` has the URL and editor for each surface; follow its steps for opening, filling, Preview, the red box and bringing the tab forward. If a sign-in page shows, stop and ask the user to sign in; never type credentials.
4. **Fill it in** by typing into the form's own fields, never through URL parameters:
   - **Recipients:** only those the user named or the thread already has.
   - **Title or subject, then the body,** written for the readers there.
   - **Markdown:** where the form renders it, escape what should stay literal per `markdown-hygiene-escape-reserved-characters`. Where it doesn't, write plain text.
   - **A requested change,** shown as below when the draft asks someone to change what they own.
   - **Line breaks in a chat box:** use Shift+Enter, since Enter alone sends.
   - **Read the field back** to check the form kept the text.
5. **Keep personal details out of public drafts.** In anything the public can read, such as an upstream issue or a forum post, put no names, email addresses, usernames, home paths, machine or network names, or private project names, unless the user put them in this draft themselves.
6. **Switch to the rendered view** where the page has one, such as GitHub's Preview tab, so the user reads the draft as it will look rather than as markup. Check the rendering yourself first and fix anything broken in the editor, then leave the page on the rendered view.
7. **Hand it over.** Bring the browser forward (`coding-agent-browser-selection` says how, and only the preferred app), then tell the user what is drafted, where, and to whom, and that it is waiting for them to send. Leave the tab open.
8. **Change it on request** in the same form, switch back to the rendered view, and hand it back again.

## A change to something someone else owns

When the draft asks someone to change a format, config or interface they own, such as an upstream file format, a project's config schema or a library's API, show the change rather than only describing it:

- **Before and after,** each in its own fenced code block, with its language named.
- **A table of the cases it changes:** one row per case, with what happens before the change and after it.

## When no browser can be driven

If Claude in Chrome isn't connected, or no browser matches the preferences and the user doesn't pick one, put the draft in the reply, ready to paste, and say where it goes. Still never send it.

## Your preferences

!`cat "$(dirname "${CLAUDE_SKILL_DIR}")/coding-agent-draft-in-browser.preferences.md" "${CLAUDE_PROJECT_DIR}/.agents/skills/coding-agent-draft-in-browser.preferences.md" 2>/dev/null || true`

If your agent doesn't run the line above, read these files yourself if they
exist: `coding-agent-draft-in-browser.preferences.md` next to this skill's folder, then
`.agents/skills/coding-agent-draft-in-browser.preferences.md` in the project. A project's
file overrides the user's, and the user's overrides this skill's defaults.

A preferences file holds up to 2 keys, as a Markdown list:

- **Browser:** the app to draft in, as macOS knows it, such as `Google Chrome`. Unset, it is the preferred app in `coding-agent-browser-selection`'s preferences, and that skill does the selecting either way.
- **Draft scope:** kinds of text to always draft, and kinds never to draft, under nested `Always` and `Never` bullets. Never-draft kinds are ones the user writes alone: don't draft them, in the browser or in the reply, unless asked.

For example:

```markdown
- Browser: Google Chrome
- Draft scope:
  - Always: replies to review comments on my own pull requests
  - Never: messages in the team chat
```

With no preferences, draft every kind of text this skill covers, in the browser `coding-agent-browser-selection` picks.

## Related skills

When one of these applies and it's in your skill listing, load it
without asking. If it isn't in your listing, tell the user which skill is
missing and ask whether to install it from the same collection this skill
came from; don't apply it from memory.

- `coding-agent-browser-selection`: picks the browser app and window to draft in, and brings only that app forward.
- `coding-agent-skill-references`: where this skill's preferences files live and who writes them.
- `github-hygiene-pull-request-mirrors-commit`: opens a pull request from its commit, which is not drafted in the browser.
- `github-hygiene-refer-to-issues-and-pull-requests`: how a draft refers to GitHub issues and pull requests.
- `github-workflow-browser-draft-preview`: the GitHub surfaces, their editors, Preview and the red box around the draft.
- `markdown-hygiene-escape-reserved-characters`: escapes what should stay literal in a form that renders Markdown.
- `markdown-hygiene-lists-headings-tables`: the Markdown syntax for a draft's lists, headings and tables.
- `writing-hygiene-headings-as-outline`: breaks a long draft into headings that read as its outline.
- `writing-hygiene-prose-to-lists`: turns a draft's run-on enumerations into lists.
- `writing-hygiene-refer-by-canonical-label`: refers to each thing in a draft by one readable label.
- `writing-hygiene-tables-for-comparison`: puts a draft's comparisons, such as a change's before and after, in a table.
