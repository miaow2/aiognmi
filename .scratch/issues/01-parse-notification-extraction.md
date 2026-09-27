# 01: Fix Notification deletes parsing and extract `parse_notification()`

**What to build:** `get()` against a Target that returns deletes in a Notification currently raises
`AttributeError` instead of returning a result. Fix it so deletes come back as xpath strings on the
Notification, then move the whole proto-to-`Notification` conversion out of the client's Get
post-processing into the utils module as a shared pure function that both Get and the coming Subscribe
work can call.

This is prefactoring: Subscribe would otherwise inherit the bug, and on-change Subscribe traffic is
heavily delete-driven.

Land it as two commits — the bug fix with its regression test first, then the extraction — so the fix
is traceable on its own rather than buried in a refactor.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [ ] A Notification containing deletes parses to the expected list of xpath strings instead of raising
- [ ] A regression test covers the deletes case and fails against the current code
- [ ] `parse_notification()` lives in the utils module as a pure function with no network side effects
- [ ] Get post-processing calls it; `get()` behaviour is otherwise unchanged and existing tests still pass
- [ ] `parse_notification()` is tested by direct call over parametrized protobuf Notifications: updates
      with each typed value, deletes, prefix, timestamp, atomic, duplicates
- [ ] The bug fix and the extraction are separate commits
- [ ] `ruff format`, `ruff check`, and the full suite pass on Python 3.12 and 3.13
