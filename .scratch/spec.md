# Subscribe RPC

Status: ready-for-agent

## Problem Statement

`aiognmi` implements three of the four gNMI RPCs — Capabilities, Get, and Set — and the README has
advertised "Subscribe (under development)" since the project began. Subscribe is the RPC that makes gNMI
worth using over any other management interface: it is how a target *pushes* state changes and periodic
samples to a client instead of being polled.

Without it, anyone building streaming telemetry, config-drift detection, or event-driven automation on
this library has to either poll `get()` in a loop — which is slow, misses transitions between polls, and
hammers the target — or abandon `aiognmi` for a client that supports Subscribe. Users who chose this
library specifically for its async design are the ones most penalised, because streaming telemetry is
precisely the workload `asyncio` is good at.

Subscribe is also the only bidirectional-streaming RPC in gNMI, so it cannot be bolted onto the existing
"await a coroutine, receive a `Response`" pattern. It needs its own interaction model, which is why it
has stayed unimplemented.

## Solution

Users get two new entry points on `AsyncgNMIClient`.

For continuous telemetry, `subscribe()` returns a `SubscribeStream` — an async context manager that is
also an async iterator. The user opens it, iterates Notifications as the target sends them, and breaks out
whenever they like; leaving the `async with` block tears the stream down:

```python
async with client.subscribe(
    subscriptions=[
        {"path": "/interfaces/interface[name=eth0]/state/counters",
         "stream_mode": "sample", "sample_interval": 10},
        {"path": "/interfaces/interface[name=eth0]/state/oper-status",
         "stream_mode": "on_change"},
    ],
) as stream:
    async for notification in stream:
        if stream.synced:
            handle(notification)
```

For a one-shot dump, `subscribe_once()` behaves exactly like the existing `get()` — await it, get a
`Response` back, check `.failed`:

```python
response = await client.subscribe_once(subscriptions=["/interfaces"])
```

For polled subscriptions, the same `SubscribeStream` exposes `.poll()`, which returns one batch of
Notifications per call:

```python
async with client.subscribe(subscriptions=["/interfaces"], mode="poll") as stream:
    while True:
        batch = await stream.poll()
        handle(batch)
        await asyncio.sleep(60)
```

Intervals are given in seconds, not the protocol's nanoseconds. Subscriptions are plain dicts, matching
the convention `set()` already established, and degrade to bare path strings when every path shares the
same options.

## User Stories

1. As a network automation engineer, I want to subscribe to a set of Paths on a Target, so that I receive
   Notifications as state changes instead of polling `get()` in a loop.
2. As a network automation engineer, I want to iterate Notifications with `async for`, so that streaming
   telemetry reads like ordinary async Python and composes with `asyncio` primitives I already use.
3. As a network automation engineer, I want the stream to be an async context manager, so that leaving the
   block deterministically tears down the gRPC stream and I cannot leak a subscription.
4. As a network automation engineer, I want to `break` out of the iteration early, so that I can stop
   consuming on a condition without special shutdown ceremony.
5. As a telemetry consumer, I want per-Subscription Stream Mode, so that I can take a fast sample of
   interface counters and on-change updates of oper-status in a single subscription request.
6. As a telemetry consumer, I want to set `sample_interval` in seconds, so that I do not have to remember
   the protocol uses nanoseconds and accidentally ask for a 10-nanosecond sample interval.
7. As a telemetry consumer, I want to set `heartbeat_interval` in seconds, so that I get a periodic
   refresh of on-change values even when nothing has changed.
8. As a telemetry consumer, I want to set `suppress_redundant` per Subscription, so that unchanged sampled
   values do not consume bandwidth.
9. As a telemetry consumer, I want fractional-second intervals, so that I can request sub-second sampling
   on targets that support it.
10. As a monitoring system author, I want to know when the Target has sent every value at least once, so
    that I can defer alerting until I have complete initial state and avoid false alarms at startup.
11. As a monitoring system author, I want the Sync Response signal exposed as a simple latched flag, so
    that I do not have to branch on a marker item inside my hot loop.
12. As an inventory tool author, I want `mode="once"`, so that I can take a single consistent snapshot of a
    subtree and have the Target close the stream when it is done.
