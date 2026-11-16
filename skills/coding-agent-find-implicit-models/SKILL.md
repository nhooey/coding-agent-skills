---
name: coding-agent-find-implicit-models
description: Find the models a codebase runs without naming them (lifecycles spread over flags, values stored or computed twice, message protocols with no stated order, queues with no bound, child tasks with no supervisor), write each down with file:line evidence before changing code, change one only when the explicit form deletes branches, flags or illegal states, and prove behaviour unchanged with a differential property test over random event sequences. Covers search signals for the five kinds, restraint rules, the default form per language and a checklist for diffs that make illegal states representable. Use when refactoring, untangling flag soup (booleans and optionals that change together, parallel sets tracking one thing), reworking state management, reviewing a design or a diff, or chasing a bug from a combination that can't happen, a copy out of sync, a reconnect loop or a queue that keeps growing.
---

# Find implicit models

_Code often runs a state machine, a protocol or a supervisor that nobody wrote down. Find it, write it down, and make it explicit only where that deletes code or illegal states._

## When to apply

- Refactoring state management, or a type about to gain another boolean or optional about the same thing.
- Flag soup: fields set and cleared together, `if connected && !identified` guards repeated across files.
- A bug from a combination that "can't happen", a copy out of sync with its source, a reconnect that never stops, a queue that grows.
- A design review, or a diff touching state, messages, queues or child processes.

Not for a lone boolean with no partners, or code about to be deleted.

## 1. Search the whole codebase for five kinds

| Kind         | The model nobody wrote           | First signals                                                                                              |
| ------------ | -------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Lifecycle    | one thing's states and moves     | booleans and optionals assigned together; parallel sets keyed by one id (`expanded`, `userClosed`, `pins`) |
| Data         | the source of truth              | one value stored in two places, or recomputed in two languages or layers; code that syncs them             |
| Conversation | message order and limits         | handlers that accept any message in any state; retries with no cap; handshake steps tracked by flags       |
| Flow         | the bound and what happens at it | queues, channels and arrays that only grow; producers with no backpressure                                 |
| Failure      | the supervisor                   | spawned processes or tasks nobody restarts, bounds or reaps; reconnect loops with no ceiling               |

[search-signals.md](search-signals.md) holds the full signals and search patterns per kind. Search past the file in front of you: a lifecycle's flags are often written in one module and read in three. Group hits by the thing they describe (one connection, one panel id), not by file.

## 2. Write each finding down before changing code

One entry per finding, in the reply or a plan node (see preferences), before any edit:

- **Name and kind.**
- **The model as the code runs it**, as a short table or diagram:
  - lifecycle: states and legal transitions;
  - data: every copy, and which one should be the source;
  - conversation: the accepted messages per state, and what an out-of-order one does;
  - flow: producer, consumer, the current bound (often none) and the policy at it;
  - failure: who starts it, who notices it died, the restart policy and its limit.
- **Evidence:** file:line for every flag, write, read and branch the model rests on.
- **Illegal states:** combinations the representation allows that no transition should produce, and whether any path reaches one now.
- **What an explicit form would delete:** the flags, branches, guards and sync code, counted.

Derive a lifecycle's states from the write sites: each place that assigns the flags gives one reachable combination. The combinations representable but never written are the illegal states, not the whole 2ⁿ product.

| From         | Event         | To           | Evidence                             |
| ------------ | ------------- | ------------ | ------------------------------------ |
| disconnected | `connect()`   | connecting   | `Conn.swift:41` sets `isConnecting`  |
| connecting   | socket opened | unidentified | `Conn.swift:88` sets `isConnected`   |
| unidentified | `identify` ok | ready        | `Conn.swift:120` sets `isIdentified` |

## 3. Decide whether it's worth changing

Change it only when the explicit form deletes something: branches, flags, guards, sync code or a reachable illegal state.

