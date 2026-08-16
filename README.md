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
* Subscribe (under development)

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