13. As an inventory tool author, I want `subscribe_once()` to return a `Response` like `get()` does, so
    that snapshot code looks the same as the rest of my `aiognmi` usage.
14. As a scheduled-collection author, I want `mode="poll"`, so that I can hold one open subscription and
    trigger dumps on my own schedule rather than re-establishing a stream each time.
15. As a scheduled-collection author, I want `.poll()` to return the Notifications for that poll cycle, so
    that I get a clean batch boundary without tracking Sync Responses myself.
16. As a user subscribing to a deep subtree, I want to pass a `prefix`, so that I do not repeat a long
    common path on every Subscription.
17. As a user of a collector fronting many devices, I want to set `target`, so that the Target name is
    carried in the request Path and the collector routes my subscription correctly.
18. As a user whose device speaks a particular encoding, I want to set `encoding`, so that I can request
    `json_ietf` or `proto` instead of the client default.
19. As a user restarting a long-running collector, I want `updates_only`, so that I skip a large initial
    dump I already have and receive only subsequent changes.
20. As a user on a constrained link, I want to set `qos`, so that telemetry traffic carries the DSCP
    marking my network expects.
21. As a user with a mixed-vendor fleet, I want to set `use_models`, so that the Target sends only the
    schemas I actually understand.
22. As a user of a Target that aggregates, I want to set `allow_aggregation`, so that I can opt into
    aggregated Notifications where the schema permits it.
23. As a user of a large subtree, I want to set `depth`, so that I bound how much of the tree the Target
    walks, the same way I already can on `get()`.
24. As a user of vendor-specific gNMI features, I want to pass prebuilt `extensions`, so that Subscribe is
    as extensible as `get()` and `set()` already are.
25. As a user parsing results, I want Subscribe to yield the same `Notification` objects `get()` produces,
    so that I can share parsing code between snapshot and streaming paths.
26. As an operator of a long-lived collector, I want stream failures to raise, so that my process learns
    the subscription died instead of silently believing all is well when iteration just stops.
27. As an operator of a long-lived collector, I want to write my own reconnect loop around the context
    manager, so that backoff and replay policy stay under my control.
28. As a user of `subscribe_once()`, I want RPC errors recorded on a failed `Response` rather than raised,
    so that snapshot error handling matches `get()` and `set()`.
29. As a developer reading a traceback, I want a clear `RuntimeError` if I iterate a stream I never entered
    with `async with`, so that I learn the correct usage immediately instead of hanging or leaking.
30. As a developer who mistakenly iterates a poll-mode stream, I want an error naming `.poll()`, so that I
      am pointed at the right API instead of two consumers racing over one read stream.
31. As a developer who typos a mode name, I want a warning and a sane fallback, so that behaviour matches
    what `encoding` and `data_type` already do on `get()`.
32. As a developer who passes a negative interval, I want a `ValueError`, so that an impossible request is
    caught locally instead of confusing the Target.
33. As a developer who passes no Subscriptions, I want a `ValueError`, so that an obviously-empty request
    fails loudly rather than opening a subscription to nothing.
34. As a developer who sets `stream_mode` under `mode="once"`, I want a warning that the Target will ignore
    it, so that I understand why my sampling setting had no effect.
35. As a user annotating my own helper functions, I want `SubscribeStream` importable from the package
    root, so that I can type-annotate code that passes streams around.
36. As a user of `get()` against a Target that returns deletes in a Notification, I want deletes parsed
    correctly, so that `get()` stops raising `AttributeError` on perfectly valid responses.
37. As a user subscribing on-change, I want deletes surfaced in Notifications, so that I learn when a list
    entry disappears and not only when values change.
38. As a new user reading the README, I want a Subscribe example per mode, so that I can copy a working
    starting point for streaming, snapshot, and polled collection.
39. As a new user reading the README, I want "Subscribe (under development)" to become an unqualified
    supported RPC, so that I can trust the feature list.
40. As a future maintainer, I want the decision to raise from stream iteration recorded as an ADR, so that
    I understand why Subscribe deliberately breaks the library's never-raise habit.
