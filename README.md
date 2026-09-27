[![Supported Versions](https://img.shields.io/pypi/pyversions/aiognmi.svg)](https://pypi.org/project/aiognmi/)
[![PyPI version](https://badge.fury.io/py/aiognmi.svg)](https://badge.fury.io/py/aiognmi)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/charliermarsh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/miaow2/aiognmi/actions/workflows/commit.yaml/badge.svg?branch=develop)](https://github.com/miaow2/aiognmi/actions)

# aiogNMI

## About

This Python library provides an efficient and lightweight gNMI client implementation that leverages asynchronous approach.

### Supported RPCs:

* Capabilities
* Get
* Set
* Subscribe

### Tested on:

* Arista EOS
* Nokia SR OS

Repository contains protobuf files from the [gNMI](https://github.com/openconfig/gnmi/tree/master/proto) repo,
vendored from OpenConfig gNMI release v0.14.1. The upstream core `gnmi_service` proto option remains `0.10.0`.
Earlier gNMI versions should work too; 0.7.0 has been tested successfully.

> **_NOTE:_**  At this moment supporting of the secure connections (with encryption or certificate) is in alpha version. You can use them, but I don't guarantee stable work.

## Install

Install with uv:

```bash
uv add aiognmi
```

Or install into the current environment:

```bash
uv pip install aiognmi
```

## Examples

`Capabilities` RPC

```python
import asyncio

from aiognmi import AsyncgNMIClient


async def main():
    async with AsyncgNMIClient(host="test-1", port=6030, username="admin", password="admin", insecure=True) as client:
        resp = await client.get_capabilities()

    print(resp.result)


if __name__ == "__main__":
    asyncio.run(main())
```

`Get` RPC

```python
import asyncio

from aiognmi import AsyncgNMIClient


async def main():
    async with AsyncgNMIClient(host="test-1", port=6030, username="admin", password="admin", insecure=True) as client:
        resp = await client.get(
            paths=[
                "/interfaces/interface[name=Management0]",
            ]
        )

    print(resp.result)


if __name__ == "__main__":
    asyncio.run(main())
```

Limit the returned subtree with the depth extension convenience option:

```python
resp = await client.get(
    paths=[
        "/interfaces/interface[name=Management0]",
    ],
    depth=2,
)
```

The depth applies to every path in the Get request, matching the gNMI depth extension semantics. A depth of `0`
means no depth limit.

`Set` RPC

```python
import asyncio

from aiognmi import AsyncgNMIClient


async def main():
    async with AsyncgNMIClient(host="test-1", port=6030, username="admin", password="admin", insecure=True) as client:
        resp = await client.set(
            update=[
                {"path": "/interfaces/interface[name=Management0]/config", "data": {"description": "gnmi update test"}}
            ]
        )

    print(resp.result)


if __name__ == "__main__":
    asyncio.run(main())
```

### Commit-confirmed Set operations

Pass a client-generated `commit_id` and a positive rollback duration (in seconds) to start a commit-confirmed Set.
Use the same ID to confirm, cancel, or change the rollback duration of the active commit:

```python
# Start a commit that rolls back after 60 seconds unless it is confirmed.
await client.set(
    update=[{"path": "/system/config", "data": {"hostname": "router-1"}}],
    commit_id="change-1",
    commit_rollback_duration=60,
)

# Confirm the active commit.
await client.set(commit_id="change-1", commit_confirm=True)

# Or cancel the active commit before it is confirmed.
await client.set(commit_id="change-1", commit_cancel=True)

# Or extend its rollback window to 120 seconds.
await client.set(commit_id="change-1", commit_set_rollback_duration=120)
```

Only one commit action can be sent in each Set request. Commit-confirmed support varies by target; unsupported or
invalid operations are returned by the target through the usual gRPC/gNMI error handling.

Prebuilt gNMI extensions can be passed to `get()` and `set()` with the `extensions` argument. Commit-confirmed
operations are supported through the `set()` arguments shown above, and `get(depth=...)` builds the depth extension
automatically. Other feature-specific extensions can still be passed as prebuilt `Extension` messages.

```python
import asyncio

from aiognmi import AsyncgNMIClient, Extension, ExtensionID, RegisteredExtension


async def main():
    extension = Extension(
        registered_ext=RegisteredExtension(id=ExtensionID.Value("EID_EXPERIMENTAL"), msg=b"custom-payload")
    )

    async with AsyncgNMIClient(host="test-1", port=6030, username="admin", password="admin", insecure=True) as client:
        resp = await client.get(
            paths=[
                "/interfaces/interface[name=Management0]",
            ],
            extensions=[extension],
        )

    print(resp.result)


if __name__ == "__main__":
    asyncio.run(main())
```

`Subscribe` RPC

Subscribe supports all three gNMI Modes: `stream` (the Target pushes Notifications until you stop), `once` (the
Target sends one dump and closes), and `poll` (the Target sends a dump each time you ask).

Stream Mode with `async for`:

```python
import asyncio

from aiognmi import AsyncgNMIClient


async def main():
    async with AsyncgNMIClient(host="test-1", port=6030, username="admin", password="admin", insecure=True) as client:
        async with client.subscribe(
            subscriptions=[
                {"path": "/interfaces/interface[name=Management0]/state/counters",
                 "stream_mode": "sample", "sample_interval": 10},
                {"path": "/interfaces/interface[name=Management0]/state/oper-status",
                 "stream_mode": "on_change"},
            ],
        ) as stream:
            async for notification in stream:
                if stream.synced:
                    print(notification.dict())


if __name__ == "__main__":
    asyncio.run(main())
```

`subscribe()` is a plain (non-async) method; the gRPC call opens when you enter `async with`, and leaving the block,
including via `break`, cancels it. Each item in `subscriptions` is either a path string or a dict with `path`,
`stream_mode`, `sample_interval`, `heartbeat_interval`, and `suppress_redundant`. The method-level arguments of the
same names are defaults for any key a dict leaves out.

`sample_interval` and `heartbeat_interval` are in **seconds** (`int` or `float`), not the nanoseconds used on the
wire; the client converts them.

`stream.synced` is `False` until the Target's first Sync Response and stays `True` after it. With
`updates_only=True` the Target skips the initial dump, so `synced` becomes `True` almost immediately.

`subscribe()` also accepts `prefix`, `target`, `encoding`, `updates_only`, `allow_aggregation`, `qos`, `use_models`,
`extensions`, and `depth`; `prefix`, `target`, `encoding`, `extensions`, and `depth` behave as they do in `get()`.

Once Mode with `subscribe_once()`, which returns a `Response` just like `get()`:

```python
resp = await client.subscribe_once(subscriptions=["/interfaces/interface[name=Management0]"])

if not resp.failed:
    print(resp.result)
```

Poll Mode with `.poll()`, which sends a Poll request and returns that cycle's list of Notifications:

```python
async with client.subscribe(subscriptions=["/interfaces"], mode="poll") as stream:
    while True:
        notifications = await stream.poll()
        print([n.dict() for n in notifications])
        await asyncio.sleep(60)
```

A poll-mode stream cannot be iterated with `async for`; use `.poll()`. Options that only apply to `stream` Mode
(`stream_mode`, `sample_interval`, `heartbeat_interval`, `suppress_redundant`) are ignored by the Target under
`once` and `poll`; the client logs a warning and still sends the request.

### Subscribe errors, reconnects, and timeouts

Unlike the other methods, iterating a stream or calling `.poll()` **raises** `grpc.aio.AioRpcError` when the
subscription fails, so a dead stream is never mistaken for one that ended normally. `.poll()` raises `EOFError` if
the Target closes the stream in the middle of a poll cycle. `subscribe_once()` does not raise; RPC errors are
recorded on the failed `Response`, as with `get()`.

Reconnect, retry, backoff, and read timeouts are deliberately left to the caller. A reconnect loop is a few lines:

```python
from grpc.aio import AioRpcError

while True:
    try:
        async with client.subscribe(subscriptions=["/interfaces"]) as stream:
            async for notification in stream:
                print(notification.dict())
    except AioRpcError:
        await asyncio.sleep(5)
```

Use `asyncio.timeout` to bound how long you wait:

```python
async with asyncio.timeout(30):
    resp = await client.subscribe_once(subscriptions=["/interfaces"])
```

## TLS

> **_NOTE:_**  At this moment supporting of the secure connections (with encryption or certificate) is in alpha version. You can use them, but I don't guarantee stable work.

Secure connections are controlled by the `verify` argument on `AsyncgNMIClient` (`insecure=True` bypasses TLS
entirely and `verify` has no effect in that case):

* `verify=True` (default) — the server certificate is actually verified. If `path_root_cert` is provided, it is
  used as the trust anchor; otherwise the system trust store is used.
* `verify=False` — the client fetches the target's certificate over the network and trusts it
  (trust-on-first-use), overriding gRPC's hostname check to match the fetched certificate. A warning is logged
  whenever verification is disabled. In this mode `path_root_cert` is ignored, while `path_private_key` and
  `path_cert_chain` continue to provide client credentials for mTLS. The target certificate must contain at
  least a SAN or a subject CN; gRPC always verifies the certificate identity, so `connect()` raises
  `ValueError` if no identity can be extracted from the fetched certificate.

> **_Behavior change:_** earlier versions silently auto-fetched and trusted the server certificate even with the
> default settings. If you relied on that behavior, pass `verify=False` explicitly — with the current default
> (`verify=True`) an untrusted certificate will now cause the connection to fail.

```python
import asyncio

from aiognmi import AsyncgNMIClient


async def main():
    async with AsyncgNMIClient(
        host="test-1", port=6030, username="admin", password="admin", verify=False
    ) as client:
        resp = await client.get_capabilities()

    print(resp.result)


if __name__ == "__main__":
    asyncio.run(main())
```

## Credits

My work is inspired by these people:

1. [Anton Karneliuk](https://github.com/akarneliuk) and his [pyGNMI](https://github.com/akarneliuk/pygnmi) library
2. [Carl Montanari](https://github.com/carlmontanari) and his [scrapli](https://github.com/carlmontanari/scrapli) library
