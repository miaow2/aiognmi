# 02: Stream a Subscription and iterate Notifications

**What to build:** A user subscribes to a set of Paths on a Target and receives Notifications as the
Target pushes them, instead of polling `get()` in a loop:

```python
async with client.subscribe(subscriptions=["/interfaces"]) as stream:
    async for notification in stream:
        if stream.synced:
            handle(notification)
```

`subscribe()` is a plain non-async method returning a `SubscribeStream`, so `async with
client.subscribe(...)` reads correctly. The gRPC call opens and the initial request is sent on entering
the block, not in `subscribe()`. Leaving the block — including via `break` — cancels the call, so a
subscription cannot leak. Iteration yields the same `Notification` objects Get produces, so parsing code
is shared between snapshot and streaming paths. Sync Response is not yielded; instead `stream.synced` is
a latch, `False` until the first Sync Response and permanently `True` after, never resetting.

Stream failures raise `AioRpcError` out of the iteration rather than ending it silently, so a collector
learns its subscription died and the caller can write its own reconnect loop. This deliberately inverts
the library's never-raise habit; the reasoning is recorded as an ADR in ticket 07.

`SubscribeStream` is part of the public surface — users need it to type-annotate helpers that pass
streams around. The request-building helpers are not exported.

This is the spine of the feature. Scope it to bare path strings and the default Stream Mode; per-path
options land in ticket 03, the other Modes in 04 and 05, and the rest of the argument surface in 06.

**Blocked by:** 01 (needs the extracted `parse_notification()`)

**Status:** resolved

- [ ] `SubscribeStream` and the request-building helpers live in a new `subscribe` module, not in the
      client module; the client keeps only the entry point and its `_pre_`/`_post_` hooks
- [ ] `SubscribeStream` is exported from the package root alongside `AsyncgNMIClient`
- [ ] `subscribe()` is a plain method; the call opens and the initial request is written on `__aenter__`
- [ ] Iteration yields `Notification` objects matching a scripted response sequence
- [ ] `synced` is `False` before the Sync Response, `True` after, and stays `True` across later Notifications
- [ ] Exiting the context manager cancels the call, including when the block is exited via `break`
- [ ] A scripted call that raises propagates the error out of `async for`
- [ ] The deprecated `error` field on a Subscribe response is logged as a warning and treated as a stream error
- [ ] Iterating a stream never entered with `async with` raises `RuntimeError` naming `async with`
      (no lazy auto-open — it leaves no defined owner responsible for closing)
- [ ] Missing or empty `subscriptions` raises `ValueError`
- [ ] An unknown `mode` string logs a warning and falls back to `stream`, matching `get_encoding` and `data_type`
- [ ] A scriptable fake bidirectional call fixture joins `conftest.py` beside the existing stub fixtures:
      it records written requests, replays a caller-supplied response sequence, and can be told to raise
- [ ] Tests reach `SubscribeStream` only through `client.subscribe()`, never by constructing it directly
- [ ] `ruff format`, `ruff check`, and the full suite pass on Python 3.12 and 3.13
