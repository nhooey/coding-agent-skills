#!/usr/bin/env bash
# PostToolUse (Write|Edit) hook: run the plan graph's check after an edit to a
# plan node, and add any finding beside the edit's result. It never blocks.
#
# Decides from the written path alone, starting no process: exits at once
# unless `file_path` is a `.md` under the plan folder, other than its
# README.md, in a project that has that folder. The plan folder is
# `agents/plans`, or the `Plan folder` line in
# `.agents/skills/coding-agent-plans-as-graph.preferences.md`, the project's
# (under $CLAUDE_PROJECT_DIR) over the user's (under ~). The project root is
# the path before the plan folder's first occurrence in `file_path`.
#
# Anything else goes to plans_check_hook.py beside this script, which imports
# plans.py from the same folder. Does nothing when python3 isn't on PATH.

set -u

# The whole input, read without starting a process; read stops at end of input.
IFS= read -r -d '' input || true

[[ "$input" =~ \"file_path\"[[:space:]]*:[[:space:]]*\"([^\"]*\.md)\" ]] || exit 0
path=${BASH_REMATCH[1]}

name=coding-agent-plans-as-graph.preferences.md
folder=agents/plans
for prefs in "${HOME:-}/.agents/skills/$name" "${CLAUDE_PROJECT_DIR:-}/.agents/skills/$name"; do
  [ -f "$prefs" ] || continue
  while IFS= read -r line || [ -n "$line" ]; do
    if [[ "$line" =~ ^[-*[:space:]]*[Pp]lan\ folder:[[:space:]]*\`?([^\`[:space:]]+) ]]; then
      folder=${BASH_REMATCH[1]%/}
    fi
  done <"$prefs"
done
folder=${folder#./}

[[ "$path" == /* ]] || path=$PWD/$path
[[ "$path" == */"$folder"/* ]] || exit 0
root=${path%%/"$folder"/*}
rest=${path#"$root/$folder/"}
[ "$rest" != README.md ] || exit 0
[ -d "$root/$folder" ] || exit 0

here=${BASH_SOURCE[0]%/*}
[ "$here" != "${BASH_SOURCE[0]}" ] || here=.
command -v python3 >/dev/null 2>&1 || exit 0
exec python3 -I -S "$here/plans_check_hook.py" "$root" "$folder" "$rest" <<<"$input"