41. As a future maintainer, I want the Subscribe vocabulary in the glossary, so that Mode and Stream Mode
    do not get conflated the way the protobuf conflates them.

## Implementation Decisions

### Module layout

- A new `subscribe` module holds `SubscribeStream` and the request-building helpers for
  `SubscriptionList`/`Subscription` messages. The client module is already the largest in the package;
  Subscribe does not go in it.
- The client module keeps only the two entry points and the `_pre_`/`_post_` hook pair, matching how
  Capabilities, Get, and Set are each structured today.
- `SubscribeStream` joins the package's public exports alongside `AsyncgNMIClient`. It is part of the
  public surface because users need it for type annotations; the request-builder helpers are not exported.
- The proto-to-`Notification` conversion currently living inline in the client's Get post-processing moves
  to the utils module as `parse_notification()`, and both Get and Subscribe call it. This is a pure
  function with no network side effects, consistent with everything else in that module.

### Entry points

- `subscribe()` is a **plain, non-async method** returning a `SubscribeStream`. This is what makes
  `async with client.subscribe(...)` read correctly; an `async def` would force
  `async with await client.subscribe(...)`.
- `subscribe_once()` is `async` and returns a `Response`, exactly like `get()`. It has **no `mode`
  parameter** — an argument with one legal value is noise. Every other option passes through unchanged.
- Internally `subscribe_once()` drives the same `SubscribeStream` machinery in `once` mode and drains it.

### Argument surface

Both entry points accept:

- `subscriptions`: a list whose items are either a path string or a dict with keys `path`, `stream_mode`,
  `sample_interval`, `heartbeat_interval`, `suppress_redundant`. This mirrors the
  `[{"path": ..., "data": ...}]` convention `set()` established. Method-level `stream_mode`,
  `sample_interval`, `heartbeat_interval`, and `suppress_redundant` act as defaults for any key a dict
  omits, so the common "same settings for every path" case needs only strings.
- `prefix`, `target`, `encoding` — handled identically to `get()`, including reusing the existing encoding
  resolution and setting the Target on the prefix Path.
- `mode` (`subscribe()` only): `"stream"` (default), `"once"`, `"poll"`.
- `updates_only`, `allow_aggregation`, `qos`, `use_models` — the full remaining `SubscriptionList` surface.
  `qos` is an integer DSCP value; `use_models` is a list of dicts with `name`/`organization`/`version`,
  the same shape the Capabilities result already produces.
- `extensions` and `depth` — same semantics and same validation as `get()`, with `depth` appended as a
  Depth extension rather than replacing caller-supplied extensions. The caller's list is never mutated.

### Naming

The protobuf uses "mode" for two unrelated things. The public API disambiguates them permanently:

- `mode` — how the whole request is delivered: `stream`, `once`, `poll` (protobuf `SubscriptionList.Mode`).
- `stream_mode` — how one Subscription triggers: `target_defined`, `on_change`, `sample` (protobuf
  `SubscriptionMode`). Only meaningful under `mode="stream"`.

`Subscription` in the glossary means *one path plus its per-path options*, which is what the
`subscriptions` dicts are — hence the returned handle is `SubscribeStream`, not `Subscription`.

### Units

`sample_interval` and `heartbeat_interval` are given in **seconds** as `int | float` and converted to
nanoseconds internally. This matches `commit_rollback_duration`, which is already seconds, and avoids the
mistake every gNMI user makes exactly once. Documented explicitly in docstrings and README.

### Stream lifecycle

- The gRPC call is opened, and the initial `SubscribeRequest` carrying the `SubscriptionList` sent, in
  `__aenter__` — not in `subscribe()`.
- `__aexit__` cancels the call, so breaking out of the iteration tears the stream down deterministically.
- Iterating a stream that was never entered raises `RuntimeError` naming `async with`. Lazy auto-open is
  rejected: it leaves no defined owner responsible for closing the stream.
- The underlying stub call is opened in writable form (write requests to the call object) rather than by
  passing a request iterator, because poll mode must send further requests after the initial one.

### Iteration and Sync Response

- Iteration yields `Notification` objects — the same dataclass Get produces. Sync Response is **not**
  yielded.
