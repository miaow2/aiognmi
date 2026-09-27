# 04: Take a one-shot snapshot with `subscribe_once()`

**What to build:** An inventory tool takes a single consistent snapshot of a subtree and has the Target
close the stream when it is done, with code that looks like the rest of the caller's `aiognmi` usage:

```python
response = await client.subscribe_once(subscriptions=["/interfaces"])
```

`subscribe_once()` is `async` and returns a `Response`, exactly like `get()` — same `.failed` check, same
error handling. RPC errors are recorded on a failed `Response` rather than raised, matching `get()` and
`set()`; only `SubscribeStream` iteration raises. There is deliberately **no `mode` parameter**: an
argument with one legal value is noise. Every other option passes through unchanged.

Internally it drives the same `SubscribeStream` machinery in `once` Mode and drains it.

The result carries a `SubscribeResult` — its own dataclass mirroring `GetResult`'s single `notifications`
field. The serialised dict is identical to `GetResult`'s, but a Get result class turning up in a Subscribe
code path would mislead every future reader, and renaming `GetResult` would break existing importers.

**Blocked by:** 02, 03 (03 defines the stream-only options this Mode must warn about)

**Status:** ready-for-agent

- [ ] `subscribe_once()` returns a `Response` whose result carries the Notifications
- [ ] On an RPC error it returns a failed `Response` with the error recorded, rather than raising —
      parallel to how Get behaves
- [ ] `subscribe_once()` takes no `mode` parameter
- [ ] A `SubscribeResult` dataclass joins the models module, mirroring `GetResult`
- [ ] `mode="once"` on `subscribe()` maps to the right `SubscriptionList.Mode`
- [ ] Passing `stream_mode`, `sample_interval`, `heartbeat_interval`, or `suppress_redundant` under
      `once` logs a warning that the Target will ignore it, but still sends the request
- [ ] `ruff format`, `ruff check`, and the full suite pass on Python 3.12 and 3.13