- **Tidiness alone is no reason:** record the finding and leave the code.
- **No library for a small machine:** an enum and a function cover a handful of states.
- **No typestate for something built once** and never handed across an API boundary.
- **Derive, don't sync:** make the second copy a computed value. When two languages compute one value, compute it in one and pass the result, or generate both from one definition.
- **A bound has a policy:** block, drop oldest, drop newest or fail. A size with no policy isn't a bound.
- **A supervisor has a limit:** a restart cap, a backoff ceiling, and a place where the final failure surfaces.
- **One model per change:** don't fold several findings into one refactor.

Record the decision with the finding: change, with the deletion count, or leave, with the reason.

## 4. Choose the form per language

The default anywhere: one enum of states, each case carrying its own data, and one pure transition function from state and event to new state and effects.

- **Rust:** enum and `match`; typestate only for protocol order where calling out of order must not compile.
- **Swift with TCA:** a child reducer owning the state enum, scoped from the parent, which keeps no copy of its flags.
- **TypeScript:** a discriminated union and a transition `switch` that ends in an exhaustiveness check against `never`.
- **Python:** an `Enum` or tagged frozen dataclasses with `match`, and a pure transition function returning the new state.
- **Data:** a derived property or selector in place of the stored copy.
- **Flow:** a bounded queue or channel with its policy named where it is constructed.
- **Failure:** the language's structured concurrency or supervision primitive, with the limits from step 3.

## 5. Prove behaviour is unchanged

1. **Before the refactor,** write a property test that drives the old code through random sequences of the events from step 2, repeats and out-of-order ones included, and records the observable outcome after each step: public state, effects emitted, errors.
2. **Commit it passing against the old code.** Its outcomes are the oracle.
3. **Refactor, then run the same sequences against the new code** and compare step by step. Run old and new side by side while both exist; otherwise record the old outcomes to a fixture under a fixed seed first.
4. **Classify every difference:** a refactor bug to fix, or an illegal state the old code reached, which the commit message names.

`trailofbits-property-based-testing` covers generators, shrinking and the library per language.

Random sequences on one thread miss interleavings. When order across actors matters (a reconnect racing a subscription, two clients, a retry crossing a timeout), model the protocol and check it with `tla-check`, or set up a check for the project with `create-formal-verification-skill`.

## 6. Review a diff for newly representable illegal states

- A new boolean or optional on a type that already has a state enum, or another flag about the same thing.
- A new stored field that could be derived from existing ones.
- A new set or dictionary keyed by the same id as an existing one.
- Data added to a state case that is also stored outside the enum.
- A message handler that doesn't check the current state, or a retry with no cap.
- A queue, channel, buffer or cache with no bound, or no policy at the bound.
- A spawned task or process with no owner to cancel, restart or reap it.
- A `default:` or `_ =>` arm in a transition `switch`, which hides the next new case.
- A test asserting a combination the model calls illegal.

Name each hit with file:line and the illegal combination it allows.

## Your preferences

!`cat "${CLAUDE_SKILL_DIR}/../coding-agent-find-implicit-models.preferences.md" "${CLAUDE_PROJECT_DIR}/.agents/skills/coding-agent-find-implicit-models.preferences.md" 2>/dev/null || true`

If your agent doesn't run the line above, read these files yourself if they
exist: `coding-agent-find-implicit-models.preferences.md` next to this skill's folder, then
`.agents/skills/coding-agent-find-implicit-models.preferences.md` in the project. A project's
file overrides the user's, and the user's overrides this skill's defaults.

The keys this skill reads, with its own defaults:

```markdown
- Findings go to: reply
```

`Findings go to` is `reply`, writing step 2's entries into the reply, or `plan`, writing each as a proposed node with `coding-agent-plans-as-graph`.

## Related skills

When one of these applies and it's in your skill listing, load it
without asking. If it isn't in your listing, tell the user which skill is
missing and ask whether to install it from the same collection this skill
came from; don't apply it from memory.

- `coding-agent-plans-as-graph`: where findings go when the preferences say `plan`.
- `create-formal-verification-skill`: sets up a formal check for a project whose protocol orderings need one.
- `tla-check`: model-checks a protocol where interleavings of reconnects, subscriptions or retries matter.
- `trailofbits-property-based-testing`: generators, shrinking and libraries for step 5's differential test.
