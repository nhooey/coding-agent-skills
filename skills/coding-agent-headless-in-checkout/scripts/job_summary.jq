# How many of a headless job's runs ended in each state, from its outcome files:
#
#   find <folder> -maxdepth 1 -name '*.outcome.json' -exec cat {} + |
#     jq --slurp --raw-input --arg job <job> --arg folder <folder> \
#       --from-file job_summary.jq
#
# The input is the outcome files' text as one string, each file one JSON line,
# as run_headless.py writes it. The output is one JSON object: the job, the
# folder, the number of runs and the count in each state, ok, failed, skipped
# and limit always among them, then any other state in name order. A line that
# holds no JSON object with a status counts as `unreadable`. With --raw-output
# and --arg format table it prints the same as a table.

def known: ["ok", "failed", "skipped", "limit"];

def status_of:
  (try fromjson catch null) as $record
  | if ($record | type) == "object" and ($record.status | type) == "string" and $record.status != ""
    then $record.status
    else "unreadable"
    end;

def pad($width): . + ([range(length; $width)] | map(" ") | add // "");

def table:
  ([.counts | keys_unsorted[] | length] + ["state" | length] | max) as $width
  | "job \(.job): \(.runs) runs with an outcome in \(.folder)",
    ("state" | pad($width)) + "  runs",
    (.counts | to_entries[] | (.key | pad($width)) + "  \(.value)");

[split("\n")[] | select(test("\\S")) | status_of] as $found
| (known + ($found - known | unique)) as $states
| {
    job: $ARGS.named.job,
    folder: $ARGS.named.folder,
    runs: ($found | length),
    counts: (reduce $states[] as $state ({}; .[$state] = ($found | map(select(. == $state)) | length)))
  }
| if $ARGS.named.format == "table" then table else . end
