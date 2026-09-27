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

**Status:** resolved

- [ ] `mode="poll"` maps to the right `SubscriptionList.Mode`
- [ ] `poll()` writes a Poll request and returns exactly the batch up to the next Sync Response
- [ ] A second `poll()` returns the next batch
- [ ] `synced` stays `True` across poll cycles
- [ ] Iterating a poll-mode stream raises `RuntimeError` naming `poll()`
- [ ] A scripted call that raises propagates the error out of `poll()`
- [ ] Passing `stream_mode`, `sample_interval`, `heartbeat_interval`, or `suppress_redundant` under
      `poll` logs a warning that the Target will ignore it, but still sends the request
- [ ] `ruff format`, `ruff check`, and the full suite pass on Python 3.12 and 3.13

## Comments

- Implemented in cc59975. The stream-only-option warning under poll is provided by ticket 04's
  `warn_on_ignored_stream_options()`.
- If the Target ends the stream before the cycle's Sync Response, `poll()` raises `EOFError` rather than returning a
  partial batch, so a dead stream is not mistaken for a healthy one.
- `poll()` sends a Poll and then reads; it does not pre-drain. This matches gNMI spec §3.5.1.5.3 (the Target generates
  updates "on reception of" a Poll message), so a conforming Target sends nothing before the first Poll.
- No lock guards concurrent `poll()` calls on one stream.
