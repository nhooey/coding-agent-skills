---
name: claude-code-garnix-ci
description: When Claude Code pushes a commit to a GitHub remote whose repo is wired up to Garnix CI, start a Monitor against the Garnix check-runs for the pushed SHA so failures surface as a notification instead of being noticed only when the user asks. Trigger any time the assistant runs `git push` (or causes a push via `gh pr create`, etc.) against a remote on a Garnix-enabled repo. Skip on repos with no Garnix wiring.
---

# Watch Garnix CI after Claude Code pushes

When this assistant pushes a commit to a remote GitHub repo, it usually moves
on to the next task. If that repo runs **Garnix CI**, the build outcome lands
~30–120s later as GitHub Checks API status — and silently going unnoticed
until someone asks "did it pass?" is the failure mode this skill exists to
fix.

The pattern: **after every assistant-initiated push, kick off a `Monitor`
loop against the just-pushed SHA so the assistant gets a notification when
the suite resolves.** No polling, no "let me check back in 5 minutes".

For everything about Garnix itself — `garnix.yaml`, the `cache.garnix.io`
substituter, the badge wrapper, sandbox-check vs Action distinction, runner
constraints — see the companion `garnix-ci` skill. This skill is only about
the **post-push watch loop** that Claude Code should attach.

## When this skill applies

Trigger after any push the assistant performs that lands on a remote with
Garnix configured. In practice:

- After `git push` (any branch, any remote that points at GitHub).
- After `gh pr create` / `gh pr ready` / `gh pr merge --auto` etc., since
  those rely on a push having just landed.
- After force-pushes the user explicitly authorized — same monitor needs
  to attach to the new tip SHA.

**Skip when** the remote isn't on a Garnix-enabled repo. Cheapest probes:

```bash
# Either of these implies "Garnix is wired up here":
test -f garnix.yaml                                   # explicit config in repo
gh api "repos/$REPO/commits/$SHA/check-suites" \
  --jq '.check_suites[] | select(.app.slug=="garnix-ci")' \
  | grep -q .                                         # app installed + suite created
```

The `garnix.yaml` test is instant and works pre-push. The `check-suites`
probe is authoritative but only meaningful **after** the push has propagated
(give it a few seconds). Prefer `garnix.yaml` presence as the gate; fall
back to the API probe if you're unsure.

Also skip when the user has explicitly said "don't monitor CI" or similar —
respect that for the rest of the session.

## Wiring up the Monitor

The watch-loop body comes from the `garnix-ci` skill — re-use it verbatim
rather than re-inventing it. The shape:

1. Resolve `SHA=$(git rev-parse HEAD)` and `REPO=<owner>/<repo>` immediately
   after the push returns success.
2. Start the watch-loop as a background `Bash` task (one line per status
   change; exits when all check-runs reach `completed`).
3. Attach `Monitor` to the background task so each emitted line becomes a
   notification — the assistant resumes when the suite resolves and reports
   the result back to the user.

Sketch:

```bash
SHA=$(git rev-parse HEAD); REPO=<owner>/<repo>
prev=""
while true; do
  runs=$(gh api "repos/$REPO/commits/$SHA/check-runs?per_page=100" \
    --jq '[.check_runs[] | select(.app.slug=="garnix-ci")
           | {name, status, conclusion}]' 2>/dev/null || echo "[]")
  count=$(jq 'length' <<<"$runs")
  [ "$count" = "0" ] && { sleep 30; continue; }
  summary=$(jq -c -S . <<<"$runs")
  [ "$summary" != "$prev" ] && {
    jq -r '[.[] | "\(.name)=\(.status)\(if .conclusion then "/\(.conclusion)" else "" end)"]
           | join(", ")' <<<"$runs"
    prev=$summary
  }
  pending=$(jq '[.[] | select(.status != "completed")] | length' <<<"$runs")
  [ "$pending" = "0" ] && {
    fails=$(jq -c '[.[] | select(.conclusion != "success" and .conclusion != "neutral" and .conclusion != "skipped")]' <<<"$runs")
    [ "$(jq length <<<"$fails")" = "0" ] && echo "all green" || echo "failures: $fails"
    break
  }
  sleep 30
done
```

