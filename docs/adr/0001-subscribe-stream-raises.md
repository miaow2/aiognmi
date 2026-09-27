# 1. Iterating a SubscribeStream raises AioRpcError

Date: 2026-09-27

## Status

Accepted

## Context

Everywhere else in `aiognmi`, an RPC failure never raises: `get_capabilities()`, `get()`, and `set()` catch
`AioRpcError`, record it on the returned `Response`, and set `Response.failed`. Callers check `.failed`
rather than wrapping calls in `try`/`except`.

Subscribe in `stream` and `poll` Mode is different: there is no single `Response` to return. The caller
iterates a `SubscribeStream` (or calls `.poll()` on it) for as long as the Target keeps the stream open,
possibly for days. If an RPC error during iteration were swallowed, the only thing the caller could observe
is the `async for` loop ending, which looks exactly like the Target closing the stream normally. A
long-running telemetry collector would stop receiving Notifications and keep believing all is well.

## Decision

- Iterating a `SubscribeStream`, or calling `.poll()` on it, **raises** `AioRpcError` when the call fails.
  The deprecated `error` field on a Subscribe response is logged as a warning and raised the same way.
- `subscribe_once()` keeps the library-wide contract: it returns a `Response`, and an RPC error is recorded
  on a failed `Response` rather than raised. There is a `Response` for the user to inspect, just as with
  `get()`.

The rule is: if the call returns a `Response`, errors go on the `Response`; if the caller is consuming a
live stream, errors are raised.

## Consequences

- A dead stream is distinguishable from one that ended normally: failure raises, a normal close ends
  iteration.
- Reconnect, retry, and backoff are left to the caller, and raising is what makes that possible in a few
  lines:

  ```python
  while True:
      try:
          async with client.subscribe(subscriptions=["/interfaces"]) as stream:
              async for notification in stream:
                  handle(notification)
      except AioRpcError:
          await asyncio.sleep(5)
  ```

- Callers of `subscribe()` must handle `AioRpcError` themselves, unlike every other client method. The README
  and the `subscribe()` docstring call this out.
- Read timeouts are also the caller's concern; `asyncio.timeout` around the iteration is the intended
  way to bound a read.