- `synced` is a **latch** on the stream: `False` until the first Sync Response arrives, then permanently
  `True`. It answers one question — "has the Target sent everything at least once?" — and never resets,
  including across poll cycles. With `updates_only=True` it latches almost immediately, which the docs
  call out as the surprising case.
- `poll()` sends a Poll request, reads until the next Sync Response, and returns that cycle's
  `list[Notification]`. Iterating a poll-mode stream raises `RuntimeError` naming `poll()`, preventing two
  consumers racing over one read stream.

### Error handling

The library's existing contract is that it never raises `AioRpcError`. Subscribe splits by whether there
is a `Response` for the user to inspect:

- `subscribe_once()` records the error on a failed `Response`, exactly like `get()` and `set()`.
- Iterating or polling a `SubscribeStream` **raises** `AioRpcError`. Swallowing it would make a dead
  telemetry stream indistinguishable from one that ended normally — a monitoring process would sit there
  believing all is well. Raising is also what makes caller-side reconnect writable at all.
- The deprecated `error` field on a Subscribe response is logged as a warning and treated as a stream
  error on the same path.

This inversion of the library's habit is recorded as an ADR.

### Validation

Following the two habits already in the codebase:

- Unknown `mode`, `stream_mode`, or `encoding` strings → log a warning and fall back (`stream`,
  `target_defined`, and the client default encoding respectively), matching `get_encoding` and
  `data_type`.
- Negative or non-integer `sample_interval`, `heartbeat_interval`, `qos`, or `depth` → `ValueError`,
  matching the existing `depth` and rollback-duration validation, including rejecting `bool`.
- Missing or empty `subscriptions` → `ValueError`. An empty subscription list is never intentional.
- Options the selected mode will ignore (`stream_mode`, `sample_interval`, `heartbeat_interval`,
  `suppress_redundant` under `once`/`poll`) → log a warning but still send the request.

### Result shape

- A `SubscribeResult` dataclass joins the models module, mirroring `GetResult`'s single `notifications`
  field. The serialised dict is identical to `GetResult`'s, but a Get result class appearing in a Subscribe
  code path would mislead every future reader, and renaming `GetResult` would break existing importers.

### Bug fixed in passing

The Get post-processing code guards on a Notification's `delete` field but iterates its `update` field,
then builds an xpath from an `Update` message, which has no path elements. `get()` therefore raises
`AttributeError` against any Target that returns deletes in a Notification. Extracting
`parse_notification()` for Subscribe to share means this bug would be inherited by the new feature, and
on-change Subscribe traffic is heavily delete-driven, so it is fixed as part of the extraction — in its own
commit, with its own regression test, so it is not buried in the feature.

## Testing Decisions

### What makes a good test here

Tests drive the public entry points and assert on what crosses the boundary: the protobuf request that
goes out, and the parsed objects that come back. They do not assert on private helpers, internal
attribute names, or call ordering within the implementation. Every existing test in the suite already
follows this shape and the new ones must not diverge from it.

### Seams

Two seams, both already established in the suite. No new seam is introduced.

**1. The stub attribute on the client** — the seam every request test already uses. Tests replace the
client's stub with a mock, call the real public method, and inspect the outgoing protobuf. Prior art:
`test_client_requests.py` throughout, and the `client_with_mock_get` / `client_with_mock_set` fixtures.

Subscribe differs only in that the stub method returns a *call object* rather than an awaitable, so a
scriptable fake bidirectional call goes in `conftest.py` alongside the existing fixtures. It records the
requests written to it, hands back a caller-supplied sequence of Subscribe responses, and can be told to
raise instead. It implements the write / read / iterate / finish-writing / cancel surface the
implementation uses.

`SubscribeStream` is never constructed directly in tests — it is always reached through
`client.subscribe()`, keeping the tested surface at the public API.

**2. Pure functions in the utils module** — tested by direct call with parametrized inputs and expected
protobuf or Python values. Prior art: the existing `create_gnmi_path`, `create_xpath`, and
`create_update_obj` tests.

### Coverage

Through seam 1:

