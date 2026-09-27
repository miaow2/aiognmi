# 03: Per-Subscription options

**What to build:** A telemetry consumer takes a fast sample of interface counters and on-change updates
of oper-status in a single Subscribe request, by giving each Subscription its own options:

```python
async with client.subscribe(
    subscriptions=[
        {"path": "/interfaces/interface[name=eth0]/state/counters",
         "stream_mode": "sample", "sample_interval": 10},
        {"path": "/interfaces/interface[name=eth0]/state/oper-status",
         "stream_mode": "on_change"},
    ],
) as stream:
    ...
```

Each item in `subscriptions` is either a path string or a dict with `path`, `stream_mode`,
`sample_interval`, `heartbeat_interval`, `suppress_redundant` — mirroring the `[{"path": ..., "data": ...}]`
convention `set()` established. Method-level `stream_mode`, `sample_interval`, `heartbeat_interval`, and
`suppress_redundant` act as defaults for any key a dict omits, so the common "same settings for every path"
case needs only strings, and a mixed list works.

Intervals are given in **seconds**, `int | float`, and converted to nanoseconds internally. This is a
deliberate departure from protobuf fidelity: it matches `commit_rollback_duration`, which is already
seconds, and avoids the ten-nanosecond sample interval every gNMI user asks for exactly once. Fractional
seconds are supported so sub-second sampling is expressible. Document the unit explicitly in docstrings.

`stream_mode` means how one Subscription triggers (`target_defined`, `on_change`, `sample`) and is only
meaningful under `mode="stream"` — do not let it drift toward "submode" or "subscription mode" in code,
test names, or docs.

**Blocked by:** 02

**Status:** resolved

- [ ] `stream_mode` maps to the right `SubscriptionMode` for each of `target_defined`, `on_change`, `sample`
- [ ] `sample_interval` and `heartbeat_interval` are seconds and reach the request in nanoseconds,
      including fractional-second values
- [ ] `suppress_redundant` reaches the request per Subscription
- [ ] Per-path dicts override method-level defaults; bare path strings inherit them; a mixed list works
- [ ] An unknown `stream_mode` string logs a warning and falls back to `target_defined`
- [ ] Negative or non-integer `sample_interval` or `heartbeat_interval` raises `ValueError`, rejecting
      `bool`, in the parametrized style of the existing invalid-`depth` tests
- [ ] Docstrings state the unit is seconds
- [ ] `ruff format`, `ruff check`, and the full suite pass on Python 3.12 and 3.13
