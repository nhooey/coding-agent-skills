#!/usr/bin/env bash
# Stop hook: lint the main session's final response with lint_reply.py, in a
# session that has loaded coding-agent-kanban-turn-responses.
#
# Exits at once when the input names no transcript, or the transcript never
# mentions the skill, so a session that never loaded it starts no Python.
# Anything else goes to reply_lint_hook.py beside this script, which checks
# that the skill was loaded, reads the `Reply lint` setting and decides, with
# lint_reply.py and reply_turns.py beside it too. Does nothing when python3
# isn't on PATH.

set -u

skill=coding-agent-kanban-turn-responses

# The whole input, read without starting a process; read stops at end of input.
IFS= read -r -d '' input || true

[[ "$input" =~ \"transcript_path\"[[:space:]]*:[[:space:]]*\"([^\"]*)\" ]] || exit 0
transcript=${BASH_REMATCH[1]}
[ -f "$transcript" ] && grep -q -F "$skill" "$transcript" || exit 0

here=${BASH_SOURCE[0]%/*}
[ "$here" != "${BASH_SOURCE[0]}" ] || here=.
command -v python3 >/dev/null 2>&1 || exit 0
exec python3 -I -S "$here/reply_lint_hook.py" <<<"$input"