Run with `Bash(run_in_background: true)` and pass the resulting shell id to
`Monitor` so each new stdout line fires a notification. Filter on
`app.slug == "garnix-ci"` — that's the canonical slug; don't guess others.

### Tool prerequisites

The watch loop needs `gh` and `jq` on `PATH`. On a Nix-flake project this
means they belong in the dev shell (see the `nix-flakes` skill on devshell
command discipline) — don't assume the user has them globally. If `gh` is
missing, fall back to `curl -H "Authorization: bearer $GH_TOKEN"` against the
same endpoints, but flag that the fallback is in use so the user knows to
add `gh` to the dev shell.

### Expected timing

A healthy basic flake produces ~10 check-runs in 30–60s (Evaluate,
per-package, per-check, per-devShell, plus the `All Garnix checks`
aggregate). Actions extend this — typically 1–5 minutes per action. If the
loop has been running >10 minutes with checks still pending, surface that as
a warning rather than waiting forever; runner stalls and silent OOMs near
the ~4.5 GB ceiling both look like "still running" to the API.

### Suite-level fallback when builds race the poll

Very fast builds (~30s) sometimes complete between polls, leaving the
check-runs query empty even though the suite is `success`. If the loop sees
zero `garnix-ci` check-runs for >2 minutes after the push, also fetch
`/check-suites` and trust its conclusion — the suite roll-up survives the
race even when the per-check query missed the window:

```bash
gh api "repos/$REPO/commits/$SHA/check-suites" \
  --jq '.check_suites[] | select(.app.slug=="garnix-ci")
        | {status, conclusion}'
```

### Dedupe Action dual-naming

Each Garnix Action posts under **two** check-run names — `app <name>` and
`action <name>` — for the same underlying run. When reporting failures,
dedupe by run id (or strip the `app `/`action ` prefix and unique on the
remainder) so the user doesn't see the same failure listed twice.

## Reporting back

When the Monitor fires its terminal line (`all green` or `failures: …`):

- **All green:** one short sentence to the user confirming CI passed for
  `<sha-short>` on `<branch>`. Don't make a fuss; they may have moved on.
- **Failures:** name the failing check-run(s) and link to
  `https://github.com/<owner>/<repo>/runs/<id>` (the
  `check_runs[*].html_url` from the API). If the assistant is still in the
  same task that triggered the push, offer to investigate; if the task is
  long since over, just surface the failure and let the user decide.

The Garnix run logs themselves live at `app.garnix.io/run/<id>` — link there
if the GitHub status page doesn't show the diagnostic dump (see the
`garnix-ci` skill's "diagnostic dump on EXIT" pattern).

## Gotchas worth remembering

- **Pre-install commits don't get built.** If the repo just installed the
  Garnix GitHub App, only commits pushed *after* the install webhook fired
  produce check-runs. The `check-suites` probe will return empty for those
  even when `garnix.yaml` exists. See the `garnix-ci` skill's "Step 3 —
  fire the first build" for the empty-commit workaround.
- **The first poll often returns zero check-runs.** Garnix may take 5–15s
  to register the suite after the push. The watch-loop's `count=0 → sleep`
  branch handles this; don't tighten the loop expecting instant data.
- **Force-pushes invalidate the prior monitor.** If a force-push lands
  while a Monitor is still attached to the old tip, kill it and start a new
  one against the new SHA — the old SHA's check-runs are now orphaned.
- **Don't double-monitor.** If the user runs `/loop` or another mechanism
  that already polls CI for them, skip starting a parallel Monitor — that
  just spams notifications.

## Cross-references

- `garnix-ci` skill — full Garnix surface, including the watch-loop snippet
  this skill re-uses, the constraints table, and the references section.
- The `Monitor` tool — used to stream stdout from the background watch
  loop into notifications.
