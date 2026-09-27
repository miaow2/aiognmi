# 06: Full `SubscriptionList` argument surface

**What to build:** The remaining Subscribe request options, so users are not forced back to a different
client for anything the RPC supports. All of them apply to both entry points and every Mode.

- `prefix` — subscribe to a deep subtree without repeating a long common path on every Subscription
- `target` — carry the Target name in the request Path so a collector fronting many devices routes correctly
- `encoding` — request `json_ietf` or `proto` instead of the client default
- `updates_only` — a restarting collector skips a large initial dump it already has
- `allow_aggregation` — opt into aggregated Notifications where the schema permits
- `qos` — an integer DSCP value, so telemetry carries the marking the network expects
- `use_models` — a list of dicts with `name`/`organization`/`version`, the same shape the Capabilities
  result already produces, so a mixed-vendor fleet only gets schemas the caller understands
- `extensions` and `depth` — same semantics and validation as `get()`

`prefix`, `target`, and `encoding` are handled identically to `get()`, reusing the existing encoding
resolution and setting the Target on the prefix Path. `depth` is appended as a Depth extension rather
than replacing caller-supplied extensions, and the caller's list is never mutated.

Note for the docs ticket: with `updates_only=True` the `synced` latch flips almost immediately, which is
the surprising case worth calling out.

**Blocked by:** 02

**Status:** resolved

- [ ] `prefix`, `target`, and `encoding` reach the request the way `get()` handles them, reusing the
      existing encoding resolution
- [ ] `updates_only`, `allow_aggregation`, `qos`, and `use_models` reach the `SubscriptionList`
- [ ] `extensions` pass through unchanged
- [ ] `depth` appends a Depth extension without mutating the caller's list, mirroring
      `test_get_depth_appends_to_caller_extensions`
- [ ] Negative or non-integer `qos` and `depth` raise `ValueError`, rejecting `bool`
- [ ] `ruff format`, `ruff check`, and the full suite pass on Python 3.12 and 3.13

## Comments

- Implemented in af299ba. `get()`'s depth handling moved verbatim into `_build_extensions()` in the client module and
  is shared by `get()` and `subscribe()`.
- `extensions`/`depth` go on `SubscribeRequest.extension` (where the proto defines them), passed through
  `SubscribeStream`'s new optional `extensions` argument.
- `qos` rejects negative, non-integer, and `bool` values; no upper bound (DSCP max 63) is enforced.
- The `updates_only`/`synced` caveat is already in the `subscribe()` docstring.
