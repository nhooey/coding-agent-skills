#!/usr/bin/env bash
# PreToolUse (Write|Edit) hook: the first time in a session that a memory file
# is written, let the write go ahead and remind the session to route a lesson
# about how to work into a skill. It never blocks.
#
# Decides from the written path alone, starting no process: exits at once
# unless `file_path` has a `/memory/` folder in it. Anything else goes to
# memory_write_reminder.py beside this script, which matches the path against
# Claude Code's memory folders and keeps the once-per-session count. Does
# nothing when python3 isn't on PATH.

set -u

# The whole input, read without starting a process; read stops at end of input.
IFS= read -r -d '' input || true

[[ "$input" =~ \"file_path\"[[:space:]]*:[[:space:]]*\"([^\"]*/memory/[^\"]*)\" ]] || exit 0

here=${BASH_SOURCE[0]%/*}
[ "$here" != "${BASH_SOURCE[0]}" ] || here=.
command -v python3 >/dev/null 2>&1 || exit 0
exec python3 -I -S "$here/memory_write_reminder.py" <<<"$input"
