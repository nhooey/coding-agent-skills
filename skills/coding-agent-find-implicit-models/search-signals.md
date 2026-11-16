# Search signals for implicit models

Signals per kind, with search patterns to start from. A pattern finds candidates; a candidate is a finding only once the write and read sites show one thing's model behind it. Adjust the patterns to the codebase's naming before trusting a miss.

## Lifecycles

- **Flags written together:** two or more booleans or optionals assigned in the same function, or always cleared in the same `reset`, `teardown` or `disconnect`. Search for `is[A-Z]\w+ = (true|false)`, `has[A-Z]`, `did[A-Z]`, `should[A-Z]`, then list each write site's full set of assignments.
- **Optionals standing for a phase:** a `session`, `task`, `token` or `timer` that is `nil`/`None`/`null` in some phases and set in others, checked as `if x != nil` to mean "we are in phase P".
- **Compound guards:** `if a && !b`, `guard isConnected, !isIdentified`, the same pair of flags tested in more than one file.
- **Parallel collections keyed by one id:** `expanded: Set<ID>`, `userClosed: Set<ID>`, `pins: Set<ID>`, or several dictionaries with the same key type on one type. Each id's membership across them is its state.
- **String or integer status fields** compared against literals scattered across files, with no enum.
- **Timestamps as state:** `startedAt`, `finishedAt`, `cancelledAt` optionals whose nil-pattern encodes the phase.
- **Comments that name a state** the code never names: "while reconnecting", "after the handshake", "once loaded".

## Data

- **The same name stored twice:** a field on a model and the same field on a view model, cache or settings object, written in separate places.
- **Two-language recomputation:** a total, id, path, hash or formatted label computed in both the backend and the UI, or in a script and the app. Search for the formula's distinctive constant or function name in each language.
- **Sync code:** `sync`, `refresh`, `update…From`, `didSet` or observers whose only job is copying one value into another.
- **Counters kept beside the collection they count,** and `isEmpty` flags beside the list.
- **Tests that build fixtures with a value the code would derive,** which drift when the derivation changes.

## Conversations

- **Handlers with no state check:** a `switch` on message type at the top level, each arm acting without looking at the current phase.
- **Handshakes by flag:** `didSendHello`, `receivedAck`, `awaitingAuth` and similar, set as steps complete.
- **Retries with no cap:** `retry`, `attempt`, `backoff` loops with no maximum, or a maximum that resets on each reconnect.
- **Request ids with no table of outstanding requests,** or a table never cleared on timeout or disconnect.
- **Messages that can arrive twice or late** (after a cancel, after a reconnect) with no handling for that case.

## Flow

- **Unbounded constructors:** `unbounded_channel`, `Channel.UNLIMITED`, `asyncio.Queue()` with no `maxsize`, `AsyncStream` with the default buffering policy, arrays used as queues.
- **Append without remove:** a collection with `append`, `push` or `insert` sites and no eviction, trim or cap.
- **Caches with no size or age limit,** and logs or histories kept in memory.
- **Producers faster than consumers:** a timer, file watcher or socket feeding work into a queue drained by slower work, with nothing slowing the producer.
- **Fan-out with no limit:** a task spawned per event or per item, with no concurrency cap.

## Failure

- **Fire-and-forget spawns:** `Task {}`, `tokio::spawn`, `asyncio.create_task`, `Process()`, `subprocess.Popen` or `spawn` whose handle is dropped or never awaited.
- **Child processes with no reaper:** no `wait`, no exit handler, no kill on the parent's shutdown.
- **Reconnect loops:** `while true` or recursive reconnect with no attempt cap, no backoff ceiling, or no state reported to the caller.
- **Errors swallowed at the task boundary:** a `catch`, `try?` or `except: pass` at the top of a spawned task, so nobody learns it died.
- **Restart logic spread across callers:** several places each restarting the same worker on their own conditions.
