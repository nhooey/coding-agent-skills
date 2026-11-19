#!/usr/bin/env bash
# PreToolUse (Claude in Chrome tools) and PostToolUse (Bash, select_browser,
# switch_browser) hook: have a session check which browser it drives before
# its first page action, and again after it switches browser.
#
# Exits at once, starting no process, for a Bash call whose input doesn't name
# which_browser.py, and for a browser tool that neither acts on a page nor
# switches browser. Anything else goes to browser_check_hook.py beside this
# script, which keeps the session's record and decides. Does nothing when
# python3 isn't on PATH.

set -u

# The whole input, read without starting a process; read stops at end of input.
IFS= read -r -d '' input || true

[[ "$input" =~ \"tool_name\"[[:space:]]*:[[:space:]]*\"([^\"]*)\" ]] || exit 0
case "${BASH_REMATCH[1]}" in
Bash) [[ "$input" == *which_browser.py* ]] || exit 0 ;;
# The tools that act on a page, and the switches that clear the record; keep
# in step with PAGE_ACTING and SWITCHING in browser_check_hook.py.
mcp__claude-in-chrome__navigate | mcp__claude-in-chrome__computer | mcp__claude-in-chrome__form_input) ;;
mcp__claude-in-chrome__javascript_tool | mcp__claude-in-chrome__file_upload) ;;
mcp__claude-in-chrome__tabs_create_mcp | mcp__claude-in-chrome__browser_batch) ;;
mcp__claude-in-chrome__select_browser | mcp__claude-in-chrome__switch_browser) ;;
*) exit 0 ;;
esac

here=${BASH_SOURCE[0]%/*}
[ "$here" != "${BASH_SOURCE[0]}" ] || here=.
command -v python3 >/dev/null 2>&1 || exit 0
exec python3 -I -S "$here/browser_check_hook.py" <<<"$input"
