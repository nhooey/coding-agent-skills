#!/usr/bin/env bats
# job_summary.jq over the fixture outcome files in fixtures/, through the
# command line SKILL.md gives under "A job's figures".

bats_require_minimum_version 1.5.0

setup() {
  PROGRAM="$BATS_TEST_DIRNAME/../../skills/coding-agent-headless-in-checkout/scripts/job_summary.jq"
  FIXTURES="$BATS_TEST_DIRNAME/fixtures"
}

# summary <folder> [jq option ...]: the job "night"'s summary from <folder>.
summary() {
  local folder=$1
  shift
  find "$folder" -maxdepth 1 -name '*.outcome.json' -exec cat {} + |
    jq --slurp --raw-input --arg job night --arg folder "$folder" "$@" --from-file "$PROGRAM"
}

@test "counts each state from the outcome files only" {
  run --separate-stderr summary "$FIXTURES/night"
  [ "$status" -eq 0 ]
  [ "$(jq --compact-output .counts <<<"$output")" = '{"ok":2,"failed":1,"skipped":0,"limit":1,"unreadable":1}' ]
  [ "$(jq .runs <<<"$output")" -eq 5 ]
  [ "$(jq --raw-output .folder <<<"$output")" = "$FIXTURES/night" ]
  [ "$(jq --raw-output .job <<<"$output")" = night ]
}

@test "prints a table with --arg format table" {
  run --separate-stderr summary "$FIXTURES/skipped" --raw-output --arg format table
  [ "$status" -eq 0 ]
  [[ ${lines[0]} == *"1 runs"* ]]
  [ "$(echo ${lines[1]})" = "state runs" ]
  [ "$(printf '%s\n' "${lines[@]:2}" | tr -s ' ' | tr '\n' ',')" = "ok 0,failed 0,skipped 1,limit 0," ]
}

@test "a job with no outcome files prints zero counts" {
  run --separate-stderr summary "$BATS_TEST_TMPDIR/no-such-folder"
  [ "$status" -eq 0 ]
  [ "$(jq --compact-output .counts <<<"$output")" = '{"ok":0,"failed":0,"skipped":0,"limit":0}' ]
  mkdir "$BATS_TEST_TMPDIR/empty"
  run --separate-stderr summary "$BATS_TEST_TMPDIR/empty" --raw-output --arg format table
  [ "$status" -eq 0 ]
  [[ ${lines[0]} == *"0 runs"* ]]
}

@test "another folder's outcome files are counted from that folder" {
  run --separate-stderr summary "$FIXTURES/elsewhere"
  [ "$status" -eq 0 ]
  [ "$(jq .counts.failed <<<"$output")" -eq 1 ]
}

@test "unknown states follow the known ones, in name order" {
  run --separate-stderr summary "$FIXTURES/unknown"
  [ "$status" -eq 0 ]
  [ "$(jq --compact-output '.counts | keys_unsorted' <<<"$output")" = '["ok","failed","skipped","limit","beta","zeta"]' ]
}
