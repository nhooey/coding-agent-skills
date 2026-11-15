#!/usr/bin/env bash
# Checks the coding-agent-kanban-answers mod the way its README says:
# `claude plugin validate`, `tsc -p` and `claude plugin test`.
#
# Usage: check.sh [MOD_DIR]   (default: this script's mod)
#
# tsc needs the Claude Code API declarations in .claude-plugin/types/, which
# the engine lays there when it loads the mod from a folder it watches. Where
# no engine has, this copies them from the ones the running build wrote for
# its plugin-authoring skill, under /tmp/claude-<uid>/bundled-skills/<version>/.
# Needs `claude` and `tsc` on PATH; the repository's dev shell has tsc.

set -euo pipefail

mod=$(cd "${1:-$(dirname "$0")/..}" && pwd)
laid=$mod/.claude-plugin/types/claude-code/index.d.ts

lay_types() {
  local version newest candidate
  version=$(claude --version | cut -d' ' -f1)
  newest=
  for candidate in /tmp/claude-"$(id -u)"/bundled-skills/"$version"/*/plugin-authoring/types/claude-code.d.ts; do
    if [[ -f $candidate && (-z $newest || $candidate -nt $newest) ]]; then
      newest=$candidate
    fi
  done
  if [[ -z $newest ]]; then
    echo "check.sh: no Claude Code $version API types to lay in $mod/.claude-plugin/types/." >&2
    echo "check.sh: load the plugin-authoring skill in a Claude Code session once, which writes them, or start one with --plugin-dir $mod, then run this again." >&2
    exit 1
  fi
  mkdir -p "$(dirname "$laid")"
  cp "$newest" "$laid"
  echo "check.sh: laid $newest" >&2
}

[[ -f $laid ]] || lay_types

echo "== claude plugin validate"
claude plugin validate "$mod"
echo "== tsc -p"
tsc -p "$mod"
echo "== claude plugin test"
claude plugin test "$mod"
