# 05: Drive polled collection with `.poll()`

**What to build:** A scheduled collector holds one open subscription and triggers dumps on its own
schedule, instead of re-establishing a stream each time:

```python
async with client.subscribe(subscriptions=["/interfaces"], mode="poll") as stream:
    while True:
        batch = await stream.poll()
        handle(batch)
        await asyncio.sleep(60)
```

`poll()` sends a Poll request, reads until the next Sync Response, and returns that cycle's
`list[Notification]` — a clean batch boundary the caller does not have to track Sync Responses to find.
The `synced` latch does not reset across poll cycles; it answers one question ("has the Target sent
everything at least once?") and stays `True`.

A poll-mode stream is not iterable: `async for` over it raises `RuntimeError` naming `.poll()`, which
both points the caller at the right API and prevents two consumers racing over one read stream. This is
why the underlying stub call is opened in writable form rather than by passing a request iterator —
poll Mode must send further requests after the initial one.

**Blocked by:** 02, 03 (03 defines the stream-only options this Mode must warn about)

**Status:** ready-for-agent

- [ ] `mode="poll"` maps to the right `SubscriptionList.Mode`
- [ ] `poll()` writes a Poll request and returns exactly the batch up to the next Sync Response
- [ ] A second `poll()` returns the next batch
- [ ] `synced` stays `True` across poll cycles
- [ ] Iterating a poll-mode stream raises `RuntimeError` naming `poll()`
- [ ] A scripted call that raises propagates the error out of `poll()`
- [ ] Passing `stream_mode`, `sample_interval`, `heartbeat_interval`, or `suppress_redundant` under
      `poll` logs a warning that the Target will ignore it, but still sends the request
- [ ] `ruff format`, `ruff check`, and the full suite pass on Python 3.12 and 3.13
