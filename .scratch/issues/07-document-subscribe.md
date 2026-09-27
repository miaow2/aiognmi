# 07: Document Subscribe and record the raising decision

**What to build:** A new user reading the README finds a working starting point for each Mode and can
trust the feature list; a future maintainer finds the reasoning behind the one place this library
deliberately raises.

README: an example per Mode — streaming with `async for`, snapshot with `subscribe_once()`, and polled
collection with `.poll()` — plus the seconds-not-nanoseconds unit called out where intervals appear, and
the `updates_only` case where `synced` latches almost immediately. "Subscribe (under development)" in
the supported-RPC list becomes an unqualified supported RPC. State that reconnect, retry, backoff, and
read timeouts are explicit non-goals, and that `asyncio.timeout` around the iteration is the intended
way to bound a read.

ADR: record why iterating a `SubscribeStream` raises `AioRpcError` when the library's contract everywhere
else is that it never raises. Swallowing it would make a dead telemetry stream indistinguishable from one
that ended normally — a monitoring process would sit there believing all is well — and raising is what
makes a five-line caller-side reconnect loop writable at all. `subscribe_once()` keeps the `Response`
contract because there is a `Response` for the user to inspect. This is the first ADR in the repo, so it
creates `docs/adr/`.

The glossary work is already done: `CONTEXT.md` carries Subscription, Mode, Stream Mode, and Sync
Response with their `_Avoid_` lists. Check the shipped code and docs have not drifted from those terms
rather than adding new ones.

Do not bump `__version__` and do not publish; only the README's supported-RPC list is corrected.

**Blocked by:** 03, 04, 05, 06

**Status:** resolved

- [ ] README has a Subscribe example for each of stream, once, and poll
- [ ] README states intervals are in seconds
- [ ] README notes reconnect/retry/backoff and read timeouts are non-goals, and points at `asyncio.timeout`
- [ ] "Subscribe (under development)" becomes an unqualified supported RPC
- [ ] An ADR under `docs/adr/` records why stream iteration raises while `subscribe_once()` does not
- [ ] Code, tests, and docs use the glossary's Mode / Stream Mode split, not the rejected synonyms
- [ ] `__version__` is unchanged
