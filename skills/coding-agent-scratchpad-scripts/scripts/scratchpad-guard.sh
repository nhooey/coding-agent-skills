#!/usr/bin/env bash
# PreToolUse (Bash|Write|Edit) and SubagentStart hook: keep loose program
# files out of temporary directories.
#
# Exits at once, printing nothing, when the hook's input names no temporary
# root, or names one but no program extension and no `source` or `.`, unless it
# holds a file-writing call such as `open(` or a heredoc beside a `>` or `tee`.
# Anything else goes to scratchpad_guard.py beside this script, which decides.
# Does nothing when python3 isn't on PATH.

set -u

# The whole input, read without starting a process; read stops at end of input.
IFS= read -r -d '' input || true

case "$input" in
*'"SubagentStart"'*) ;;
# An inline program or a heredoc that may write a file.
*'open('* | *'.write_text('* | *'.write_bytes('* | *'writeFile'* | *'File.write('*) ;;
*'<<'*'>'* | *'>'*'<<'* | *'<<'*'tee '* | *'tee '*'<<'*) ;;
*)
  tmpdir=${TMPDIR:-}
  tmpdir=${tmpdir%/}
  case "$input" in
  */tmp/* | */var/folders/* | *'$TMPDIR'* | *'${TMPDIR}'*) ;;
  *) [ -n "$tmpdir" ] && [[ "$input" == *"$tmpdir/"* ]] || exit 0 ;;
  esac
  program='\.(py|sh|bash|zsh|fish|js|mjs|cjs|ts|rb|pl|awk|sed|bb|clj)([^A-Za-z0-9]|$)'
  sourced='(source|(^|[^A-Za-z0-9_./-])\.)[[:space:]]'
  [[ "$input" =~ $program || "$input" =~ $sourced ]] || exit 0
  ;;
esac

here=${BASH_SOURCE[0]%/*}
[ "$here" != "${BASH_SOURCE[0]}" ] || here=.
command -v python3 >/dev/null 2>&1 || exit 0
exec python3 -I -S "$here/scratchpad_guard.py" <<<"$input"