- Request construction: `mode` maps to the right `SubscriptionList.Mode`; `stream_mode` maps to the right
  `SubscriptionMode`; second-to-nanosecond conversion including fractional seconds; `prefix`, `target`,
  `encoding`, `updates_only`, `allow_aggregation`, `qos`, `use_models`, `suppress_redundant`.
- Per-path dicts override method-level defaults; bare path strings inherit them; a mixed list works.
- `extensions` pass through; `depth` appends a Depth extension without mutating the caller's list —
  mirroring the existing `test_get_depth_appends_to_caller_extensions`.
- Iteration yields `Notification` objects matching a scripted response sequence.
- `synced` is `False` before the Sync Response, `True` after, and stays `True` across subsequent
  Notifications and poll cycles.
- `poll()` writes a Poll request and returns exactly the batch up to the next Sync Response; a second
  `poll()` returns the next batch.
- Iterating a poll-mode stream raises `RuntimeError`; iterating an un-entered stream raises `RuntimeError`.
- Exiting the context manager cancels the call, including when the block is exited via `break`.
- A fake call that raises propagates the error out of `async for` and out of `poll()`.
- `subscribe_once()` returns a `Response` whose result carries the notifications, and on an RPC error
  returns a failed `Response` with the error recorded rather than raising — parallel to how Get behaves.
- Validation: parametrized `ValueError` cases for bad intervals, `qos`, `depth`, and empty
  `subscriptions`, following the parametrized style of the existing invalid-`depth` and
  invalid-rollback-duration tests; warning-and-fallback cases for unknown mode strings.

Through seam 2:

- `parse_notification()` over parametrized protobuf Notifications: updates with each typed value, deletes,
  prefix, timestamp, atomic, duplicates.
- A regression test for the deletes bug: a Notification containing deletes parses to the expected xpath
  list instead of raising.

The full suite must pass on Python 3.12 and 3.13, with `ruff format` and `ruff check` clean, per the
project's CI expectations.

## Out of Scope

- **Reconnect, retry, and backoff.** Explicitly a non-goal, stated in the README. Retry policy is where
  telemetry clients accumulate their worst complexity — backoff, jitter, whether to replay the initial
  dump, whether the sync latch resets — and every user wants different semantics. Raising from iteration
  is what makes a five-line caller-side reconnect loop possible. Worth revisiting once real usage shows a
  common pattern.
- **Read timeouts and keepalive.** No timeout parameter. `asyncio.timeout` around the iteration is stdlib
  and composes better than anything invented here. The commented-out `gnmi_timeout` client parameter stays
  a separate future decision.
- **A version bump.** `__version__` is not changed by this work. Only the README's supported-RPC list is
  corrected.
- **Publishing.** No `twine upload`. Release stays with the workflow and the maintainer's explicit call.
- **Aliases.** The protobuf reserves the removed `use_aliases`/`aliases` fields; nothing to implement.
- **Buffering, deduplication, or persistence of Notifications.** The stream hands the user what the Target
  sent; storage and windowing belong to the caller.
- **Any change to Capabilities, Get, or Set behaviour**, beyond the shared parser extraction and the
  deletes bug fix it necessitates.
- **Regenerating protobuf modules.** The vendored protos already contain everything Subscribe needs.
- **A `Subscription` dataclass.** Dicts ship first; a dataclass can be layered on later without breaking
  them, whereas the reverse is harder.

## Further Notes

- The `mode` / `stream_mode` split is the single most important naming decision here. The protobuf calls
  both "mode", and prior-art clients disagree (`gnmic` uses `mode` + `stream-mode`; `pygnmi` uses `mode` +
  `submode`). `stream_mode` was chosen because it is self-documenting about when it applies. Both terms
  are now in the glossary with the rejected synonyms listed under `_Avoid_`, and issue titles, test names,
  and docs should not drift.
- Seconds-not-nanoseconds is a deliberate departure from protobuf fidelity, which the library otherwise
  respects (extensions are accepted as prebuilt protobuf messages). The precedent is
  `commit_rollback_duration`, already seconds.
- The client already carries a commented-out `no_qos_marking` parameter, indicating QoS was on the
  roadmap; exposing `qos` on Subscribe is where that lands.
- Work is split so the parser extraction and bug fix land independently of API review — see the issues
  alongside this spec.
